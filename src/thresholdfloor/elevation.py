
from rasterio.merge import merge
from rasterio.transform import rowcol
import rasterio
import math
from rasterio.transform import array_bounds
from pathlib import Path
import os
import requests
from functools import lru_cache

SRTM_URL = "https://pythoness.duckdns.org/v1/thresh/srtm"


USE_LOCAL = os.getenv("SRTM_LOCAL", "0") == "1"

tiles = []

from statistics import mean, median


def _offset_lat_lon(lat, lon, north_m=0.0, east_m=0.0):
    """
    Offset a lat/lon by local meter distances.

    north_m: positive north, negative south
    east_m: positive east, negative west
    """
    d_lat = north_m / 111320.0

    cos_lat = math.cos(math.radians(lat))
    if abs(cos_lat) < 1e-6:
        cos_lat = 1e-6

    d_lon = east_m / (111320.0 * cos_lat)
    return lat + d_lat, lon + d_lon


def _radial_offsets(radius_m, directions=8):
    """
    Return evenly spaced radial offsets.

    Uses azimuth convention:
    0° = north, 90° = east, 180° = south, 270° = west.
    """
    for i in range(directions):
        az = (360.0 / directions) * i
        north_m = radius_m * math.cos(math.radians(az))
        east_m = radius_m * math.sin(math.radians(az))
        yield az, north_m, east_m


def _flatness_samples(lat, lon, radius_m, directions=8):
    """
    Sample the candidate crown/top area.

    This tells us whether the proposed floor-pad is reasonably calm,
    instead of a sharp spike.
    """
    values = []

    center = topo(lat, lon)
    if center is not None:
        values.append(float(center))

    for _az, north_m, east_m in _radial_offsets(radius_m, directions):
        s_lat, s_lon = _offset_lat_lon(lat, lon, north_m, east_m)
        elev = topo(s_lat, s_lon)
        if elev is not None:
            values.append(float(elev))

    return values


