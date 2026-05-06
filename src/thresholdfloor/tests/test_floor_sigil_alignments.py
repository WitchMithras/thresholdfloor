from thresholdfloor.floor_sigil import (
    CONJUNCTION_TINT,
    ECLIPSE_TINT,
    ZODIAC_TINTS,
    CelestialAlignmentSnapshot,
    _safe_moonstamp,
    _sign_color,
    tf_sigil,
)
from datetime import datetime, timezone


def test_alignment_snapshot_uses_planet_color_for_single_body():
    snapshot = CelestialAlignmentSnapshot.from_alignments({"mars": "Aries"})

    assert snapshot.bodies_for_sign("Aries") == ("mars",)
    assert snapshot.color_for_sign("Aries") == (255, 69, 0)
    assert not snapshot.is_eclipse("Aries")


def test_alignment_snapshot_uses_conjunction_color_for_stacked_bodies():
    snapshot = CelestialAlignmentSnapshot.from_alignments({
        "venus": "Libra",
        "jupiter": "Libra",
    })

    assert snapshot.bodies_for_sign("Libra") == ("venus", "jupiter")
    assert snapshot.color_for_sign("Libra") == CONJUNCTION_TINT


def test_alignment_snapshot_marks_eclipse_like_node_stack():
    snapshot = CelestialAlignmentSnapshot.from_alignments({
        "sun": "Taurus",
        "moon": "Taurus",
        "north_node": "Taurus",
    })

    assert snapshot.color_for_sign("Taurus") == ECLIPSE_TINT
    assert snapshot.is_eclipse("Taurus")


def test_sign_color_falls_back_to_plain_zodiac_color_without_alignment():
    snapshot = CelestialAlignmentSnapshot.from_alignments({})

    fill, glow = _sign_color("Leo", 180, snapshot)

    assert fill == ZODIAC_TINTS["Leo"] + (240,)
    assert glow is None


def test_safe_moonstamp_always_returns_filename_token(monkeypatch):
    monkeypatch.setattr("thresholdfloor.floor_sigil.moonstamp", lambda: (_ for _ in ()).throw(ValueError("bad ledger")))

    stamp = _safe_moonstamp()

    assert stamp.isdigit()
    assert len(stamp) == 14


def test_tf_sigil_writes_png_even_when_moonstamp_fails(monkeypatch, tmp_path):
    class FakeAether:
        def sign(self, _observed_at, body):
            return "Aries" if body == "sun" else None

    class FakeFloor:
        af = FakeAether()
        current_phase = "Nigredo"

        def now(self):
            return datetime(2026, 5, 6, tzinfo=timezone.utc)

        def observe(self, _observed_at=None):
            return {"sun": {"alt_apparent": 45.0, "azimuth": 180.0}}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("thresholdfloor.floor_sigil.moonstamp", lambda: (_ for _ in ()).throw(ValueError("bad ledger")))

    output_path = tf_sigil(FakeFloor(), size=256)

    assert output_path is not None
    assert (tmp_path / output_path).is_file()
