# shadow_simulation.py

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple, List


Point2D = Tuple[float, float]


@dataclass
class Gnomon:
    """
    Vertical shadow-casting object.

    base_x/base_y are in floor coordinates.
    height is in the same unit scale as the floor:
      - meters if measuring real ground
      - pixels if simulating directly in canvas space
      - arbitrary floor units if your floor has its own model space
    """
    base_x: float
    base_y: float
    height: float


@dataclass
class SimulatedShadow:
    """
    Result of projecting a gnomon's shadow onto the floor.
    """
    tip_x: float
    tip_y: float
    length: float
    shadow_azimuth_deg: float
    sun_azimuth_deg: float
    sun_altitude_deg: float
    timestamp: str

    @property
    def tip(self) -> Point2D:
        return self.tip_x, self.tip_y


def normalize_angle_deg(angle: float) -> float:
    return angle % 360.0


def angle_delta_deg(a: float, b: float) -> float:
    return (a - b + 180.0) % 360.0 - 180.0


def azimuth_to_xy_unit(
    azimuth_deg: float,
    *,
    x_axis_azimuth_deg: float = 90.0,
    y_axis_azimuth_deg: float = 0.0,
) -> Point2D:
    """
    Convert compass azimuth into floor XY unit direction.

    Default convention:
      x+ = east
      y+ = north

    Azimuth convention:
      0° = north
      90° = east
      180° = south
      270° = west

    Returns:
      dx, dy
    """

    az = math.radians(azimuth_deg)

    # In east/north coordinates:
    # east component = sin(az)
    # north component = cos(az)
    dx = math.sin(az)
    dy = math.cos(az)

    return dx, dy


def shadow_length_from_altitude(
    gnomon_height: float,
    sun_altitude_deg: float,
    *,
    max_length: Optional[float] = None,
    min_altitude_deg: float = 0.1,
) -> float:
    """
    Shadow length for a vertical gnomon on a flat floor.

    length = height / tan(altitude)

    Very low Sun creates enormous shadows, so min_altitude_deg and max_length
    prevent singular goblin behavior near the horizon.
    """

    safe_alt = max(float(sun_altitude_deg), min_altitude_deg)
    alt_rad = math.radians(safe_alt)

    length = gnomon_height / math.tan(alt_rad)

    if max_length is not None:
        length = min(length, max_length)

    return length


def project_shadow_tip(
    gnomon: Gnomon,
    sun_azimuth_deg: float,
    sun_altitude_deg: float,
    *,
    timestamp: Optional[str] = None,
    max_length: Optional[float] = None,
    min_altitude_deg: float = 0.1,
) -> Optional[SimulatedShadow]:
    """
    Project the tip of a vertical gnomon's shadow onto the floor.

    The shadow points exactly opposite the Sun's azimuth.

    Returns None when the Sun is below the horizon.
    """

    if sun_altitude_deg <= 0:
        return None

    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    shadow_azimuth_deg = normalize_angle_deg(sun_azimuth_deg + 180.0)

    length = shadow_length_from_altitude(
        gnomon.height,
        sun_altitude_deg,
        max_length=max_length,
        min_altitude_deg=min_altitude_deg,
    )

    dx, dy = azimuth_to_xy_unit(shadow_azimuth_deg)

    tip_x = gnomon.base_x + dx * length
    tip_y = gnomon.base_y + dy * length

    return SimulatedShadow(
        tip_x=tip_x,
        tip_y=tip_y,
        length=length,
        shadow_azimuth_deg=shadow_azimuth_deg,
        sun_azimuth_deg=normalize_angle_deg(sun_azimuth_deg),
        sun_altitude_deg=sun_altitude_deg,
        timestamp=timestamp,
    )


def simulate_shadow_series(
    gnomon: Gnomon,
    sun_positions: List[Tuple[str, float, float]],
    *,
    max_length: Optional[float] = None,
    min_altitude_deg: float = 0.1,
) -> List[SimulatedShadow]:
    """
    Simulate many shadows.

    sun_positions format:
      [
        (timestamp, sun_azimuth_deg, sun_altitude_deg),
        ...
      ]
    """

    shadows = []

    for timestamp, az, alt in sun_positions:
        shadow = project_shadow_tip(
            gnomon,
            sun_azimuth_deg=az,
            sun_altitude_deg=alt,
            timestamp=timestamp,
            max_length=max_length,
            min_altitude_deg=min_altitude_deg,
        )

        if shadow is not None:
            shadows.append(shadow)

    return shadows