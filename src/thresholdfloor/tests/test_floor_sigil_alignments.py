from thresholdfloor.floor_sigil import (
    CONJUNCTION_TINT,
    ECLIPSE_TINT,
    ZODIAC_TINTS,
    CelestialAlignmentSnapshot,
    _sign_color,
)


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
