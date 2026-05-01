"""threshold_floor — Full ThresholdFloor class implementation.

This module contains the complete ThresholdFloor class with all methods
for solar geometry, alchemical phases, vault state, and ritual automation.

See also:
- __init__.py for public functions and utilities
"""

from __future__ import annotations

from typing import Optional, Tuple, List, Dict, Any, Callable
from datetime import datetime, date as _date_cls, timezone, timedelta
import os
import pytz
import math
import json

from dotenv import load_dotenv

from aetherfield import AetherField
from .aether_thresher import (
    solar_declination as _solar_declination,
    sunrise_azimuth as _sunrise_azimuth,
    determine_solar_movement as _determine_solar_movement,
    solar_horizontal_at as _solar_horizontal_at,
    tf_as_above_zodiac, tf_so_below_zodiac,
)
#from tarot import narrate_seed_reading # Future update

from .elevation import topo, scan_vector, get_horizon_interp, scan_horizon, estimate_sun_delay
from .floor_sigil import tf_sigil, show_sigil

load_dotenv()

WEATHER_EXISTS = False

try:
    api_key = os.getenv("weather_api_key")
    WEATHER_EXISTS = True
except Exception:
    pass

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

# Alchemy constants
ALCHEMY_PHASES = ["Nigredo", "Albedo", "Citrinitas", "Rubedo"]
FIELD_JOBS = {
    "Nigredo": "return, rest, let decay, settle",
    "Albedo": "plow, sow, cleanse, sweep, purify water channels",
    "Citrinitas": "tend, build, illuminate, water",
    "Rubedo": "harvest, prepare feast, store",
}
COLORS = {
    "Nigredo": "black",
    "Albedo": "white",
    "Citrinitas": "yellow-gold",
    "Rubedo": "crimson-red",
}

EARTH_RADIUS_M = 6371000.0

def _deg2rad(d: float) -> float:
    return d * math.pi / 180.0


def _rad2deg(r: float) -> float:
    return r * 180.0 / math.pi

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    φ1, φ2 = _deg2rad(lat1), _deg2rad(lat2)
    Δφ = φ2 - φ1
    Δλ = _deg2rad(lon2 - lon1)

    a = math.sin(Δφ / 2.0) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_M * c


