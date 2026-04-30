"""
Aether-backed seasonal and solar-geometry helpers (North hemisphere by default).

This module replaces Skyfield-heavy routines in `threshing_floor.py` with
computations driven by the internal AetherField model. It provides:

- solar_declination(dt): declination in degrees from AetherField solar longitude
- sunrise_azimuth(date, lat, lon, tz, depression_deg): azimuth at sunrise
- determine_solar_movement(yesterday_az, today_az): North/South/Stationary
- current_season(dt, hemisphere='N'): season name from solar longitude
- season_boundaries(year, tz, hemisphere='N'): equinox/solstice datetimes
- season_start_for(dt, tz, hemisphere='N'): the most recent boundary before dt

Conventions
- Azimuth is returned in degrees from North, increasing clockwise (0..360).
- Sunrise/sunset depression angle default is -0.833 deg (standard apparent).
- Seasons use astronomical definitions by solar ecliptic longitude λ:
  λ ∈ [0,90) Spring, [90,180) Summer, [180,270) Autumn, [270,360) Winter (North).
  For Southern hemisphere, Spring↔Autumn and Summer↔Winter are swapped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import numpy as np

import math
import pytz

try:
    # Root-level shim that re-exports from aetherfield_pkg.core
    from aetherfield import (
        AetherField,
        aether_longitude,
        ecliptic_to_equatorial,
        OBLIQUITY_DEG,
        sunrise_sunset,
        ae_is_up as _ae_is_up,
        get_zodiac_by_longitude_dt,
        rotated_zodiac,
        get_age_sign
    )
except Exception as exc:  # pragma: no cover - environment fallback
    raise RuntimeError("aetherfield module not available.") from exc


# ---------------- Solar basics ----------------

def julian_day(dt):
    """Convert datetime (UTC) → Julian Day"""
    year = dt.year
    month = dt.month
    day = dt.day + (
        dt.hour +
        dt.minute / 60 +
        dt.second / 3600
    ) / 24

    if month <= 2:
        year -= 1
        month += 12

    A = year // 100
    B = 2 - A + A // 4

    JD = int(365.25 * (year + 4716)) \
       + int(30.6001 * (month + 1)) \
       + day + B - 1524.5

    return JD

def get_zodiac_phase(longitude: float, dt: datetime):
    #dt = _as_datetime(dt)
    year = dt.year

    raw_index = longitude / 30.0
    i = int(raw_index) % 12
    frac = raw_index % 1.0  # 👈 THIS is the smooth part

    return {
        "index": i,
        "phase": frac  # 0.0 → 1.0 within the sign
    }

def tf_as_above_zodiac(dt, coords):
    lat, lon = coords

    # 1. Get local sidereal time (degrees)
    lst = local_sidereal_time(dt, lon)

    # 2. Midheaven approximation (ecliptic longitude at meridian)
    # (simple version: treat RA ≈ ecliptic longitude)
    mid_lon = lst % 360
    midsign = get_zodiac_by_longitude_dt(mid_lon, dt)
    #print("midsign:", midsign)
    # 3. Define arc (180° centered on mid_lon)
    start = (mid_lon + 90) % 360

    signs = []
    seen = set()


    for i in range(6):
        lon_i = (start - i * 30) % 360
        sign = get_zodiac_by_longitude_dt(lon_i, dt)
        phase_data = get_zodiac_phase(lon_i, dt)

        if sign not in seen:
            signs.append({
                "sign": sign,
                "center_lon": lon_i,
                "phase": phase_data["phase"]
            })
            seen.add(sign)

    return signs

def tf_so_below_zodiac(dt, coords):
    lat, lon = coords

    lst = local_sidereal_time(dt, lon)
    mid_lon = lst % 360

    # Opposite side of the sky
    mid_lon_below = (mid_lon + 180) % 360

    start = (mid_lon_below + 90) % 360

    signs = []
    seen = set()

    for i in range(6):
        lon_i = (start - i * 30) % 360
        sign = get_zodiac_by_longitude_dt(lon_i, dt)
        phase_data = get_zodiac_phase(lon_i, dt)

        if sign not in seen:
            signs.append({
                "sign": sign,
                "center_lon": lon_i,
                "phase": phase_data["phase"]

            })
            seen.add(sign)

    return signs

def local_sidereal_time(dt, lon_deg):
    """
    Returns Local Sidereal Time in degrees [0, 360)
    lon_deg: east positive
    """
    dt_utc = dt.astimezone(pytz.utc)
    JD = julian_day(dt_utc)
    T = (JD - 2451545.0) / 36525.0

    # Greenwich Mean Sidereal Time (degrees)
    GMST = (
        280.46061837
        + 360.98564736629 * (JD - 2451545.0)
        + 0.000387933 * T**2
        - (T**3) / 38710000.0
    )

    GMST = GMST % 360.0

    # Local Sidereal Time
    LST = (GMST + lon_deg) % 360.0

    return LST

def obliquity_deg(dt):
    """
    Approximate mean obliquity of the ecliptic (arcseconds → degrees)
    Good to ~0.01° over a few centuries.
    """
    T = (dt.year - 2000) / 100.0  # centuries since J2000

    eps_arcsec = (
        84381.406
        - 46.836769 * T
        - 0.0001831 * T**2
        + 0.00200340 * T**3
    )

    return eps_arcsec / 3600.0

def equatorial_to_horizontal(ra_deg, dec_deg, dt, lat_deg, lon_deg):
    lst = local_sidereal_time(dt, lon_deg)  # degrees

    ha = (lst - ra_deg) % 360.0

    ha_rad  = math.radians(ha)
    dec_rad = math.radians(dec_deg)
    lat_rad = math.radians(lat_deg)

    sin_alt = (
        math.sin(dec_rad)*math.sin(lat_rad) +
        math.cos(dec_rad)*math.cos(lat_rad)*math.cos(ha_rad)
    )
    alt = math.degrees(math.asin(sin_alt))

    y = -math.sin(ha_rad)
    x = (
        math.tan(dec_rad)*math.cos(lat_rad) -
        math.sin(lat_rad)*math.cos(ha_rad)
    )

    az = math.degrees(math.atan2(y, x)) % 360.0

    return alt, az

def bennett_refraction(alt_deg, pressure=1013.25, temperature=10.0):
    alt = np.maximum(alt_deg, -1.0)  # clamp near horizon

    R = 1.02 / np.tan(np.radians(alt + 10.3 / (alt + 5.11)))
    R *= (pressure / 1010.0) * (283.0 / (273.0 + temperature))

    return R  # arcminutes

def solar_horizontal_at(dt, lat, lon, af=None):
    if not af:
        af = AetherField.load_calibration('AetherField')
    lon_ecl = af.longitude(dt=dt, body="sun")
    eps = obliquity_deg(dt)

    ra, dec = ecliptic_to_equatorial(lon_ecl, 0.0, eps)
    alt, az = equatorial_to_horizontal(ra, dec, dt, lat, lon)

    # apply Bennett refraction
    R_arcmin = bennett_refraction(alt)
    alt_apparent = alt + (R_arcmin / 60.0)

    return {
        "alt_true": alt,
        "alt_apparent": alt_apparent,
        "azimuth": az
    }

def solar_declination(dt: datetime) -> float:
    """Compute solar declination (deg) from AetherField solar longitude.

    dt may be naive (interpreted as UTC) or timezone-aware.
    """
    lam = aether_longitude(dt, "sun")
    _, dec = ecliptic_to_equatorial(lam, 0.0, OBLIQUITY_DEG)
    return float(dec)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def sunrise_azimuth(
    date: datetime,
    latitude: float,
    longitude: float,
    tz: Optional[pytz.BaseTzInfo | str] = "UTC",
    depression_deg: float = -0.833,
) -> Optional[float]:
    """Approximate sunrise azimuth in degrees (0=N, clockwise), or None in polar day/night.

    Uses a closed-form horizon geometry at apparent sunrise altitude h0. This
    does not require the actual sunrise instant; it depends on latitude and
    solar declination on that date. The result closely matches full ephemeris
    models for typical latitudes.
    """
    # Normalize tz
    if isinstance(tz, str):
        tz = pytz.timezone(tz)

    # Use local solar noon declination for the date (adequate for azimuth).
    local_noon = tz.localize(datetime(date.year, date.month, date.day, 12, 0, 0))
    dec = solar_declination(local_noon)

    phi = math.radians(float(latitude))
    h0 = math.radians(depression_deg)
    sd = math.sin(math.radians(dec))
    cd = math.cos(math.radians(dec))

    denom = math.cos(phi) * math.cos(h0)
    if abs(denom) < 1e-12:
        return None

    cosA = (math.sin(h0) - math.sin(phi) * sd) / denom
    if cosA > 1.0 or cosA < -1.0:
        # Polar day/night (no sunrise or no sunset)
        return None

    A = math.degrees(math.acos(_clamp(cosA, -1.0, 1.0)))  # angle from North, eastward
    return float(A)


def sunrise_azimuth_for_declination(
    latitude: float,
    dec_deg: float,
    depression_deg: float = -0.833,
) -> Optional[float]:
    """Closed-form sunrise azimuth for a given latitude and solar declination.

    Returns degrees from North clockwise, or None in polar day/night conditions.
    """
    phi = math.radians(float(latitude))
    h0 = math.radians(depression_deg)
    sd = math.sin(math.radians(dec_deg))
    cd = math.cos(math.radians(dec_deg))
    denom = math.cos(phi) * math.cos(h0)
    if abs(denom) < 1e-12:
        return None
    cosA = (math.sin(h0) - math.sin(phi) * sd) / denom
    if cosA > 1.0 or cosA < -1.0:
        return None
    return float(math.degrees(math.acos(_clamp(cosA, -1.0, 1.0))))


def determine_solar_movement(yesterday_az: float, today_az: float) -> str:
    """Return 'North', 'South', or 'Stationary' by comparing sunrise azimuths."""
    delta = (today_az - yesterday_az + 180) % 360 - 180
    if delta > 0:
        return "North"
    elif delta < 0:
        return "South"
    return "Stationary"

# ---------------- Rise/set + temporal (general bodies) ----------------

def _body_altitude(dt: datetime, coords: str, body: str) -> Optional[float]:
    try:
        up, info = _ae_is_up(dt, body=body, coords=coords, method='full')
        return info.get('alt_deg')
    except Exception:
        return None


def _bisect_altitude_zero(t0: datetime, t1: datetime, coords: str, body: str, max_iter: int = 30, tol_sec: float = 1.0) -> Optional[datetime]:
    a0 = _body_altitude(t0, coords, body)
    a1 = _body_altitude(t1, coords, body)
    if a0 is None or a1 is None:
        return None
    if a0 == 0:
        return t0
    if a1 == 0:
        return t1
    if a0 * a1 > 0:
        return None
    a, b = t0, t1
    fa, fb = a0, a1
    for _ in range(max_iter):
        mid = a + (b - a) / 2
        fm = _body_altitude(mid, coords, body)
        if fm is None:
            break
        if abs((b - a).total_seconds()) <= tol_sec:
            return mid
        if fa * fm <= 0:
            b, fb = mid, fm
        else:
            a, fa = mid, fm
    return a + (b - a) / 2


def body_crossings_around(dt: datetime, tz, coords: str, body: str, search_hours: int = 36) -> Tuple[Optional[datetime], Optional[datetime], Optional[str], Optional[str], Optional[bool]]:
    """Find previous and next altitude=0 crossings (rise/set) of `body` around dt.

    Returns (prev_time, next_time, prev_type, next_type, is_up_now)
    where types are 'rise' or 'set'.
    """
    d = dt if dt.tzinfo else tz.localize(dt)
    # Current altitude and up/down
    try:
        up_now, info = _ae_is_up(d, body=body, coords=coords, method='full')
        alt_now = info.get('alt_deg')
    except Exception:
        return None, None, None, None, None

    # Scan backward hourly to bracket previous crossing
    step = timedelta(hours=1)
    t_left = d
    alt_left = alt_now
    prev_time = None
    prev_type = None
    for i in range(max(1, int(search_hours))):
        t2 = t_left - step
        alt2 = _body_altitude(t2, coords, body)
        if alt2 is None:
            break
        if alt_left == 0 or alt2 == 0 or (alt_left > 0 and alt2 < 0) or (alt_left < 0 and alt2 > 0):
            # refine between t2..t_left
            zt = _bisect_altitude_zero(t2, t_left, coords, body)
            prev_time = zt or t2
            prev_type = 'rise' if (alt2 < 0 and alt_left > 0) else ('set' if (alt2 > 0 and alt_left < 0) else ('rise' if alt2 <= 0 else 'set'))
            break
        t_left, alt_left = t2, alt2

    # Scan forward hourly to bracket next crossing
    t_right = d
    alt_right = alt_now
    next_time = None
    next_type = None
    for i in range(max(1, int(search_hours))):
        t2 = t_right + step
        alt2 = _body_altitude(t2, coords, body)
        if alt2 is None:
            break
        if alt_right == 0 or alt2 == 0 or (alt_right > 0 and alt2 < 0) or (alt_right < 0 and alt2 > 0):
            zt = _bisect_altitude_zero(t_right, t2, coords, body)
            next_time = zt or t2
            next_type = 'rise' if (alt_right < 0 and alt2 > 0) else ('set' if (alt_right > 0 and alt2 < 0) else ('rise' if alt_right <= 0 else 'set'))
            break
        t_right, alt_right = t2, alt2

    return prev_time, next_time, prev_type, next_type, bool(up_now)


def planetary_temporal(dt: datetime, tz, coords: str, body: str) -> Dict[str, Optional[object]]:
    """Generic temporal time for a planet-like body (Sun, Moon, Mercury..Saturn).

    Splits the current up or down interval (rise→set or set→rise) into 12 equal hours.
    """
    d = dt if dt.tzinfo else tz.localize(dt)
    prev_t, next_t, prev_type, next_type, is_up_now = body_crossings_around(d, tz, coords, body)
    if prev_t is None or next_t is None or is_up_now is None:
        return {
            'is_up': None, 'start': None, 'end': None,
            'hour_length_seconds': None, 'hour_index': None,
            'minute_index': None, 'second_index': None,
        }
    if is_up_now:
        start = prev_t
        end = next_t
    else:
        start = prev_t
        end = next_t

    span = max(1e-9, (end - start).total_seconds())
    hour_len = span / 12.0
    elapsed = (d - start).total_seconds()
    elapsed = max(0.0, min(span, elapsed))
    h_idx = int(elapsed // hour_len) + 1
    if h_idx > 12:
        h_idx = 12
    within_h = elapsed - (h_idx - 1) * hour_len
    min_len = hour_len / 60.0
    m_idx = int(within_h // min_len) + 1
    if m_idx > 60:
        m_idx = 60
    within_m = within_h - (m_idx - 1) * min_len
    sec_len = min_len / 60.0
    s_idx = int(within_m // sec_len) + 1
    if s_idx > 60:
        s_idx = 60

    return {
        'is_up': bool(is_up_now),
        'start': start,
        'end': end,
        'hour_length_seconds': hour_len,
        'hour_index': h_idx,
        'minute_index': m_idx,
        'second_index': s_idx,
    }


# ---------------- Lunar wrappers ----------------

def moon_crossings_around(dt: datetime, tz, coords: str, search_hours: int = 36):
    return body_crossings_around(dt, tz, coords, body='moon', search_hours=search_hours)


def lunar_temporal(dt: datetime, tz, coords: str) -> Dict[str, Optional[object]]:
    return planetary_temporal(dt, tz, coords, body='moon')


# ---------------- Seasons ----------------

def _angdiff_deg(a: float, b: float) -> float:
    """Signed smallest difference a-b in (-180, +180] degrees."""
    return ((a - b + 180.0) % 360.0) - 180.0


def _season_name_from_lon(lon: float, hemisphere: str = "N") -> str:
    lon = lon % 360.0
    if hemisphere.upper().startswith("S"):
        # Swap seasons for Southern hemisphere
        if 0 <= lon < 90:
            return "Autumn"
        if 90 <= lon < 180:
            return "Winter"
        if 180 <= lon < 270:
            return "Spring"
        return "Summer"
    else:
        if 0 <= lon < 90:
            return "Spring"
        if 90 <= lon < 180:
            return "Summer"
        if 180 <= lon < 270:
            return "Autumn"
        return "Winter"


def current_season(dt: datetime, hemisphere: str = "N") -> str:
    """Season name (Spring, Summer, Autumn, Winter) for dt.

    North hemisphere by default; pass hemisphere='S' to invert.
    """
    lon = aether_longitude(dt, "sun")
    return _season_name_from_lon(lon, hemisphere)


def _bisection_for_longitude(
    target_deg: float,
    t0: datetime,
    t1: datetime,
    max_iter: int = 40,
    tol_sec: float = 1.0,
) -> Optional[datetime]:
    """Find t in [t0,t1] such that solar longitude crosses target_deg.

    Uses sign of wrapped angular difference and simple bisection.
    Returns None if no crossing is bracketed.
    """
    f0 = _angdiff_deg(aether_longitude(t0, "sun"), target_deg)
    f1 = _angdiff_deg(aether_longitude(t1, "sun"), target_deg)
    if f0 == 0:
        return t0
    if f1 == 0:
        return t1
    if f0 * f1 > 0:
        return None
    a, b = t0, t1
    fa, fb = f0, f1
    for _ in range(max_iter):
        mid = a + (b - a) / 2
        fm = _angdiff_deg(aether_longitude(mid, "sun"), target_deg)
        if abs((b - a).total_seconds()) <= tol_sec:
            return mid
        if fa * fm <= 0:
            b, fb = mid, fm
        else:
            a, fa = mid, fm
    return a + (b - a) / 2


def _approx_boundary_guess(year: int, quarter: int, tz: pytz.BaseTzInfo) -> datetime:
    # quarter: 0->Mar eqx, 1->Jun sol, 2->Sep eqx, 3->Dec sol
    if quarter == 0:
        m, d = 3, 20
    elif quarter == 1:
        m, d = 6, 21
    elif quarter == 2:
        m, d = 9, 22
    else:
        m, d = 12, 21
    return tz.localize(datetime(year, m, d, 12, 0, 0))


def season_boundaries(
    year: int,
    tz: Optional[pytz.BaseTzInfo | str] = "UTC",
    hemisphere: str = "N",
) -> Dict[str, datetime]:
    """Return approximate equinox/solstice datetimes for a year (tz-aware).

    Keys (North): 'spring_equinox', 'summer_solstice', 'autumn_equinox', 'winter_solstice'.
    Southern hemisphere returns the same keys; interpretation of seasons is inverted by consumer.
    """
    if isinstance(tz, str):
        tz = pytz.timezone(tz)
    # Targets in ecliptic longitude
    targets = [0.0, 90.0, 180.0, 270.0]
    names = [
        "spring_equinox",
        "summer_solstice",
        "autumn_equinox",
        "winter_solstice",
    ]
    out: Dict[str, datetime] = {}
    for q, (name, target) in enumerate(zip(names, targets)):
        guess = _approx_boundary_guess(year, q, tz)
        # Try to bracket within ±14 days; expand if needed
        span = 14
        when = None
        for span in (14, 28, 56):
            t0 = guess - timedelta(days=span)
            t1 = guess + timedelta(days=span)
            when = _bisection_for_longitude(target, t0, t1)
            if when is not None:
                break
        if when is None:
            # Fallback to guess if bisection failed (should be rare)
            when = guess
        out[name] = when
    return out


def season_start_for(
    dt: datetime,
    tz: Optional[pytz.BaseTzInfo | str] = "UTC",
    hemisphere: str = "N",
) -> Tuple[str, datetime]:
    """Return (season_name, season_start_dt) for the moment dt.

    Finds the most recent boundary at λ = 0, 90, 180, 270 degrees.
    """
    if isinstance(tz, str):
        tz = pytz.timezone(tz)
    cur_season = current_season(dt, hemisphere=hemisphere)
    year = dt.year
    # Build boundaries for current and previous year
    b0 = season_boundaries(year - 1, tz, hemisphere)
    b1 = season_boundaries(year, tz, hemisphere)
    candidates = [
        b0["spring_equinox"], b0["summer_solstice"], b0["autumn_equinox"], b0["winter_solstice"],
        b1["spring_equinox"], b1["summer_solstice"], b1["autumn_equinox"], b1["winter_solstice"],
    ]
    candidates = [c for c in candidates if c <= dt]
    if not candidates:
        # If all in future (rare at year start), fallback to earliest boundary in previous year
        prev_first = season_boundaries(year - 1, tz, hemisphere)["winter_solstice"]
        return cur_season, prev_first
    start_dt = max(candidates)
    return cur_season, start_dt


# If run directly, print a quick seasonal summary for now
if __name__ == "__main__":
    import sys
    tz = pytz.timezone("UTC")
    now = tz.localize(datetime.utcnow())
    lat = float(os.getenv("THRESH_LAT", "37.7749")) if 'os' in globals() else 0.0
    lon = float(os.getenv("THRESH_LON", "-122.4194")) if 'os' in globals() else 0.0
    dec = solar_declination(now)
    az = sunrise_azimuth(now, lat, lon, tz)
    season = current_season(now, 'N')
    _, start = season_start_for(now, tz, 'N')
    print(f"Now: {now.isoformat()}  decl={dec:.3f}°  sunrise_az={az if az is not None else 'n/a'}  season={season} since {start.isoformat()}")

    coords = lat, lon
    print(tf_as_above_zodiac(now, coords))
    print(tf_so_below_zodiac(now, coords))
