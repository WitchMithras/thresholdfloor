# ThresholdFloor

*ThresholdFloor* is a geolocated simulation of light, shadow, and sky.

It answers a very old question:

> *If I stand here, what is the sky doing right now?*

Where *MoonTime* tracks cycles, and *AetherField* tracks positions,
ThresholdFloor brings those movements down to Earth — into light, into shadow, into place.

---

## 🌍 What It Does

ThresholdFloor creates a virtual “floor” at a real location on Earth and lets you observe:

* ☀️ The Sun’s angle across the sky
* 🌗 The shifting length and direction of shadows
* 🌅 Sunrise and sunset behavior
* 🌞 Seasonal turning points (equinoxes, solstices)
* 🌌 Zodiac regions above and below the horizon

It turns celestial motion into something physical:

> light touching ground

---

## 🧭 Core Idea

In many ancient systems, knowledge of time and season did not come from clocks.

It came from:

* shadows on the ground
* the angle of light
* where the sun rose and set

ThresholdFloor recreates that perspective computationally.

Instead of asking:

> *What time is it?*

You can ask:

> *Where is the light?*

---

## 🚀 Quick Example

```python
from thresholdfloor import ThresholdFloor as tf

def test_one():

    tfloor = tf(
        name="meow meow tehran",
        latitude=35.6892,
        longitude=51.3890,
        tz="Asia/Tehran"
    )

    print(tfloor.get_phase())  # Shadow-based phase

    tfloor.sigil()  # Visual representation of current state

    hkfloor = tf(
        "meow meow hongkong",
        22.3027,
        114.1772,
        "Asia/Hong_Kong",
        elevation_m=958
    )

    sigil = hkfloor.sigil(show=False)

    print(hkfloor.get_sunrise())  # Sunrise angle

    bfloor = tf(
        "meow meow beijing",
        39.9075,
        116.3972,
        "Asia/Shanghai",
        elevation_m=50
    )

    print(bfloor.as_above())  # Zodiac above horizon
    print(bfloor.so_below())  # Zodiac below horizon

    tofloor = tf(
        "meow meow tokyo",
        35.68972,
        139.69222,
        "Asia/Tokyo"
    )

    print(tofloor.now())      # Local MoonTime
    print(tofloor.observe())  # Current solar geometry
```

---

## 🌞 Solar Cycle Example

```python
def test_two():

    jfloor = tf(
        "Jericho",
        latitude=31.871,
        longitude=35.443,
        tz="Asia/Jerusalem"
    )

    # Configure observation point
    jfloor.configure_gatehouse(31.8720, 35.4440, -245.0, bearing_deg=90.7)

    # Compute solstice anchors
    summer, winter = jfloor.compute_solstice_anchors()

    # Lay out solar markers across the year
    jfloor.auto_layout_gate_posts_across_solar_range(
        start_date=winter,
        days=366,
        num_pegs=7,
    )

    # Scan solar cycle into months
    result = jfloor.scan_solar_cycle_for_months(winter, days=366)

    for m in range(1, 13):
        print(f"Month {m}: first hit on {result['first_hits'][m]}")
```

---

## 🧩 Core Concepts

### Floor

A *Floor* is a fixed location defined by:

* latitude
* longitude
* timezone
* optional elevation

It represents a real place on Earth.

---

### Observation

```python
tfloor.observe()
```

Returns the current solar position relative to the floor:

* altitude
* azimuth
* light direction

---

### Phase

```python
tfloor.get_phase()
```

A shadow-based phase derived from solar geometry.

---

### Sigil

```python
tfloor.sigil()
```

Generates a visual encoding of the current state of the floor.

This is an evolving feature and may expand in future releases.

---

### Horizon Mapping

```python
tfloor.as_above()
tfloor.as_below()
```

Maps zodiac regions relative to the local horizon.

---

### Local Time

```python
tfloor.now()
```

Returns the current moment expressed relative to the floor.

---

## 🌌 Design Philosophy

ThresholdFloor is built around a simple inversion:

Modern systems:

* abstract time
* global reference
* detached observation

ThresholdFloor:

* grounded time
* local reference
* embodied observation

It does not ask you to synchronize with a global clock.

It lets you observe what is happening *where you are*.

---

## 🧬 Ecosystem

ThresholdFloor builds on:

* `moontime` → temporal cycles
* `aetherfield` → celestial positions

Together they form:

* **Time** → MoonTime
* **Sky** → AetherField
* **Ground** → ThresholdFloor

---

## 🧪 Status

Alpha release.

Core functionality is in place, but APIs and visual systems (such as sigils) are still evolving.

---

## 🕯️ Closing Note

There was a time when people did not need instruments to understand the day.

They could look at a shadow and know:

* how far the sun had traveled
* what season they were in
* where they stood in the cycle

ThresholdFloor is an attempt to rebuild that intuition.

Not by replacing modern systems —

but by letting light and shadow speak again.