def _vertical_angle_deg(d_horizontal_m: float, dz_m: float) -> float:
    """Elevation angle (deg) from observer to target."""
    if d_horizontal_m <= 0.0:
        return 90.0 if dz_m > 0 else -90.0 if dz_m < 0 else 0.0
    return _rad2deg(math.atan2(dz_m, d_horizontal_m))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from (lat1,lon1) to (lat2,lon2); 0°=N, clockwise."""
    φ1, φ2 = _deg2rad(lat1), _deg2rad(lat2)
    Δλ = _deg2rad(lon2 - lon1)

    x = math.sin(Δλ) * math.cos(φ2)
    y = math.cos(φ1) * math.sin(φ2) - math.sin(φ1) * math.cos(φ2) * math.cos(Δλ)

    θ = math.atan2(x, y)  # NOTE: swapped to align 0°=N convention
    bearing = (_rad2deg(θ) + 360.0) % 360.0
    return bearing

def calculate_sunrise_azimuth(date, latitude, longitude, tz: Optional[str] = "UTC"):
    """Return sunrise azimuth (deg, 0=N clockwise) using AetherField.

    Returns None for polar day/night (no sunrise).
    """
    tzinfo = pytz.timezone(tz) if isinstance(tz, str) else tz
    dt = tzinfo.localize(datetime(date.year, date.month, date.day, 12, 0, 0)) if tzinfo else datetime(
        date.year, date.month, date.day, 12, 0, 0
    )
    return _sunrise_azimuth(dt, float(latitude), float(longitude), tzinfo or "UTC")

def determine_solar_movement(yesterday_az, today_az):
    
    return _determine_solar_movement(yesterday_az, today_az)


def is_solstice(prev_direction, current_direction):
    """Simple direction-change heuristic for solstice detection."""
    return prev_direction != current_direction and prev_direction != "Stationary"

def current_solstice_anchors(today):
    year = today.year
    # Approx solstice dates (good enough for geometry)
    summer = datetime(year, 6, 21).date()
    winter = datetime(year, 12, 21).date()

    if today <= summer:
        # We are in: last winter -> this summer
        winter_anchor = date(year-1, 12, 21)
        summer_anchor = summer
    else:
        # We are in: this summer -> this winter
        summer_anchor = summer
        winter_anchor = winter

    return winter_anchor, summer_anchor

class CityDaemon:
    def __init__(self, name, latitude, longitude, tz, guardian_id):
        self.name = name
        self.floor = ThresholdFloor(name, latitude, longitude, tz)
        self.floor.guardian = guardian_id
        self.phase = None

    def run_sweep(self):
        # detect local direction / phase from sun position
        direction = detect_solar_direction(self.floor.latitude, self.floor.longitude)
        print(direction)
        self.floor.set_directional_phase(direction)
        self.phase = self.floor.current_phase

        # update wheel, vault, visual states
        if self.phase == "nigredo":
            self.floor.vault.open_gate(self.floor.guardian)
        elif self.phase == "albedo":
            self.floor.vault.fetch_key("Aries")
        elif self.phase == "citrinitas":
            self.floor.vault.deposit_seed(100)
        elif self.phase == "rubedo":
            self.floor.ignite_rim()
        print(f"{self.name}: sweep complete → {self.phase}")

class Gate:
    def __init__(self, city, rung, posts, coords, tree_link, direction_policy="both", stone_required=None, ritual_note=None, cooldown_days=3):
        self.city = city
        self.rung = rung
        self.posts = posts[:]  # list of post names
        self.coords = coords
        self.tree_link = tree_link
        self.direction_policy = direction_policy.lower()
        self.stone_required = stone_required
        self.ritual_note = ritual_note

        self.cooldown_days = cooldown_days
        # state
        self.last_opened = None
        self.bindings = []  # list of {who, post, date, stone}
    
    def allows_direction(self, axis):
        axis = axis.lower()
        if self.direction_policy == "both":
            return True
        return (self.direction_policy == "west_only" and axis == "west") or \
               (self.direction_policy == "east_only" and axis == "east")
    
    def is_rung_active(self, k_step):
        # exact match; could accept tolerance rules here
        return k_step == self.rung
    
    def can_open(self, k_step, axis, today):
        if not self.is_rung_active(k_step):
            return False
        if not self.allows_direction(axis):
            return False
        if self.last_opened:
            if (today - self.last_opened).days < self.cooldown_days:
                return True  # still open
        return True
    
    def tie_cord(self, who, post, stone, today):
        if post not in self.posts:
            return {"ok": False, "reason": "bad_post"}
        if self.stone_required and stone != self.stone_required:
            return {"ok": False, "reason": "wrong_stone"}
        # consume stone externally then record
        binding = {"who": who, "post": post, "date": today.isoformat(), "stone": stone}
        self.bindings.append(binding)
        self.last_opened = today
        return {"ok": True, "binding": binding}
    
    def open_state(self, k_step, axis, today):
        return {
            "city": self.city,
            "rung": self.rung,
            "active": self.is_rung_active(k_step),
            "direction_ok": self.allows_direction(axis),
            "can_open": self.can_open(k_step, axis, today),
            "last_opened": getattr(self.last_opened, "isoformat", lambda: None)()
        }

class FloorDaemon:
    def __init__(self, name, latitude, longitude, tz, guardian_id):
        self.name = name
        self.floor = ThresholdFloor(name, latitude, longitude, tz)
        self.floor.guardian = guardian_id
        self.phase = None

    def run_sweep(self):
        # detect local direction / phase from sun position
        direction = detect_solar_direction(self.floor.latitude, self.floor.longitude)
        print(direction)
        self.floor.set_directional_phase(direction)
        self.phase = self.floor.current_phase

        # update wheel, vault, visual states
        if self.phase == "nigredo":
            self.floor.vault.open_gate(self.floor.guardian)
        elif self.phase == "albedo":
            self.floor.vault.fetch_key("Aries")
        elif self.phase == "citrinitas":
            self.floor.vault.deposit_seed(100)
        elif self.phase == "rubedo":
            self.floor.ignite_rim()
        print(f"{self.name}: sweep complete → {self.phase}")

class FloorMemory:
    def __init__(self):
        self.records = []

    def log(self, timestamp, temp, rain, wind):
        self.records.append({
            "time": timestamp,
            "temp": temp,
            "rain": rain,
            "wind": wind
        })

class ChthonicVault:
    def __init__(self):
        self.keys = {}        # {sign: {"element": "gold", "found": False}}
        self.sandals = {}     # {month: {"constellation": "Virgo", "status": "hidden"}}
        self.seed_storage = 0 # barley, wheat, etc.
        self.is_open = False
        self.guardian_inside = None

    def open_gate(self, guardian):
        if not self.is_open:
            self.is_open = True
            self.guardian_inside = guardian
            print(f"The gate yawns open. {guardian} descends.")
        else:
            print("Vault already open.")

    def close_gate(self):
        if self.is_open:
            print(f"{self.guardian_inside} ascends; gate closes.")
            self.is_open = False
            self.guardian_inside = None

    def fetch_key(self, sign):
        key = self.keys.get(sign)
        if key:
            key["found"] = True
            print(f"Fetched the {sign} equinox key.")
            return key
        print("No key found for that sign.")

    def fetch_sandal(self, month):
        sandal = self.sandals.get(month)
        if sandal:
            sandal["status"] = "worn"
            print(f"Sandal of {month} retrieved and worn.")
            return sandal

    def deposit_seed(self, amount):
        self.seed_storage += amount
        print(f"Stored {amount} sheaves. Total: {self.seed_storage}.")

    def withdraw_seed(self, amount):
        if self.seed_storage >= amount:
            self.seed_storage -= amount
            print(f"Withdrew {amount} sheaves for planting.")
            return amount
        print("Not enough grain stored.")

class ThresholdFloor:
    """The Threshold Floor — where sun, moon, and alchemy intersect."""
    
    def __init__(
        self,
        name: str,
        latitude: float = 0,
        longitude: float = 0,
        tz: str = "UTC",
        elevation_m: float = 0.0,
        gate_coords: Optional[Tuple[float, float, float]] = None,
        tree_coords: Optional[Tuple[float, float, float]] = None,
        calibration: str = "AetherField"
    ):
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self.tz = tz
        self.af = AetherField.load_calibration(calibration)
        self.pegs = self.compute_pegs()
        # Scan for horizon elevation using SRTM
        self.horizon = {}
        self.elevation_m = float(elevation_m) if elevation_m else topo(latitude, longitude)
        self.gate_coords: Optional[Tuple[float, float, float]] = gate_coords
        self.tree_coords: Optional[Tuple[float, float, float]] = tree_coords
        self.arch_bearing_deg: float = EAST_ARCH["azimuth"]
        self.arch_altitude_center_deg: Optional[float] = None
        self.arch_altitude_span_deg: Optional[Tuple[float, float]] = None
        self.gate_posts: Dict[str, float] = {}
        self.scarlet_cord_bearing_deg: Optional[float] = None
        self.scarlet_cord_altitude_deg: Optional[float] = None
        self.visual_state = "idle"
        self.mode = "threshing"
        self.current_phase = None
        self.water_level = 0.0
        self.blood_level = 0.0
        self.wine_level = 0.0
        self.fruit_load = 0.0
        self.must_level = 0.0
        self.food_supply = 0.0
        self.vault = ChthonicVault()
        self.underworld_gates = "locked"
        self.key_state = "seated"
        self.sandal_state = "hidden"
        self.guardian = None
        self.current_atmosphere = []
        self.current_wind = []
        self.current_weather = None
        self.weather_raw = {}
        self.fire_intensity = 0.0
        self.lunar_phase = None
        self.is_purified = False
        self.last_swept = None
        self.wheel_enabled = True
        self.wheel_speed = 1.0

    def compute_solstice_anchors(self, year=None):
        """
        Return (winter_date, summer_date) anchors for the *cycle that contains today*.
        Uses simple approximate dates (Dec 21 / Jun 21) but you can replace with more accurate solstice calcs.
        """
        today = _date_cls.today()
        if year is None:
            year = today.year
        # choose anchors around the current year such that they bracket the current date when used appropriately
        summer = _date_cls(year, 6, 21)
        winter = _date_cls(year, 12, 21)
        # if today's earlier than summer, use last winter -> this summer
        if today <= summer:
            return (_date_cls(year-1, 12, 21), summer)
        else:
            # today after summer: use this summer -> this winter
            return (summer, winter)

    def get_phase(self):
        return self.alchemy_phase()["phase"]

    def alchemy_phase(self) -> Dict[str, Any]:
        """Discern alchemical phase from prior-day sunrise movement and position.

        Logic (hemisphere-aware using arches on the threshing floor):
        - East arch = ~90° azimuth for sunrise.
        - Position relative to arch:
            - Northern hemisphere: north-of-east if az > 90; south-of-east if az < 90.
            - Southern hemisphere: warm side flips → south-of-east is the warm half.
        - Heading from prior-day movement:
            - 'Advancing' → southern heading (declination decreasing)
            - 'Retreating' → northern heading (declination increasing)
        - Mapping (for both hemispheres via warm-side notion):
            - heading=north & on warm side     → Albedo
            - heading=south & on warm side     → Rubedo
            - heading=south & on cool side     → Citrinitas
            - heading=north & on cool side     → Nigredo
            - heading=stationary               → Rubedo if warm side else Nigredo
        Returns a dict: { phase, heading, position, hemisphere, azimuth, east_arch }.
        """
        row = self
        tz = row.tz or os.getenv('TZ') or 'UTC'
        lat, _lon = row.latitude, row.longitude
        hemisphere = 'north' if _lon >= 0.001 else 'south'
        east_arch = EAST_ARCH["azimuth"]
        # Seed yesterday's azimuth and direction if missing
        today = _date_cls.today()
        yesterday = today - timedelta(days=1)
        last_az = None
        last_date = None
        last_dir = None
        prev_az = None
        heading = None
        # If we have no history yet, seed yesterday's values
        if not last_date or last_date != yesterday:
            try:
                prev_az = calculate_sunrise_azimuth(yesterday, self.latitude, self.longitude, tz)
                heading = self.get_solar_direction().lower()
            except Exception as e:
                print(e)
                pass
    
        az = prev_az
        if not isinstance(az, (int, float)):
            # Fallback to today's azimuth if prior snapshot is missing
            try:
                az = calculate_sunrise_azimuth(self.now(), self.latitude, self.longitude, tz)
                heading = self.get_solar_direction().lower()

            except Exception:
                az = None
        try:
            azf = float(az) if az is not None else None
        except Exception:
            azf = None
        # If azimuth is unknown, return unknown phase
        if azf is None:
            return {
                'phase': 'unknown',
                'heading': 'unknown',
                'position': 'unknown',
                'hemisphere': hemisphere,
                'azimuth': None,
                'east_arch': east_arch,
            }
        # Determine position relative to east arch
        north_of_east = azf > east_arch
        south_of_east = azf < east_arch
        # Warm side depends on hemisphere
        warm_side = north_of_east if hemisphere == 'north' else south_of_east
        position_label = 'north_of_east' if north_of_east else ('south_of_east' if south_of_east else 'on_east')
        # Map to alchemical phase
        if heading == 'north' and warm_side:
            phase = 'Albedo' if hemisphere == 'north' else 'Rubedo'
        elif heading == 'south' and warm_side:
            phase = 'Rubedo' if hemisphere == 'north' else 'Albedo'
        elif heading == 'south' and not warm_side:
            phase = 'Citrinitas' if hemisphere == 'north' else 'Nigredo'
        elif heading == 'north' and not warm_side:
            phase = 'Nigredo' if hemisphere == 'north' else 'Citrinitas'
        else:
            phase = 'Rubedo' if warm_side else 'Nigredo' if hemisphere == 'north' else 'Nigredo' if warm_side else 'Rubedo'
        self.phase = phase
        return {
            'phase': phase,
            'heading': heading,
            'position': position_label,
            'hemisphere': hemisphere,
            'azimuth': azf,
            'east_arch': east_arch,
        }

    def sun_delay(self) -> Dict[str, Any]:
        angle = scan_vector(self.latitude, self.longitude, self.get_sunrise())
        delay = estimate_sun_delay(angle)
        return {"angle": angle, "delay": delay}

    def sigil(self, size: int = 512, show: bool = True):
        try:
            self.get_phase()
            sig = tf_sigil(self, size)
            if show:
                show_sigil(sig)
            return sig
        except Exception:
            return None

    def compute_gdd(self, base_temp: float = 10) -> float:
        return None # TODO

    def recent_rain(self, days: int = 3) -> float:
        return None # TODO
        cutoff = datetime.utcnow() - timedelta(days=days)

    def ecological_state(self) -> Dict[str, Any]:
        gdd = self.compute_gdd()
        rain = self.recent_rain(days=5)
        return {
            "gdd": gdd,
            "recent_rain": rain,
            "phase": self._infer_phase(gdd, rain)
        }

    def _infer_phase(self, gdd: float, rain: float) -> str:
        if gdd < 100:
            return "dormant"
        if 100 <= gdd <= 300:
            return "shoots"
        if 300 < gdd <= 800:
            return "growth"
        if 800 < gdd <= 1400:
            return "fruiting"
        if gdd > 1200 and rain > 10:
            return "mushroom_trigger"
        return "late"

    def observe(self, dt: Optional[datetime] = None) -> Dict[str, Any]:
        if dt is None:
            dt = self.now()
        obs = _solar_horizontal_at(dt, self.latitude, self.longitude)
        return {
            "time": dt,
            "sun": obs,
            "location": {
                "lat": self.latitude,
                "lon": self.longitude,
                "elevation": self.elevation_m
            }
        }

    def as_above(self) -> Dict[str, Any]:
        return tf_as_above_zodiac(self.now(), (self.latitude, self.longitude))

    def so_below(self) -> Dict[str, Any]:
        return tf_so_below_zodiac(self.now(), (self.latitude, self.longitude))

    def now(self) -> datetime:
        tzinfo = pytz.timezone(self.tz)
        return datetime.now(tzinfo)

    def weather(self) -> str:
        if not WEATHER_EXISTS:
            return None
        self.weather_raw = get_weather(self.latitude, self.longitude, api_key)
        self.current_weather = self.weather_raw.get("weather", [{}])[0].get("description", "").lower()
        return self.current_weather

    def atmosphere(self) -> Dict[str, Any]:
        if not WEATHER_EXISTS:
            return None
        if not self.weather_raw:
            self.weather()
        self.current_atmosphere = get_local_atmosphere_data(self.weather_raw)
        return self.current_atmosphere

    def wind(self) -> Dict[str, Any]:
        if not WEATHER_EXISTS:
            return None
        if not self.weather_raw:
            self.weather()
        self.current_wind = get_wind_data(self.weather_raw)
        self.weather_raw.get("weather", [{}])[0].get("description", "").lower()
        return self.current_wind

    def find_alignment_day(self, year: int, tol_deg: float = 0.5) -> List[Dict[str, Any]]:
        from datetime import date, timedelta

        def ang_diff(a, b) -> float:
            return min((a - b) % 360.0, (b - a) % 360.0)

        start = date(year, 1, 1)
        end = date(year, 12, 31)
        prev_az = None
        prev_dir = None
        candidates = []

        d = start
        while d <= end:
            az = calculate_sunrise_azimuth(d, self.latitude, self.longitude, self.tz)
            if az is None:
                d += timedelta(days=1)
                continue
            if self.scarlet_cord_bearing_deg is not None:
                Δ = ang_diff(az, self.scarlet_cord_bearing_deg)
                if Δ <= tol_deg:
                    if prev_az is not None:
                        direction = "North" if az > prev_az else "South"
                        if prev_dir and direction != prev_dir:
                            candidates.append((d, az, Δ, direction))
                        prev_dir = direction
            prev_az = az
            d += timedelta(days=1)
        return candidates

    def compute_pegs(self, winter_anchor=None, summer_anchor=None) -> List[float]:
        calc = globals().get("calculate_sunrise_azimuth", None)
        if calc is None and hasattr(self, "calculate_sunrise_azimuth"):
            calc = getattr(self, "calculate_sunrise_azimuth")
        if winter_anchor is None or summer_anchor is None:
            winter_anchor, summer_anchor = self.compute_solstice_anchors()
        try:
            A_w = calc(winter_anchor, self.latitude, self.longitude, getattr(self, "tz", None))
            A_s = calc(summer_anchor, self.latitude, self.longitude, getattr(self, "tz", None))
            span = A_s - A_w
            if span < 0:
                span = (A_s + 360.0) - A_w
            step = span / 6.0
            pegs = [(A_w + i * step) % 360.0 for i in range(7)]
        except Exception:
            base = 90.0
            pegs = [(base + i * (30.0)) % 360.0 for i in range(7)]
        self.pegs = pegs
        return pegs

    def peg_index(self, az: float) -> int:
        if not hasattr(self, "pegs") or not self.pegs:
            try:
                self.compute_pegs()
            except Exception:
                self.pegs = [76.69, 81.46, 86.23, 91.01, 95.79, 100.56, 105.33]
        pegs = self.pegs
        az = az % 360.0
        base = pegs[0]
        shifted = [p if p >= base else p + 360.0 for p in pegs]
        target = az
        if target < base:
            target += 360.0
        for i in range(1, len(shifted)):
            if target < shifted[i]:
                return i - 1
        return len(shifted) - 1

    def step_peg(self, raw: int, direction: str) -> int:
        if direction is None:
            direction = "north"
        direction = direction.lower()
        if direction == "south":
            return max(0, min(6, raw + 1))
        else:
            return max(0, min(6, raw - 1))

    def current_k_and_direction(self, dt: datetime) -> Tuple[int, str, float, int]:
        calc = globals().get("calculate_sunrise_azimuth", None)
        get_dir = globals().get("get_solar_direction", None)
        if calc is None and hasattr(self, "calculate_sunrise_azimuth"):
            calc = getattr(self, "calculate_sunrise_azimuth")
        if get_dir is None and hasattr(self, "get_solar_direction"):
            get_dir = getattr(self, "get_solar_direction")
        try:
            az = calc(dt, self.latitude, self.longitude, getattr(self, "tz", None))
        except Exception:
            az = 90.0
        if not hasattr(self, "pegs") or not self.pegs:
            try:
                self.compute_pegs()
            except Exception:
                self.pegs = [76.69, 81.46, 86.23, 91.01, 95.79, 100.56, 105.33]
        raw = self.peg_index(az)
        try:
            direction_val = get_dir(dt, getattr(self, "tz", None))
        except Exception:
            try:
                az2 = calc(dt + timedelta(days=1), self.latitude, self.longitude, getattr(self, "tz", None))
                direction_val = "north" if az2 < az else "south"
            except Exception:
                direction_val = "south"
        k_step = self.step_peg(raw, direction_val)
        return k_step, direction_val, az, raw

    # Site / geometry configuration
    def configure_gatehouse(self, lat: float, lon: float, elev_m: float, bearing_deg: Optional[float] = None):
        self.gate_coords = (float(lat), float(lon), float(elev_m))
        if bearing_deg is not None:
            self.arch_bearing_deg = float(bearing_deg)
        self._update_scarlet_cord_geometry()

    def add_gate_post(self, name: str, bearing_deg: float):
        self.gate_posts[name] = float(bearing_deg)

    def add_symmetric_gate_posts(self, count: int, spread_deg: float):
        if count < 1:
            return
        center = self.arch_bearing_deg
        if count == 1:
            self.gate_posts["center"] = center
            return
        step = spread_deg / (count - 1)
        start = center - spread_deg / 2.0
        for i in range(count):
            bearing = start + i * step
            name = f"post_{i+1}"
            self.gate_posts[name] = bearing

    def auto_layout_lion_springs_across_solar_range(self, year: int | None = None, start_date: _date_cls | None = None, days: int = 365, num_lions: int = 7, tz: str | None = None):
        if tz is None:
            tz = self.tz
        if start_date is None:
            if year is None:
                today = _date_cls.today()
                year = today.year
            start_date = _date_cls(year, 1, 1)
        end_date = start_date + timedelta(days=days)
        d = start_date
        min_az = None
        max_az = None
        while d < end_date:
            az = calculate_sunrise_azimuth(d, self.latitude, self.longitude, tz)
            if az is not None and not math.isnan(az):
                if min_az is None or az < min_az:
                    min_az = az
                if max_az is None or az > max_az:
                    max_az = az
            d += timedelta(days=1)
        if min_az is None or max_az is None:
            print(f"{self.name}: could not determine solar azimuth range for window {start_date} → {end_date}.")
            return
        spread = max_az - min_az
        sector_width = spread / num_lions
        for i in range(num_lions):
            lion_az_min = min_az + i * sector_width
            lion_az_max = lion_az_min + sector_width
            lion_az_center = (lion_az_min + lion_az_max) / 2.0
            delta = lion_az_center - self.arch_bearing_deg
            δ = math.radians(delta)
            x = math.cos(δ) * math.sin(δ)
            z = math.cos(δ) ** 2
            self.lions[i] = {
                "azimuth_min": lion_az_min,
                "azimuth_max": lion_az_max,
                "azimuth_center": lion_az_center,
                "wall_x": x,
                "wall_z": z,
                "state": "clean"
            }

    def auto_layout_gate_posts_across_solar_range(self, year: int | None = None, start_date: _date_cls | None = None, days: int = 365, num_pegs: int = 7, tz: str | None = None):
        if tz is None:
            tz = self.tz
        if start_date is None:
            if year is None:
                today = _date_cls.today()
                year = today.year
            start_date = _date_cls(year, 1, 1)
        end_date = start_date + timedelta(days=days)
        d = start_date
        min_az = None
        max_az = None
        while d < end_date:
            az = calculate_sunrise_azimuth(d, self.latitude, self.longitude, tz)
            if az is not None and not math.isnan(az):
                if min_az is None or az < min_az:
                    min_az = az
                if max_az is None or az > max_az:
                    max_az = az
            d += timedelta(days=1)
        if min_az is None or max_az is None:
            print(f"{self.name}: could not determine solar azimuth range for window {start_date} → {end_date}.")
            return
        self.gate_posts.clear()
        if num_pegs <= 0:
            print(f"{self.name}: num_pegs must be >= 1")
            return
        if num_pegs == 1:
            mid = (min_az + max_az) / 2.0
            self.gate_posts["peg_1"] = mid
            return
        spread = max_az - min_az
        step = spread / (num_pegs - 1)
        for i in range(num_pegs):
            bearing = min_az + i * step
            name = f"peg_{i+1}"
            self.gate_posts[name] = bearing

    def scan_solar_cycle_for_months(self, start_date: _date_cls, days: int = 365, tz: str | None = None, tol_deg: float = 2.0) -> Dict[str, Any]:
        if tz is None:
            tz = self.tz
        months: Dict[int, List[_date_cls]] = {m: [] for m in range(1, 13)}
        first_hits: Dict[int, _date_cls | None] = {m: None for m in range(1, 13)}
        timeline: List[Dict] = []
        d = start_date
        end = start_date + timedelta(days=days)
        while d < end:
            record = self.get_current_peg_and_month(target_date=d, tz=tz, tol_deg=tol_deg)
            if record is None:
                timeline.append({"date": d, "sun_az": None, "peg_index": None, "peg_name": None, "peg_bearing": None, "delta_deg": None, "direction": None, "month": None, "hit": False})
                d += timedelta(days=1)
                continue
            timeline.append(record)
            month = record.get("month")
            hit = record.get("hit", False)
            if month is not None and 1 <= month <= 12:
                months[month].append(d)
                if first_hits[month] is None:
                    first_hits[month] = d
            d += timedelta(days=1)
        return {"start_date": start_date, "end_date": end, "months": months, "first_hits": first_hits, "timeline": timeline}

    def configure_tree(self, lat: float, lon: float, elev_m: float):
        self.tree_coords = (float(lat), float(lon), float(elev_m))
        self._update_scarlet_cord_geometry()

    def _update_scarlet_cord_geometry(self):
        if not (self.gate_coords and self.tree_coords):
            return
        g_lat, g_lon, g_elev = self.gate_coords
        t_lat, t_lon, t_elev = self.tree_coords
        bearing = _bearing_deg(g_lat, g_lon, t_lat, t_lon)
        self.scarlet_cord_bearing_deg = bearing
        d = _haversine_m(g_lat, g_lon, t_lat, t_lon)
        dz = t_elev - g_elev
        alt = _vertical_angle_deg(d, dz)
        self.scarlet_cord_altitude_deg = alt
        self.arch_altitude_center_deg = alt
        self.arch_altitude_span_deg = (alt - 1.0, alt + 1.0)
        print(f"{self.name}: scarlet cord line set → bearing {bearing:.2f}°, altitude {alt:.2f}°")

    def check_dawn_gate_alignment(self, target_date=None, tz=None, tol_deg: float = 1.0):
        if target_date is None:
            target_date = _date_cls.today()
        if tz is None:
            tz = self.tz
        sun_az = calculate_sunrise_azimuth(target_date, self.latitude, self.longitude, tz)
        if sun_az is None:
            print(f"{self.name}: no sunrise computed for {target_date}.")
            return
        def ang_diff(a, b) -> float:
            return min((a - b) % 360.0, (b - a) % 360.0)
        print(f"{self.name}: sunrise {sun_az:.2f}°")
        Δ_gate = ang_diff(sun_az, self.arch_bearing_deg)
        print(f"  Gate center {self.arch_bearing_deg:.2f}° (Δ={Δ_gate:.2f}°)")
        if self.scarlet_cord_bearing_deg is not None:
            Δ_cord = ang_diff(sun_az, self.scarlet_cord_bearing_deg)
            print(f"  Scarlet cord bearing {self.scarlet_cord_bearing_deg:.2f}° (Δ={Δ_cord:.2f}°)")
        best_post = None
        best_Δ = None
        for name, bearing in self.gate_posts.items():
            d = ang_diff(sun_az, bearing)
            if best_Δ is None or d < best_Δ:
                best_Δ = d
                best_post = (name, bearing, d)
        if best_post is not None:
            name, bearing, d = best_post
            print(f"  Nearest post: {name} at {bearing:.2f}° (Δ={d:.2f}°)")
            if d <= tol_deg:
                print(f"  ➜ Dawn stands on {name} today.")
            else:
                print("  ➜ Dawn misses all posts.")

    def get_sunrise(self, target_date=None) -> float:
        if target_date is None:
            target_date = self.now()
        return calculate_sunrise_azimuth(target_date, self.latitude, self.longitude, self.tz) or float("nan")

    def get_solar_direction(self, target_date=None, tz=None) -> str:
        if target_date is None:
            target_date = _date_cls.today()
        if tz is None:
            tz = self.tz
        today = target_date
        yesterday = today - timedelta(days=1)
        y_az = calculate_sunrise_azimuth(yesterday, self.latitude, self.longitude, tz) or float("nan")
        t_az = calculate_sunrise_azimuth(today, self.latitude, self.longitude, tz) or float("nan")
        return determine_solar_movement(y_az, t_az)

    def _ang_diff(self, a: float, b: float) -> float:
        return min((a - b) % 360.0, (b - a) % 360.0)

    def get_current_peg_and_month(self, target_date=None, tz=None, tol_deg: float = 2.0) -> Dict[str, Any]:
        if target_date is None:
            target_date = _date_cls.today()
        if tz is None:
            tz = self.tz
        sun_az = calculate_sunrise_azimuth(target_date, self.latitude, self.longitude, tz)
        if sun_az is None or math.isnan(sun_az):
            print(f"{self.name}: no sunrise for {target_date}")
            return None
        if not self.gate_posts:
            print(f"{self.name}: no gate posts defined.")
            return None
        best_name = None
        best_bearing = None
        best_delta = None
        best_index = None
        sorted_posts = sorted(self.gate_posts.items(), key=lambda kv: kv[1])
        for idx, (name, bearing) in enumerate(sorted_posts, start=1):
            d = self._ang_diff(sun_az, bearing)
            if best_delta is None or d < best_delta:
                best_delta = d
                best_name = name
                best_bearing = bearing
                best_index = idx
        direction = self.get_solar_direction(target_date, tz)
        month_num = self._month_from_peg_and_direction(best_index, direction)
        hit = best_delta <= tol_deg
        return {"date": target_date, "sun_az": sun_az, "peg_index": best_index, "peg_name": best_name, "peg_bearing": best_bearing, "delta_deg": best_delta, "direction": direction, "month": month_num, "hit": hit}

    @staticmethod
    def _month_from_peg_and_direction(peg_index: int, direction: str) -> int:
        direction = (direction or "").capitalize()
        if direction == "North":
            return max(1, min(7, peg_index))
        if direction == "South":
            mapping = {6: 8, 5: 9, 4: 10, 3: 11, 2: 12, 7: 7, 1: 1}
            return mapping.get(peg_index, peg_index)
        return max(1, min(7, peg_index))

    def scan_year_for_months(self, year: int, tz: str | None = None, tol_deg: float = 2.0) -> Dict[str, Any]:
        if tz is None:
            tz = self.tz
        months: Dict[int, List[_date_cls]] = {m: [] for m in range(1, 13)}
        first_hits: Dict[int, _date_cls | None] = {m: None for m in range(1, 13)}
        timeline: List[Dict] = []
        d = _date_cls(year, 1, 1)
        end = _date_cls(year + 1, 1, 1)
        while d < end:
            record = self.get_current_peg_and_month(target_date=d, tz=tz, tol_deg=tol_deg)
            if record is None:
                timeline.append({"date": d, "sun_az": None, "peg_index": None, "peg_name": None, "peg_bearing": None, "delta_deg": None, "direction": None, "month": None, "hit": False})
                d += timedelta(days=1)
                continue
            timeline.append(record)
            month = record.get("month")
            hit = record.get("hit", False)
            if month is not None and 1 <= month <= 12 and hit:
                months[month].append(d)
                if first_hits[month] is None:
                    first_hits[month] = d
            d += timedelta(days=1)
        return {"year": year, "months": months, "first_hits": first_hits, "timeline": timeline}

    def descend(self, guardian):
        self.vault.open_gate(guardian)
        self.key_state = "hidden"
        self.sandal_state = "hidden"
        print(f"{guardian} enters the chthonic vault for retrieval.")

    def ascend(self):
        self.vault.close_gate()
        self.key_state = "seated"
        self.sandal_state = "worn"

    def sweep(self):
        self.is_purified = True
        self.last_swept = "now"
        print(f"{self.name}: floor swept and ready for new rites.")

    def fill(self, element="water", amount=1.0):
        if element == "water":
            self.water_level = min(1.0, self.water_level + amount)
            self.mode = "mirror"
        elif element == "blood":
            self.blood_level = min(1.0, self.blood_level + amount)
            self.mode = "sacrifice"
        elif element == "wine":
            self.wine_level = min(1.0, getattr(self, "wine_level", 0.0) + amount)
            self.mode = "reset"
        print(f"{self.name}: filled with {element}, mode set to {self.mode}.")

    def drain(self):
        self.water_level = 0
        self.blood_level = 0
        self.wine_level = 0
        self.mode = "threshing"
        print(f"{self.name}: floor drained and dry again.")

    def toggle_gates(self, state=None):
        self.underworld_gates = state or ("unlocked" if self.underworld_gates == "locked" else "locked")
        print(f"Gates to underworld now {self.underworld_gates}.")

    def seat_key(self, state="seated"):
        self.key_state = state
        print(f"Key is now {state}.")

    def adjust_sandal(self, state="worn"):
        self.sandal_state = state
        print(f"Sandal is now {state}.")

    def ignite_fire(self, intensity=1.0):
        self.fire_intensity = intensity
        print(f"Torch lit at {intensity*100:.0f}% intensity.")

    def extinguish_fire(self):
        self.fire_intensity = 0
        print("Torches extinguished; awaiting relight at tuning moment.")

    def harvest(self) -> float:
        if not self.is_purified:
            print("Warning: floor uncleansed, yield reduced.")
        yield_amt = self.food_supply * 0.8 if self.is_purified else self.food_supply * 0.5
        print(f"Harvest completed, yield {yield_amt:.2f} units.")
        self.food_supply = 0
        return yield_amt

    def describe(self):
        desc = f"{self.name} — mode:{self.mode}, gates:{self.underworld_gates}, key:{self.key_state}, sandal:{self.sandal_state}, fire:{self.fire_intensity}, water:{self.water_level}, blood:{self.blood_level}"
        print(desc)

    def stop_wheel(self):
        self.wheel_enabled = False
        self.wheel_speed = 0.0
        print(f"{self.name}: celestial wheel halted.")

    def resume_wheel(self, speed=1.0):
        self.wheel_enabled = True
        self.wheel_speed = speed
        print(f"{self.name}: wheel resumes at {speed}× speed.")

    def adjust_wheel_speed(self, delta):
        if self.wheel_enabled:
            self.wheel_speed = max(0.1, self.wheel_speed + delta)
            print(f"{self.name}: wheel speed adjusted to {self.wheel_speed:.2f}×")

    def set_visual(self, state):
        visuals = {
            "idle":      {"color": "soft gold", "fire": 0.1, "ambience": "breeze"},
            "pit":       {"color": "crimson glow", "fire": 1.0, "ambience": "roar"},
            "mirror":    {"color": "silver blue", "fire": 0.2, "ambience": "echo"},
            "feast":     {"color": "amber warmth", "fire": 0.4, "ambience": "music"},
            "nigredo":   {"color": "black ash", "fire": 0.0, "ambience": "silence"},
            "equinox":   {"color": "white gold", "fire": 0.8, "ambience": "choir"},
        }
        if state not in visuals:
            print(f"Unknown visual state: {state}")
            return
        self.visual_state = state
        vs = visuals[state]
        self.fire_intensity = vs["fire"]
        print(f"{self.name}: visual set to {state} | color {vs['color']}, fire {vs['fire']}, ambience {vs['ambience']}.")

    def ignite_rim(self):
        self.set_visual("pit")
        self.stop_wheel()
        self.underworld_gates = "locked"

    def cool_rim(self):
        self.set_visual("idle")
        self.resume_wheel(1.0)
        self.underworld_gates = "unlocked"

    def start_duel(self, floor, attacker, defender, weapon=None):
        floor.mode = "pit"
        floor.fire_intensity = 1.0
        floor.underworld_gates = "locked"
        floor.wheel_enabled = False
        a_health = attacker.health
        d_health = defender.health
        a_attack, a_magic = attacker.strength, attacker.magic
        d_attack, d_magic = defender.strength, defender.magic
        crit = 0.1
        if weapon and getattr(attacker, "has_trait", lambda x: False)("Huntress"):
            crit += 0.2
        scythe_speed = weapon.get("speed", 50) if weapon else 50
        attacker_turn = random.randint(1, 100) > scythe_speed
        while a_health > 0 and d_health > 0:
            if attacker_turn:
                dmg = a_attack if defender.strength > defender.magic else a_magic
                if random.random() < crit:
                    dmg *= 1.5
                d_health -= dmg
                attacker_turn = False
            else:
                dmg = d_attack if attacker.strength > attacker.magic else d_magic
                a_health -= dmg
                attacker_turn = True
        if a_health > 0 and d_health <= 0:
            winner, loser = attacker, defender
        elif d_health > 0 and a_health <= 0:
            winner, loser = defender, attacker
        else:
            winner, loser = random.choice([(attacker, defender), (defender, attacker)])
        floor.key_holder = winner.user_id
        floor.key_state = "held"
        floor.fire_intensity = 0.3
        floor.underworld_gates = "unlocked"
        floor.wheel_enabled = True
        floor.mode = "threshing"
        return winner, loser

    def set_directional_phase(self, direction: str):
        mapping = {
            "east":  {"season": "spring", "phase": "albedo", "visual": "white dawn"},
            "south": {"season": "summer", "phase": "citrinitas", "visual": "amber noon"},
            "west":  {"season": "autumn", "phase": "rubedo", "visual": "red dusk"},
            "north": {"season": "winter", "phase": "nigredo", "visual": "indigo night"},
        }
        info = mapping[direction]
        self.visual_state = info["visual"]
        self.current_phase = info["phase"]
        print(f"{self.name}: facing {direction} → {info['season']} / {info['phase']}.")

    def check_balance(self):
        if 0.4 <= self.vault.water_level <= 0.6 and self.wheel_enabled:
            self.manifest_arc_weapon()
        else:
            self.dissolve_arc_weapon()

    def manifest_arc_weapon(self):
        self.arc_visible = True
        print("A luminous bow arcs across the chamber — covenant restored.")

    def dissolve_arc_weapon(self):
        if getattr(self, "arc_visible", False):
            self.arc_visible = False
            print("The bow fades as balance falters.")