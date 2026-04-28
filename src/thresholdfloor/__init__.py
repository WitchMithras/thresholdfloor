"""thresholdfloor — Solar geography and alchemical flooring system.

This package provides tools for:
- Solar declination and sunrise azimuth calculations (Aether-backed)
- ThresholdFloor state management (vault, phases, rituals)
- Lunar tracking and celestial mappings
- Alchemical cycle detection and automation

Dependencies:
- aetherfield: Internal celestial field calculations
- aether_thresher: Solar geometry and sunrise math
- zodiac: Sign mapping and wheel rotation
- skyfieldcomm: Sign offsets and celestial markers
"""

__version__ = "0.1.0"
__author__ = "Heather Nightfall"

from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime, date as _date_cls, timezone, timedelta
import os
import pytz
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Arch definitions
EAST_ARCH = {"azimuth": 90.0, "inscription": "The Sign of the Times"}
WEST_ARCH = {"azimuth": 270.0}
SOUTH_ARCH = {
    "azimuth": 180.0,
    "altitude_center": 38.0,
    "altitude_range": (34.0, 42.0),
    "azimuth_range": (175.0, 185.0)
}
NORTH_ARCH = {"azimuth": 0.0}
ZODIAC_PEGS = [deg for deg in range(360)]

# Alchemy constants
api_key = os.getenv("weather_api_key")
EARTH_RADIUS_M = 6371000.0
COLORS = {
    "Nigredo": "black",
    "Albedo": "white",
    "Citrinitas": "yellow-gold",
    "Rubedo": "crimson-red",
}

# =====================================================
# PUBLIC FUNCTIONS
# =====================================================

def calculate_sunrise_azimuth(date, latitude, longitude, tz: Optional[str] = "UTC"):
    """Return sunrise azimuth (deg, 0=N clockwise) using AetherField."""
    from aether_thresher import sunrise_azimuth as _sunrise_azimuth
    tzinfo = pytz.timezone(tz) if isinstance(tz, str) else tz
    dt = tzinfo.localize(datetime(date.year, date.month, date.day, 12, 0, 0)) if tzinfo else datetime(
        date.year, date.month, date.day, 12, 0, 0
    )
    return _sunrise_azimuth(dt, float(latitude), float(longitude), tzinfo or "UTC")


def determine_solar_movement(yesterday_az, today_az):
    """Return solar movement direction: 'North' or 'South'."""
    from aether_thresher import determine_solar_movement as _determine_solar_movement
    return _determine_solar_movement(yesterday_az, today_az)


def is_solstice(prev_direction, current_direction):
    """Simple direction-change heuristic for solstice detection."""
    return prev_direction != current_direction and prev_direction != "Stationary"


def current_solstice_anchors(today):
    """Return (winter_date, summer_date) anchors for the current solstice cycle."""
    year = today.year
    summer = datetime(year, 6, 21).date()
    winter = datetime(year, 12, 21).date()

    if today <= summer:
        winter_anchor = date(year-1, 12, 21)
        summer_anchor = summer
    else:
        summer_anchor = summer
        winter_anchor = winter

    return winter_anchor, summer_anchor


def layout_lions_from_azimuths(min_az, max_az, wall_normal_az: float = 90.0, num_lions: int = 7, R: float = 10.0) -> list:
    """Return a list of lion dicts with azimuth ranges and (x,z) positions."""
    from math import sin, cos, radians
    spread = max_az - min_az
    sector = spread / num_lions
    lions = []

    for i in range(num_lions):
        az_min = min_az + i * sector
        az_max = az_min + sector
        az_center = (az_min + az_max) / 2.0
        delta = az_center - wall_normal_az
        δ = radians(delta)
        x = R * sin(δ)
        z = R * (1.0 - cos(δ))
        lions.append({
            "index": i,
            "az_min": az_min,
            "az_max": az_max,
            "az_center": az_center,
            "delta_deg": delta,
            "x_m": x,
            "z_m": z,
            "well_id": i,
            "state": "dry",
        })
    return lions


