from thresholdfloor.floor_sigil import _phase_outer_ring_color


class DummyFloor:
    def __init__(self, current_phase):
        self.current_phase = current_phase


def test_outer_ring_color_uses_current_phase_color():
    assert _phase_outer_ring_color(DummyFloor("Rubedo")) == (190, 24, 55, 180)


def test_outer_ring_color_falls_back_when_phase_is_missing():
    assert _phase_outer_ring_color(DummyFloor(None)) == (180, 150, 255, 180)
