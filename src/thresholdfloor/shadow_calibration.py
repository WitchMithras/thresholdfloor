# shadow_calibration.py

import math
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any


Point = Tuple[float, float]  # (x, y) in local floor coordinates


@dataclass
class ShadowMark:
    """
    A measured shadow-tip mark on the floor.

    x/y should be in a consistent local frame:
      x = floor-right or image-right
      y = floor-up / image-up / local north-ish, depending on your canvas

    The calibration only needs consistency. True orientation emerges from the marks.
    """
    x: float
    y: float
    timestamp: str


@dataclass
class EastWestCalibration:
    """
    Result of fitting shadow-tip marks.
    """
    east_azimuth_deg: float
    west_azimuth_deg: float
    rms_error: float
    direction_vec_x: float
    direction_vec_y: float
    slope: float
    intercept: float
    mark_count: int
    created_at: str

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(raw: str) -> "EastWestCalibration":
        data = json.loads(raw)
        return EastWestCalibration(**data)


def _angle_delta_deg(a: float, b: float) -> float:
    """
    Smallest signed-ish absolute angle difference.
    """
    return abs((a - b + 180.0) % 360.0 - 180.0)


def fit_east_west_from_points(points: List[Point]) -> Dict[str, float]:
    """
    Fit a PCA best-fit line through shadow-tip points.

    Input points MUST be chronological.
    Earliest -> latest is interpreted as TRUE EAST.
    """

    if len(points) < 3:
        raise ValueError("Need at least 3 shadow-tip points for calibration.")

    x_mean = sum(p[0] for p in points) / len(points)
    y_mean = sum(p[1] for p in points) / len(points)

    sxx = sum((p[0] - x_mean) ** 2 for p in points)
    syy = sum((p[1] - y_mean) ** 2 for p in points)
    sxy = sum((p[0] - x_mean) * (p[1] - y_mean) for p in points)

    # Principal axis angle.
    theta = 0.5 * math.atan2(2.0 * sxy, sxx - syy)

    dx = math.cos(theta)
    dy = math.sin(theta)

    # Force line direction to follow time: earliest -> latest = east.
    time_dx = points[-1][0] - points[0][0]
    time_dy = points[-1][1] - points[0][1]

    if time_dx * dx + time_dy * dy < 0:
        dx = -dx
        dy = -dy

    # Azimuth convention:
    # 0° = north/up, 90° = east/right, clockwise positive.
    east_azimuth_deg = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0
    west_azimuth_deg = (east_azimuth_deg + 180.0) % 360.0

    if abs(dx) < 1e-8:
        slope = float("inf")
        intercept = float("nan")
    else:
        slope = dy / dx
        intercept = y_mean - slope * x_mean

    # Perpendicular RMS error to fitted line.
    # Direction vector is (dx, dy), normal vector is (-dy, dx).
    a = -dy
    b = dx
    c = -(a * x_mean + b * y_mean)

    def perp_dist(p: Point) -> float:
        return abs(a * p[0] + b * p[1] + c) / math.sqrt(a * a + b * b)

    rms_error = math.sqrt(sum(perp_dist(p) ** 2 for p in points) / len(points))

    return {
        "east_azimuth_deg": east_azimuth_deg,
        "west_azimuth_deg": west_azimuth_deg,
        "rms_error": rms_error,
        "direction_vec_x": dx,
        "direction_vec_y": dy,
        "slope": slope,
        "intercept": intercept,
    }


def calibrate_east_west(
    marks: List[ShadowMark],
    previous: Optional[EastWestCalibration] = None,
    min_angle_update_deg: float = 0.5,
    max_rms_error: Optional[float] = None,
) -> Tuple[EastWestCalibration, bool]:
    """
    Build a calibration from chronological shadow marks.

    Returns:
      calibration, should_publish

    should_publish is True when:
      - there is no previous calibration
      - east azimuth moved more than min_angle_update_deg
      - rms_error exceeds max_rms_error, when max_rms_error is supplied
    """

    if len(marks) < 3:
        raise ValueError("Need at least 3 marks.")

    # Sort by timestamp just in case they were added out of order.
    ordered = sorted(marks, key=lambda m: m.timestamp)
    points = [(m.x, m.y) for m in ordered]

    fit = fit_east_west_from_points(points)

    calibration = EastWestCalibration(
        east_azimuth_deg=fit["east_azimuth_deg"],
        west_azimuth_deg=fit["west_azimuth_deg"],
        rms_error=fit["rms_error"],
        direction_vec_x=fit["direction_vec_x"],
        direction_vec_y=fit["direction_vec_y"],
        slope=fit["slope"],
        intercept=fit["intercept"],
        mark_count=len(marks),
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    if previous is None:
        return calibration, True

    angle_changed = (
        _angle_delta_deg(
            calibration.east_azimuth_deg,
            previous.east_azimuth_deg,
        )
        > min_angle_update_deg
    )

    rms_bad = False
    if max_rms_error is not None:
        rms_bad = calibration.rms_error > max_rms_error

    return calibration, angle_changed or rms_bad