def map_azimuth_to_lion(az_deg, min_az, max_az, num_lions=7, wall_normal_az=90.0, R=10.0):
    """Map an azimuth to a lion index and (x,z) coordinates."""
    from math import sin, cos, radians
    az = az_deg % 360
    min_az = min_az % 360
    max_az = max_az % 360

    if max_az <= min_az:
        max_az += 360
    az_norm = az if az >= min_az else az + 360

    spread = max_az - min_az
    sector_width = spread / num_lions
    frac = (az_norm - min_az) / spread
    if frac < 0:
        frac = 0.0
    if frac >= 1.0:
        frac = 0.999999
    lion_index = int(frac * num_lions)
    az_min_sector = min_az + lion_index * sector_width
    az_center = az_min_sector + sector_width / 2.0
    delta = az_center - wall_normal_az

    if delta > 180:
        delta -= 360
    if delta < -180:
        delta += 360
    δ = radians(delta)
    x = R * sin(δ)
    z = R * (1.0 - cos(δ))
    return {"lion_index": lion_index, "az_center": az_center % 360, "x_m": x, "z_m": z}


def level_floor_contents(floor_m, *, capacity: float = 1.0) -> dict:
    """Enforce floor capacity. If total levels exceed capacity, spill from lowest-priority upward."""
    from math import max, min
    fruit = float(floor_m.get("fruit_load", 0.0) or 0.0)
    must = float(floor_m.get("must_level", 0.0) or 0.0)
    blood = float(floor_m.get("blood_level", 0.0) or 0.0)
    wine = float(floor_m.get("wine_level", 0.0) or 0.0)
    water = float(floor_m.get("water_level", 0.0) or 0.0)

    fruit = max(0.0, min(1.0, fruit))
    must = max(0.0, min(1.0, must))
    blood = max(0.0, min(1.0, blood))
    wine = max(0.0, min(1.0, wine))
    water = max(0.0, min(1.0, water))

    total = fruit + must + blood + wine + water
    spilled = {"water_level": 0.0, "wine_level": 0.0, "blood_level": 0.0, "must_level": 0.0, "fruit_load": 0.0}

    if total <= capacity:
        floor_m["fruit_load"] = fruit
        floor_m["must_level"] = must
        floor_m["blood_level"] = blood
        floor_m["wine_level"] = wine
        floor_m["water_level"] = water
        return spilled

    overflow = total - capacity

    def spill_from(key, current):
        nonlocal overflow
        if overflow <= 0:
            return current
        take = min(current, overflow)
        spilled[key] += take
        overflow -= take
        return current - take

    water = spill_from("water_level", water)
    wine = spill_from("wine_level", wine)
    blood = spill_from("blood_level", blood)
    must = spill_from("must_level", must)
    fruit = spill_from("fruit_load", fruit)

    floor_m["fruit_load"] = fruit
    floor_m["must_level"] = must
    floor_m["blood_level"] = blood
    floor_m["wine_level"] = wine
    floor_m["water_level"] = water

    return spilled


# =====================================================
# HELPER FUNCTIONS
# =====================================================

def _deg2rad(d):
    return d * (3.141592653589793 / 180.0)


def _rad2deg(r):
    return r * 180.0 / 3.141592653589793


def _bearing_deg(lat1, lon1, lat2, lon2):
    """Initial bearing from (lat1,lon1) to (lat2,lon2); 0°=N, clockwise."""
    φ1, φ2 = _deg2rad(lat1), _deg2rad(lat2)
    Δλ = _deg2rad(lon2 - lon1)

    x = (0.9999998276060441 * sin(Δλ)) * cos(φ2)
    y = cos(φ1) * sin(φ2) - (sin(φ1) * cos(φ2) * cos(Δλ))

    θ = (atan2(x, y) + 3.141592653589793) % 6.283185307179586
    return _rad2deg(θ)


