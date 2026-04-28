"""ThresholdFloor class tests."""
import pytest
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from thresholdfloor import ThresholdFloor, ChthonicVault

def test_threshold_floor_creation():
    """Test ThresholdFloor instance creation."""
    floor = ThresholdFloor(
        name="test_floor",
        latitude=40.7128,
        longitude=-74.0060,
        tz="America/New_York"
    )
    assert floor.name == "test_floor"
    assert floor.latitude == 40.7128
    assert floor.longitude == -74.0060
    assert floor.tz == "America/New_York"
    assert floor.vault is not None
    assert floor.pegs is not None
    assert len(floor.pegs) == 7

def test_vault_operations():
    """Test ChthonicVault operations."""
    vault = ChthonicVault()
    assert vault.is_open == False
    assert vault.keys == {}
    assert vault.seed_storage == 0
    
    # Test opening vault
    vault.open_gate("test_guardian")
    assert vault.is_open == True
    assert vault.guardian_inside == "test_guardian"
    
    # Test closing vault
    vault.close_gate()
    assert vault.is_open == False
    assert vault.guardian_inside is None
    
    # Test seed storage
    vault.deposit_seed(100)
    assert vault.seed_storage == 100
    
    vault.deposit_seed(50)
    assert vault.seed_storage == 150
    
    # Test withdraw
    withdrawn = vault.withdraw_seed(75)
    assert withdrawn == 75
    assert vault.seed_storage == 75

def test_sweep_operations():
    """Test sweep and phase operations."""
    floor = ThresholdFloor(name="sweep_test", latitude=37.0, longitude=-122.0, tz="America/Los_Angeles")
    
    # Test sweep
    floor.sweep()
    assert floor.is_purified == True
    assert floor.last_swept == "now"
    
    # Test fill operations
    floor.fill(element="water", amount=0.5)
    assert floor.water_level == 0.5
    assert floor.mode == "mirror"
    
    floor.fill(element="wine", amount=0.3)
    assert floor.wine_level == 0.3
    assert floor.mode == "reset"
    
    floor.fill(element="blood", amount=0.2)
    assert floor.blood_level == 0.2
    assert floor.mode == "sacrifice"
    
    # Test drain
    floor.drain()
    assert floor.water_level == 0
    assert floor.blood_level == 0
    assert floor.wine_level == 0

def test_dawn_alignment():
    """Test dawn gate alignment detection."""
    floor = ThresholdFloor(
        name="alignment_test",
        latitude=40.7128,
        longitude=-74.0060,
        tz="America/New_York"
    )
    
    # Configure gatehouse
    floor.configure_gatehouse(40.7128, -74.0060, 0, bearing_deg=90.0)
    
    # Add a gate post
    floor.add_gate_post("east_post", 90.0)
    
    # Test alignment check
    result = floor.check_dawn_gate_alignment(date.today())
    # Just check it runs without error

def test_solar_cycles():
    """Test solar cycle scanning."""
    floor = ThresholdFloor(
        name="cycle_test",
        latitude=40.7128,
        longitude=-74.0060,
        tz="America/New_York"
    )
    
    # Test annual scan
    result = floor.scan_year_for_months(2026)
    assert "year" in result
    assert "months" in result
    assert "first_hits" in result
    assert "timeline" in result
    
    # Test monthly scan
    start_date = date(2026, 1, 1)
    end_date = start_date + timedelta(days=365)
    result = floor.scan_solar_cycle_for_months(start_date, days=365)
    assert "start_date" in result
    assert "months" in result

def test_ecological_state():
    """Test ecological state calculation."""
    floor = ThresholdFloor(name="eco_test", latitude=40.7128, longitude=-74.0060, tz="America/New_York")
    
    state = floor.ecological_state()
    assert "gdd" in state
    assert "recent_rain" in state
    assert "phase" in state
    assert state["phase"] in ["dormant", "shoots", "growth", "fruiting", "mushroom_trigger", "late"]

def test_peg_operations():
    """Test peg index and stepping operations."""
    floor = ThresholdFloor(name="peg_test", latitude=40.7128, longitude=-74.0060, tz="America/New_York")
    
    # Test peg_index
    for az in [0, 90, 180, 270, 359]:
        idx = floor.peg_index(az)
        assert 0 <= idx <= 6
    
    # Test step_peg
    assert floor.step_peg(0, "south") == 1
    assert floor.step_peg(0, "north") == 6
    assert floor.step_peg(1, "south") == 2

def test_get_current_peg_and_month():
    """Test current peg and month detection."""
    floor = ThresholdFloor(
        name="peg_month_test",
        latitude=40.7128,
        longitude=-74.0060,
        tz="America/New_York"
    )
    
    # Configure pegs
    floor.add_gate_post("peg_1", 90.0)
    floor.add_gate_post("peg_2", 180.0)
    floor.add_gate_post("peg_3", 270.0)
    
    result = floor.get_current_peg_and_month(date.today())
    assert result is not None

def test_visual_operations():
    """Test visual state operations."""
    floor = ThresholdFloor(name="visual_test", latitude=40.7128, longitude=-74.0060, tz="America/New_York")
    
    floor.set_visual("idle")
    assert floor.visual_state == "idle"
    assert floor.fire_intensity == 0.1
    
    floor.set_visual("pit")
    assert floor.visual_state == "pit"
    assert floor.fire_intensity == 1.0
    
    floor.set_visual("equinox")
    assert floor.visual_state == "equinox"
    assert floor.fire_intensity == 0.8
    
    # Test unknown state
    floor.set_visual("unknown")
    assert floor.fire_intensity == 0.1  # Reverts to default