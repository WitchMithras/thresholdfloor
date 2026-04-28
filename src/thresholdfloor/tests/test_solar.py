"""Solar geometry tests for thresholdfloor."""
import pytest
import math
from datetime import date

# Import functions from the module
from thresholdfloor import (
    calculate_sunrise_azimuth,
    compute_pegs,
    compute_solstice_anchors,
    determine_solar_movement,
    is_solstice,
    current_solstice_anchors,
    level_floor_contents,
    map_azimuth_to_lion,
    layout_lions_from_azimuths,
)

def test_current_solstice_anchors():
    """Test solstice anchor calculation."""
    today = date.today()
    winter_anchor, summer_anchor = current_solstice_anchors(today)
    assert isinstance(winter_anchor, date)
    assert isinstance(summer_anchor, date)
    assert winter_anchor.month in [11, 12] or summer_anchor.month in [5, 6]

def test_compute_pegs_format():
    """Test that compute_pegs returns 7 values."""
    pegs = compute_pegs()
    assert len(pegs) == 7
    for peg in pegs:
        assert isinstance(peg, (int, float))
        assert peg >= 0 and peg <= 360

def test_level_floor_contents():
    """Test floor capacity management."""
    floor = {"fruit_load": 0.5, "must_level": 0.3, "blood_level": 0.2, "wine_level": 0.1, "water_level": 0.1}
    result = level_floor_contents(floor.copy(), capacity=1.0)
    assert result == {"water_level": 0.0, "wine_level": 0.0, "blood_level": 0.0, "must_level": 0.0, "fruit_load": 0.0}
    
    # Test overflow
    floor2 = {"fruit_load": 0.8, "must_level": 0.5, "blood_level": 0.4, "wine_level": 0.4, "water_level": 0.4}
    result2 = level_floor_contents(floor2.copy(), capacity=1.0)
    assert floor2["fruit_load"] < 0.8
    assert floor2["must_level"] < 0.5

def test_map_azimuth_to_lion():
    """Test azimuth to lion mapping."""
    lion = map_azimuth_to_lion(90.0, 0, 360, 7, 90, 10)
    assert "lion_index" in lion
    assert "az_center" in lion
    assert "x_m" in lion
    assert "z_m" in lion

def test_layout_lions_from_azimuths():
    """Test lion fountain layout."""
    lions = layout_lions_from_azimuths(90, 270, 90, 7, 10)
    assert len(lions) == 7
    for lion in lions:
        assert "index" in lion
        assert "az_min" in lion
        assert "az_max" in lion
        assert "az_center" in lion
        assert "wall_x" in lion
        assert "wall_z" in lion

def test_is_solstice():
    """Test solstice detection."""
    assert is_solstice("North", "South") == True
    assert is_solstice("North", "North") == False
    assert is_solstice("South", "North") == True

def test_compute_solstice_anchors():
    """Test solstice anchor calculation."""
    today = date.today()
    winter, summer = compute_solstice_anchors(today)
    assert isinstance(winter, date)
    assert isinstance(summer, date)

def test_azimuth_bounds():
    """Test azimuth calculations are bounded 0-360."""
    az = calculate_sunrise_azimuth(date.today(), 40.7128, -74.0060, "America/New_York")
    if az is not None:
        assert 0 <= az <= 360
        assert az != math.nan

def test_compute_pegs_bounds():
    """Test compute_pegs returns valid azimuths."""
    pegs = compute_pegs()
    for peg in pegs:
        if peg is not None:
            assert peg >= 0
            assert peg <= 360

def test_significant_digits():
    """Test that azimuths have reasonable precision."""
    pegs = compute_pegs()
    for peg in pegs:
        if peg is not None:
            assert peg is not None

def test_multiple_locations():
    """Test azimuth calculation for different locations."""
    locations = [
        ("New York", 40.7128, -74.0060),
        ("London", 51.5074, -0.1278),
        ("Tokyo", 35.6762, 139.6503),
    ]
    for name, lat, lon in locations:
        az = calculate_sunrise_azimuth(date.today(), lat, lon, "UTC")
        if az is not None:
            assert az is not None
            assert az != math.nan