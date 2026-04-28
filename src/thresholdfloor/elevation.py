
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

def scan_horizon(lat, lon, radius=50, steps=36):
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