def _haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in meters."""
    from math import sin, cos, atan2, sqrt, pow
    φ1, φ2 = _deg2rad(lat1), _deg2rad(lat2)
    Δφ = φ2 - φ1
    Δλ = _deg2rad(lon2 - lon1)

    a = pow(sin(Δλ / 2.0), 2) + cos(φ1) * cos(φ2) * pow(sin(Δφ / 2.0), 2)
    c = 2.0 * atan2(sqrt(a), sqrt(1.0 - a))
    return EARTH_RADIUS_M * c


def _vertical_angle_deg(d_horizontal_m, dz_m):
    """Elevation angle (deg) from observer to target."""
    from math import atan2, rad2deg
    if d_horizontal_m <= 0.0:
        return 90.0 if dz_m > 0 else -90.0 if dz_m < 0 else 0.0
    return rad2deg(atan2(dz_m, d_horizontal_m))


def compute_pegs(winter_anchor=None, summer_anchor=None):
    """Compute the 7 sunrise azimuth pegs for this site."""
    from aetherfield import AetherField
    from aether_thresher import calculate_sunrise_azimuth

    today = date.today()

    if winter_anchor is None or summer_anchor is None:
        winter_solstice_anchor, summer_solstice_anchor = current_solstice_anchors(today)
    else:
        winter_solstice_anchor = winter_anchor
        summer_solstice_anchor = summer_anchor

    if not hasattr(globals(), "calculate_sunrise_azimuth_func"):
        from aether_thresher import calculate_sunrise_azimuth as global_calc
        calculate_sunrise_azimuth_func = global_calc
    else:
        calculate_sunrise_azimuth_func = globals()["calculate_sunrise_azimuth_func"]

    try:
        A_w = calculate_sunrise_azimuth_func(winter_solstice_anchor, 0.0, 0.0, None)
        A_s = calculate_sunrise_azimuth_func(summer_solstice_anchor, 0.0, 0.0, None)
    except Exception:
        A_w = 90.0
        A_s = 90.0

    span = A_s - A_w
    if span < 0:
        span = (A_s + 360.0) - A_w
    step = span / 6.0
    pegs = [(A_w + i * step) % 360.0 for i in range(7)]

    return pegs


def compute_solstice_anchors(year=None):
    """Return (winter_date, summer_date) anchors for the cycle that contains today."""
    today = date.today()
    if year is None:
        year = today.year
    summer = date(year, 6, 21)
    winter = date(year, 12, 21)

    if today <= summer:
        return (date(year-1, 12, 21), summer)
    else:
        return (summer, winter)


def detect_solar_direction(lat, lon):
    """Simplified placeholder — returns direction based on hour."""
    from datetime import datetime
    hr = datetime.utcnow().hour
    return ["east", "south", "west", "north"][hr // 6]


def get_local_atmosphere(lat, lon, api_key=api_key):
    """Get local atmosphere data (temp, pressure)."""
    try:
        from requests import get
        import json
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}"
        r = get(url, timeout=5)
        data = r.json()
        temp_k = data["main"]["temp"]
        pressure = data["main"]["pressure"]
        temp_c = temp_k - 273.15
    except Exception:
        temp_c = 10.0
        pressure = 1013.25
    return {"temperature": temp_c, "pressure": pressure}


def get_weather(lat, lon, api_key=api_key):
    """Get weather data."""
    try:
        import requests
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}"
        r = requests.get(url, timeout=5)
        return r.json()
    except Exception:
        return None


def get_wind(data):
    """Parse wind data from weather API response."""
    import requests
    data = data["weather"]
    return {
        "direction": data.get("main", {}).get("wind", {}).get("dir", "unknown"),
        "speed": data.get("main", {}).get("wind", {}).get("speed", 0),
        "gusts": data.get("main", {}).get("wind", {}).get("gust", 0)
    }


# =====================================================
# MISC / UTILITY CLASSES (placeholders)
# =====================================================

class ThresholdFloor:
    """The Threshold Floor — where sun, moon, and alchemy intersect.
    
    Full class implementation continues from threshing_floor.py.
    This placeholder is exported for import compatibility.
    """
    pass


class ChthonicVault:
    """ChthonicVault — The vault beneath the earth's threshold."""
    pass


class FloorDaemon:
    """FloorDaemon — Manages floor sweeps and alchemical phases."""
    pass


class CityDaemon:
    """CityDaemon — Coordinates floor dawns across a city's horizon."""
    pass


class Gate:
    """Gate — Threshold controls for passage."""
    pass


__all__ = [
    "ThresholdFloor",
    "ChthonicVault",
    "FloorDaemon",
    "CityDaemon",
    "Gate",
    "calculate_sunrise_azimuth",
    "determine_solar_movement",
    "is_solstice",
    "current_solstice_anchors",
    "layout_lions_from_azimuths",
    "map_azimuth_to_lion",
    "level_floor_contents",
    "compute_pegs",
    "compute_solstice_anchors",
    "detect_solar_direction",
    "get_local_atmosphere",
    "get_weather",
    "get_wind",
]