def tel_finder(
    center_lat,
    center_lon,
    *,
    block_radius_m=500,
    grid_step_m=30,
    floor_radius_m=20,
    ring_radius_m=120,
    directions=8,
    min_prominence_m=5.0,
    min_side_drop_m=1.0,
    max_floor_relief_m=2.0,
    require_all_sides=True,
    keep=25,
    cluster_radius_m=60,
):
    """
    Sweep a block of coordinates for raised clear mounts.

    A candidate is a possible threshold-floor site when:
    - its center elevation is above the surrounding ring,
    - the surrounding area drops away on all or most sides,
    - the immediate crown/top is relatively flat,
    - the site has enough prominence to matter.

    Returns a ranked list of candidate dicts.

    Parameters
    ----------
    center_lat, center_lon:
        Center of the search block.

    block_radius_m:
        Radius of the square-ish sweep area around the center.

    grid_step_m:
        Spacing between sampled candidate points.

    floor_radius_m:
        Radius used to test whether the top/crown is floor-like.

    ring_radius_m:
        Radius used to test surrounding drop.

    directions:
        Number of radial directions sampled around each candidate.
        8 gives cardinal + diagonal slope checks.

    min_prominence_m:
        Minimum height above surrounding median elevation.

    min_side_drop_m:
        Minimum drop required per side.

    max_floor_relief_m:
        Maximum relief allowed across the immediate floor pad.

    require_all_sides:
        If True, every sampled side must drop by at least min_side_drop_m.
        If False, allows one side to fail.

    keep:
        Maximum number of candidates returned.

    cluster_radius_m:
        Prevents returning many nearby points from the same mound.
    """

    if ring_radius_m <= floor_radius_m:
        raise ValueError("ring_radius_m must be larger than floor_radius_m")

    if grid_step_m <= 0:
        raise ValueError("grid_step_m must be positive")

    raw_candidates = []
    span = int(block_radius_m // grid_step_m)

    for north_i in range(-span, span + 1):
        for east_i in range(-span, span + 1):
            north_m = north_i * grid_step_m
            east_m = east_i * grid_step_m

            # Keep the sweep roughly circular inside the block.
            if math.hypot(north_m, east_m) > block_radius_m:
                continue

            lat, lon = _offset_lat_lon(center_lat, center_lon, north_m, east_m)
            center_elev = topo(lat, lon)

            if center_elev is None:
                continue

            center_elev = float(center_elev)

            # Test the proposed floor pad first.
            pad_elevs = _flatness_samples(
                lat,
                lon,
                floor_radius_m,
                directions=directions,
            )

            if len(pad_elevs) < max(3, directions // 2):
                continue

            floor_relief_m = max(pad_elevs) - min(pad_elevs)

            if floor_relief_m > max_floor_relief_m:
                continue

            # Test the surrounding ring.
            ring_elevs = []
            side_drops = []
            side_angles = []

            for az, r_north_m, r_east_m in _radial_offsets(
                ring_radius_m,
                directions=directions,
            ):
                s_lat, s_lon = _offset_lat_lon(lat, lon, r_north_m, r_east_m)
                ring_elev = topo(s_lat, s_lon)

                if ring_elev is None:
                    continue

                ring_elev = float(ring_elev)
                drop_m = center_elev - ring_elev

                ring_elevs.append(ring_elev)
                side_drops.append(drop_m)
                side_angles.append({
                    "azimuth": az,
                    "drop_m": drop_m,
                    "slope_deg": math.degrees(math.atan2(drop_m, ring_radius_m)),
                })

            if len(side_drops) < max(4, directions // 2):
                continue

            sides_that_drop = sum(1 for d in side_drops if d >= min_side_drop_m)

            if require_all_sides:
                if sides_that_drop < len(side_drops):
                    continue
            else:
                # Allow one weak side, useful for saddles or elongated crowns.
                if sides_that_drop < len(side_drops) - 1:
                    continue

            surrounding_median = median(ring_elevs)
            surrounding_mean = mean(ring_elevs)

            prominence_m = center_elev - surrounding_median
            mean_drop_m = mean(side_drops)
            min_drop_m = min(side_drops)
            max_drop_m = max(side_drops)

            if prominence_m < min_prominence_m:
                continue

            slope_coverage = sides_that_drop / len(side_drops)

            # Score favors prominence, true all-side falloff, and calm floor top.
            # The floor_relief penalty keeps sharp cones from winning too easily.
            score = (
                prominence_m * 1.00
                + mean_drop_m * 0.45
                + min_drop_m * 0.35
                + slope_coverage * 10.0
                - floor_relief_m * 2.0
            )

            raw_candidates.append({
                "lat": lat,
                "lon": lon,
                "elevation_m": center_elev,
                "surrounding_median_m": surrounding_median,
                "surrounding_mean_m": surrounding_mean,
                "prominence_m": prominence_m,
                "mean_drop_m": mean_drop_m,
                "min_drop_m": min_drop_m,
                "max_drop_m": max_drop_m,
                "floor_relief_m": floor_relief_m,
                "slope_coverage": slope_coverage,
                "side_angles": side_angles,
                "score": score,
                "search_offset_m": {
                    "north": north_m,
                    "east": east_m,
                },
            })

    raw_candidates.sort(key=lambda c: c["score"], reverse=True)

    # De-duplicate clusters so one mound does not return twenty nearly identical crowns.
    chosen = []

    def distance_m(a, b):
        avg_lat = math.radians((a["lat"] + b["lat"]) / 2.0)
        dn = (a["lat"] - b["lat"]) * 111320.0
        de = (a["lon"] - b["lon"]) * 111320.0 * math.cos(avg_lat)
        return math.hypot(dn, de)

    for candidate in raw_candidates:
        if all(distance_m(candidate, existing) >= cluster_radius_m for existing in chosen):
            chosen.append(candidate)

        if len(chosen) >= keep:
            break

    return chosen

def build_tile_index(folder="srtm"):

    for path in Path(folder).glob("*.tif"):
        with rasterio.open(path) as ds:
            bounds = ds.bounds  # (left, bottom, right, top)

        tiles.append({
            "path": path,
            "bounds": bounds
        })

    return tiles

def find_tile(lat, lon, tiles=tiles):
    if not tiles:
        tiles = build_tile_index()
    for tile in tiles:
        left, bottom, right, top = tile["bounds"]

        if left <= lon <= right and bottom <= lat <= top:
            return tile["path"]

    print(f"⚠️ No tile covers ({lat}, {lon})")
    return None

_tile_cache = {}

def load_tile(path):
    if path not in _tile_cache:
        _tile_cache[path] = rasterio.open(path)
    return _tile_cache[path]

def get_elevation_safe(lat, lon):
    global tiles
    if not tiles:
        tiles = build_tile_index()
    path = find_tile(lat, lon, tiles)
    if path is None:
        return None

    ds = load_tile(path)

    try:
        row, col = rowcol(ds.transform, lon, lat)
    except Exception:
        return None

    band = ds.read(1)

    if 0 <= row < band.shape[0] and 0 <= col < band.shape[1]:
        val = band[row, col]

        if ds.nodata is not None and val == ds.nodata:
            return None

        return float(val)

    return None

@lru_cache(maxsize=10000)
def topo(lat, lon):
    if USE_LOCAL:
        return topo_local(lat, lon)
    else:
        return topo_remote(lat, lon)

def topo_local(lat, lon):
    path = find_tile(lat, lon)
    if not path:
        return None

    ds = load_tile(path)
    
    for val in ds.sample([(lon, lat)]):
        return float(val[0])

def topo_remote(lat, lon):
    try:
        response = requests.get(
            SRTM_URL,
            json={"coords": f"{lat},{lon}"},
            timeout=2
        )
        
        if response.status_code != 200:
            return None
        
        data = response.json()  # parses JSON into dict :contentReference[oaicite:0]{index=0}
        
        if not data.get("ok", True):
            return None
        
        return data.get("elevation")
    
    except Exception:
        return None

def estimate_wind_exposure(horizon, direction):
    risk = get_horizon_interp(horizon, direction) < 2

def get_elevation(lat, lon):
    row, col = rowcol(transform, lon, lat)
    return band[row, col]

def get_elevation_peak(lat, lon, radius=5):
    base_row, base_col = rowcol(transform, lon, lat)
    
    max_elev = -999
    
    for r in range(-radius, radius+1):
        for c in range(-radius, radius+1):
            try:
                val = band[base_row + r, base_col + c]
                if val > max_elev:
                    max_elev = val
            except:
                pass
    
    return max_elev

def get_elevation_safe_old(lat, lon):

    if not (bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3]):
        return None  # outside dataset
    
    row, col = rowcol(transform, lon, lat)
    
    if 0 <= row < band.shape[0] and 0 <= col < band.shape[1]:
        return band[row][col]
    
    return None

def scan_vector(lat, lon, azimuth, radius=500, step=20):
    base_elev = topo(lat, lon)
    
    if base_elev is None:
        return None
    
    max_angle = -999
    
    for dist in range(step, radius, step):
        sample_lat = lat + (dist * math.cos(math.radians(azimuth))) / 111320
        sample_lon = lon + (dist * math.sin(math.radians(azimuth))) / (
            111320 * math.cos(math.radians(lat))
        )
        
        elev = topo(sample_lat, sample_lon)
        if elev is None:
            continue
        
        delta_elev = elev - base_elev
        elev_angle = math.degrees(math.atan2(delta_elev, dist))
        
        if elev_angle > max_angle:
            max_angle = elev_angle
    
    return max_angle

def scan_horizon(lat, lon, radius=500, steps=36):
    results = {}

    for angle in range(0, 360, int(360/steps)):
        max_angle = -999

        for dist in range(10, radius, 10):
            sample_lat = lat + (dist * math.cos(math.radians(angle))) / 111320
            sample_lon = lon + (dist * math.sin(math.radians(angle))) / (111320 * math.cos(math.radians(lat)))

            elev = topo(sample_lat, sample_lon)

            # compute elevation angle
            delta_elev = elev - topo(lat, lon)
            elev_angle = math.degrees(math.atan2(delta_elev, dist))

            max_angle = max(max_angle, elev_angle)

        results[angle] = max_angle

    return results

def extract_horizon_features(horizon):
    features = {}

    # Normalize horizon angles into 0–1 shade scale
    max_h = max(horizon.values())
    min_h = min(horizon.values())

    shade_map = {}
    for angle, val in horizon.items():
        norm = (val - min_h) / (max_h - min_h + 1e-6)
        shade_map[angle] = norm  # 0=open, 1=blocked

    # Valley detection (low-angle sectors)
    valley_dirs = [
        angle for angle, val in horizon.items()
        if val < (min_h + 0.25 * (max_h - min_h))
    ]

    # Ridge detection (high-angle sectors)
    ridge_dirs = [
        angle for angle, val in horizon.items()
        if val > (min_h + 0.75 * (max_h - min_h))
    ]

    # Exposure score (how open the sky is overall)
    exposure = 1 - (sum(shade_map.values()) / len(shade_map))

    # Edge detection (rapid changes in horizon)
    edge_score = 0
    angles = sorted(horizon.keys())

    for i in range(len(angles)):
        a1 = horizon[angles[i]]
        a2 = horizon[angles[(i + 1) % len(angles)]]
        edge_score += abs(a2 - a1)

    edge_score /= len(angles)

    features["shade_map"] = shade_map
    features["valleys"] = valley_dirs
    features["ridges"] = ridge_dirs
    features["exposure"] = exposure
    features["edge_score"] = edge_score

    return features

def full_signal(node):
    features = node.horizon_features
    gdd = node.gdd
    rain = node.recent_rain

    return forage_signals(features, gdd, rain)


def forage_signals(features, gdd):
    # TODO
    signals = []

    shade = 1 - features["exposure"]
    moisture = len(features["valleys"]) / 360
    edge = features["edge_score"]

    # 🌿 Salmonberry shoots
    if 100 <= gdd <= 300:
        score = 0.4 * moisture + 0.3 * edge + 0.3 * shade
        if score > 0.6:
            signals.append("🌿 Salmonberry shoots likely nearby")

    # 🍓 Berries
    if 800 <= gdd <= 1500:
        score = 0.5 * features["exposure"] + 0.3 * edge
        if score > 0.6:
            signals.append("🍓 Berry habitat active")

    # 🍄 Mushrooms (triggered by rain + cooldown)
    if gdd > 1200 and moisture > 0.5:
        signals.append("🍄 Mushroom conditions forming (watch for rain)")

    if gdd > 1200 and recent_rain > threshold:
        signal = "🍄 Flush likely in next 3–7 days"

    return signals

def estimate_sun_delay(horizon_angle_deg):
    return horizon_angle_deg * 4  # minutes (approx)

def classify_site(horizon):
    east = horizon.get(90, 0)
    south = horizon.get(180, 0)
    
    if east > 10:
        return "Late Sunrise Site"
    elif south < 2:
        return "Solar Optimized Site"
    elif east < 3 and south < 3:
        return "Full Exposure Site"
    else:
        return "Balanced Site"

def get_horizon_angle(horizon, azimuth):
    nearest = min(horizon.keys(), key=lambda k: abs(k - azimuth))
    return horizon[nearest]

def get_horizon_interp(horizon, azimuth):
    keys = sorted(horizon.keys())
    
    for i in range(len(keys)):
        k1 = keys[i]
        k2 = keys[(i + 1) % len(keys)]
        
        if k1 <= azimuth <= k2:
            t = (azimuth - k1) / (k2 - k1)
            return horizon[k1] * (1 - t) + horizon[k2] * t
    
    return horizon[keys[0]]

def estimate_sun_hours(site, date, horizon, step_minutes=10, min_alt=5):
    from datetime import timedelta
    
    total_minutes = 0
    
    t = date.replace(hour=0, minute=0, second=0)
    end = t + timedelta(days=1)
    
    while t < end:
        solar = site.observe(t)
        
        az = solar["azimuth"]
        alt = solar["elevation"]
        
        if alt > 0:  # sun is above astronomical horizon
            
            terrain_alt = get_horizon_interp(horizon, az)
            
            # 🌞 sun must clear terrain AND be strong enough
            if alt > terrain_alt and alt > min_alt:
                total_minutes += step_minutes
        
        t += timedelta(minutes=step_minutes)
    
    return total_minutes / 60  # hours


def estimate_slope(lat, lon):
    # ~30 meters in degrees
    d_lat = 30 / 111000  
    
    # adjust longitude step by latitude
    d_lon = 30 / (111000 * math.cos(math.radians(lat)))
    
    dzdx = topo(lat, lon + d_lon) - topo(lat, lon - d_lon)
    dzdy = topo(lat + d_lat, lon) - topo(lat - d_lat, lon)
    
    # slope magnitude
    slope = math.sqrt(dzdx**2 + dzdy**2)
    
    # direction slope is facing (aspect)
    aspect = math.degrees(math.atan2(dzdx, dzdy))
    
    return slope, aspect