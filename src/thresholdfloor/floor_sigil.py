from pydub.generators import WhiteNoise
import math
import random
import io, os, tempfile
from math import radians
from datetime import timedelta
from moontime import moonstamp, MoonTime
from .bundle import _bundle_key_with_ext, _maybe_write_temp_png, bundle_put_bytes, _bundle_load, ASSET_BYTES, bundle_put_image, _resolve_asset_to_pil
from aetherfield import rotated_zodiac

TK_EXISTS = False
PIL_EXISTS = False

try:
    import tkinter as tk
    TK_EXISTS = True
except Exception:
    pass
try:
    from PIL import Image, ImageOps, ImageChops, ImageOps, ImageFilter, ImageDraw, ImageFont, ImageTk, ImageEnhance, ImageColor
    PIL_EXISTS = True
except Exception:
    pass

DEFAULT_OUTER_RING_COLOR = (180, 150, 255, 180)
PHASE_COLOR_RGBA = {
    "black": (0, 0, 0, 90),
    "white": (170, 170, 170, 170),
    "yellow-gold": (170, 100, 40, 90),
    "crimson-red": (190, 12, 20, 90),
}


def _coerce_ring_color(color, default=DEFAULT_OUTER_RING_COLOR):
    if isinstance(color, str):
        keyed = color.strip().lower().replace("_", "-").replace(" ", "-")
        if keyed in PHASE_COLOR_RGBA:
            return PHASE_COLOR_RGBA[keyed]

        image_color = globals().get("ImageColor")
        if image_color is not None:
            try:
                r, g, b = image_color.getrgb(color)
                return (r, g, b, default[3])
            except ValueError:
                return default

    if isinstance(color, (tuple, list)) and len(color) in (3, 4):
        values = tuple(int(c) for c in color)
        if len(values) == 3:
            return (*values, default[3])
        return values

    return default


def _phase_outer_ring_color(floor, default=DEFAULT_OUTER_RING_COLOR):
    phase = getattr(floor, "current_phase", None)
    if not phase and hasattr(floor, "get_phase"):
        try:
            phase = floor.get_phase()
        except Exception:
            phase = None

    if not phase:
        return default

    COLORS = {
        "Nigredo": "black",
        "Albedo": "white",
        "Citrinitas": "yellow-gold",
        "Rubedo": "crimson-red",
    }

    return _coerce_ring_color(COLORS.get(phase), default)

SIGNS = {
    '♈': 'Aries',
    '♉': 'Taurus',
    '♊': 'Gemini',
    '♋': 'Cancer',
    '♌': 'Leo',
    '♍': 'Virgo',
    '♎': 'Libra',
    '♏': 'Scorpio',
    '♐': 'Sagittarius',
    '♑': 'Capricorn',
    '♒': 'Aquarius',
    '♓': 'Pisces'
}

TREE_SPRITE_MAP = {
    'Ash': "tree",
    'Birch': "tree_pale_skinny",
    'Oak': "tree",
    'Elm': "tree",
    'Beech': "tree",
    'Alder': "shrub",
    'Willow': "tree_dark",
    'Yew': "tree_dark",
    'Spruce': "tree_dark_skinny",
    'Pine': "tree_pale_skinny",
    'Elder': "shrub",
    'Apple': "tree"
}

TREE_LOOKUP = {
    'ᚠ': 'Elder',
    'ᚢ': 'Birch',
    'ᚦ': 'Hawthorn', 
    'ᚨ': 'Ash', 
    'ᚱ': 'Oak', 
    'ᚲ': 'Pine', 
    'ᚷ': 'Elm', 
    'ᚹ': 'Ash', 
    'ᚺ': 'Ash', 
    'ᚾ': 'Beech', 
    'ᛁ': 'Alder', 
    'ᛃ': 'Oak', 
    'ᛇ': 'Yew', 
    'ᛈ': 'Beech', 
    'ᛉ': 'Elm', 
    'ᛊ': 'Oak', 
    'ᛏ': 'Oak', 
    'ᛒ': 'Birch', 
    'ᛖ': 'Ash', 
    'ᛗ': 'Ash', 
    'ᛚ': 'Willow', 
    'ᛜ': 'Apple', 
    'ᛞ': 'Spruce', 
    'ᛟ': 'Pine',
}

ZODIAC_TINTS = {
    "Aries": (255, 60, 60),      # Red
    "Taurus": (120, 200, 80),    # Green
    "Gemini": (180, 180, 255),   # Pale blue
    "Cancer": (150, 150, 180),   # Silver-gray
    "Leo": (255, 200, 80),       # Gold
    "Virgo": (180, 255, 180),    # Soft green
    "Libra": (200, 180, 255),    # Lavender
    "Scorpio": (100, 50, 150),   # Deep purple
    "Sagittarius": (255, 140, 0),# Orange
    "Capricorn": (90, 90, 90),   # Earthy stone
    "Aquarius": (60, 180, 255),  # Sky blue
    "Pisces": (100, 200, 255)    # Ocean blue
}
PLANET_TINTS = {
    "Mercury": (200, 200, 255),   # Pale blue
    "Venus": (255, 192, 203),     # Soft pink
    "Earth": (100, 200, 100),     # Green-blue earthy tone
    "Mars": (255, 69, 0),         # Aggressive red
    "Jupiter": (255, 215, 0),     # Golden yellow
    "Saturn": (210, 180, 140),    # Sandy beige
    "Uranus": (173, 216, 230),    # Icy blue
    "Neptune": (70, 130, 180),    # Deep ocean blue
    "Moon": (220, 220, 220),      # Silvery gray
    "Sun": (255, 140, 0),          # Fiery orange
}

HERMETIC_METALS = {
    "moon":        (192, 192, 192),  # Silver
    "venus":       (184, 115, 51),   # Copper
    "sun":         (255, 215, 0),    # Gold
    "mercury":     (220, 220, 220),  # Quicksilver (silvery gray)
    "jupiter":     (193, 204, 222),  # Tin (pale blue-gray)
    "bronze":      (205, 127, 50),   # Bronze (close enough)
    "electrum":    (239, 206, 74),   # Electrum (gold-silver alloy)
    "saturn":      (105, 105, 105),  # Lead (dark gray)
    "mars":        (120, 120, 120),  # Iron (gray)
    "steel":       (140, 140, 140),  # Steel (light gray)
}

COLOR_PALLET = {}
for d in (ZODIAC_TINTS, PLANET_TINTS, HERMETIC_METALS):
    COLOR_PALLET.update(d)

asset_path = "assets.png"

try:
    _bundle_load()
    _bytes = ASSET_BYTES.get(asset_path) or None
    if _bytes:
        SHEET = Image.open(io.BytesIO(_bytes))
    else:
        SHEET = Image.open(asset_path)
        bundle_put_image(asset_path, SHEET, fmt="PNG")
except Exception as e:
    print(e)
    SHEET = Image.new("RGBA", (800, 800), (0, 0, 0, 0))

ASSET_PATHS = {
    "tree": SHEET.crop((609, 2, 670, 62)),
    "shrub": SHEET.crop((513, 5, 543, 28)),
    "tree_pale_skinny": SHEET.crop((672, 0, 704, 60)),
    "tree_dark_skinny": SHEET.crop((256, 771, 288, 831)),
    "tree_dark": SHEET.crop((448, 706, 510, 766)),
}

sprite_lookup = {
    rune: TREE_SPRITE_MAP.get(tree_type, "tree")
    for rune, tree_type in TREE_LOOKUP.items()
}

def overlay_shadow_tree(base_img, rune, cx, cy, azimuth, altitude, size=64):
    import math
    #cx, cy = cx + size, cy + size
    sprite_key = sprite_lookup.get(rune)
    if not sprite_key:
        return base_img

    sprite = ASSET_PATHS.get(sprite_key)
    if isinstance(sprite, str):
        try:
            sprite = Image.open(sprite).convert("RGBA")
        except:
            return base_img
    elif sprite:
        sprite = sprite.copy()
    else:
        return base_img

    # Resize
    sprite = sprite.resize((size, size), Image.LANCZOS)

    # 🌑 Darken
        # 1. Convert RGB to grayscale
    r, g, b, a = sprite.split()

    #rgb = Image.merge("RGB", (r, g, b))

    #gray = ImageOps.grayscale(rgb)

        # 2. Apply ash tint (charcoal hues)
    #tinted = ImageOps.colorize(gray, black=(30, 30, 30), white=(80, 80, 80)).convert("RGBA")


    sprite = ImageEnhance.Brightness(sprite).enhance(0.1)

    # 🌫 Optional blur
    sprite = sprite.filter(ImageFilter.GaussianBlur(1.1))

    # 🌞 Clamp altitude
    alt = max(altitude, 2)
    alt_rad = math.radians(alt)

    # angle difference from the "broadside" shadow direction (180° in your case)
    delta = abs((azimuth - 180 + 180) % 360 - 180)

    # cosine falloff (0° = full width, 90° = very thin)
    falloff = abs(math.cos(math.radians(delta)))

    # soften it so it doesn’t collapse too fast
    falloff = falloff ** 1.5   # tweak 1.2–2.5

    # clamp to your minimum thickness
    min_scale = 0.09
    scale = min_scale + (1 - min_scale) * falloff

    new_w = int(size * scale)
      # 🌿 Stretch length based on altitude (LOW sun = LONG shadow)
    stretch = min(6.0, 1 / math.tan(alt_rad))

    inc = size * stretch
    new_h = int(size + inc)  # flatten vertically
    sprite_offset = -90
    sprite = sprite.resize((new_w, new_h), Image.LANCZOS)

    # 🧭 Rotate so it lays away from sun
    angle = (azimuth - 90) % 360
    diff = 0
    if azimuth > 180: 
        diff = (azimuth - 180)
        angle = (180 - diff)
    elif azimuth < 180: 
        diff = (180 - azimuth)
        angle = (180 + diff)

    sprite = sprite.rotate(angle, resample=Image.BICUBIC, expand=True)

    # 🎯 Anchor correction (THIS is the magic)
    w, h = sprite.size

    # We want the "base" of the tree to stay at (cx, cy)
    # After rotation, base ≈ center-bottom of the image
    if azimuth >= 180:

        x = cx - w * min(1, diff // 20)

        #y = cy

    else:
        x = cx

        #y = cy - w
    #x = cx

    y = cy


    base_img.paste(sprite, (int(x), int(y)), sprite)
    return base_img

def overlay_tree_sprite(base_img, rune, position=None, size=48):
    """Overlay the tree sprite mapped to ``rune`` onto ``base_img``.

    Parameters
    ----------
    base_img : PIL.Image.Image
        Image to draw onto.
    rune : str
        Rune character used to look up the sprite.
    position : tuple[int, int] | None
        Optional ``(x, y)`` coordinates.  If ``None``, bottom-right corner
        is used.
    size : int
        Width and height of the sprite after resizing.

    Returns
    -------
    PIL.Image.Image
        Image with the sprite composited.
    """
    sprite_key = sprite_lookup.get(rune)
    if not sprite_key:
        return base_img

    sprite = ASSET_PATHS.get(sprite_key)
    if isinstance(sprite, str):
        try:
            sprite = Image.open(sprite).convert("RGBA")
        except FileNotFoundError:
            return base_img
    elif sprite:
        sprite = sprite.copy()
    else:
        return base_img

    sprite = ImageEnhance.Brightness(sprite).enhance(0.6)

    sprite = sprite.resize((size, size), Image.LANCZOS)
    if position is None:
        x = base_img.width - size - 10
        y = base_img.height - size - 10
    else:
        x, y = position

    base_img.paste(sprite, (int(x), int(y)), sprite)
    return base_img

def _load_motto_font(font_size=24):
    preferred_fonts = [
        #"Hermissoul-Regular.ttf",
        "CinzelDecorative-Regular.ttf",
        "DejaVuSans.ttf",
    ]

    for font_path in preferred_fonts:
        try:
            _bundle_load()
            _bytes = ASSET_BYTES.get(font_path)

            if _bytes:
                return ImageFont.truetype(io.BytesIO(_bytes), font_size)

            with open(font_path, "rb") as f:
                raw_bytes = f.read()

            bundle_put_bytes(font_path, raw_bytes)
            return ImageFont.truetype(io.BytesIO(raw_bytes), font_size)

        except Exception:
            continue

    return ImageFont.load_default()

def _load_sigil_font(font_size=36):
    font_path = "DejaVuSans.ttf"

    try:
        _bundle_load()
        _bytes = ASSET_BYTES.get(font_path)

        if _bytes:
            return ImageFont.truetype(io.BytesIO(_bytes), font_size)

        with open(font_path, "rb") as f:
            raw_bytes = f.read()

        bundle_put_bytes(font_path, raw_bytes)
        return ImageFont.truetype(io.BytesIO(raw_bytes), font_size)

    except Exception as e:
        print(e)
        return ImageFont.load_default()


def _draw_sigil_background(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.pieslice((0, 0, size, size), start=0, end=180, fill=(10, 10, 35, 255))
    draw.pieslice((0, 0, size, size), start=180, end=360, fill=(20, 15, 10, 255))
    return img


def _draw_sigil_tree_axis(img, cx, cy, size=82):
    rune = "\u16a8"
    overlay_tree_sprite(
        img,
        rune,
        position=(cx - (size / 2), cy - size),
        size=size
    )
    return img


def _draw_sigil_glyphs(img, floor, font, cx, cy, r, observed_at):
    try:
        beam = floor.observe(observed_at)
        sun = beam.get("sun")

        if not sun:
            return None, None

        alt = sun["alt_apparent"]
        az = sun["azimuth"]
        sign = floor.af.sign(observed_at, "sun")
        lon = az
        signs = rotated_zodiac(sign)

        for sign in signs:
            theta = math.radians(lon)

            x = cx + r * -math.sin(theta)
            y = cy + r * math.cos(theta)

            glyph = next((k for k, v in SIGNS.items() if v == sign), '?')

            dx = x - cx
            dy = y - cy
            mag = math.hypot(dx, dy) or 1
            ox = x + (dx / mag) * 12
            oy = y + (dy / mag) * 12

            # Above horizon bright
            #if 90 < lon < 270:
                #color = COLOR_PALLET.get(sign, (200, 200, 255, 240))
            #else:
                #color = tuple(int(c * 0.4) for c in COLOR_PALLET.get(sign, (200, 200, 255, 240)))
            
            # All bright    
            #color = COLOR_PALLET.get(sign, (200, 200, 255, 240))
            
            # All dark
            color = tuple(int(c * 0.4) for c in COLOR_PALLET.get(sign, (200, 200, 255, 240)))

            glyph_img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            glyph_draw = ImageDraw.Draw(glyph_img)

            bbox = font.getbbox(glyph)
            gw, gh = bbox[2] - bbox[0], bbox[3] - bbox[1]

            glyph_draw.text(
                ((64 - gw) / 2, (64 - gh) / 2),
                glyph,
                font=font,
                fill=color
            )

            angle = -math.degrees(theta)
            angle -= 180

            glyph_img = glyph_img.rotate(angle, resample=Image.BICUBIC, expand=True)

            gw2, gh2 = glyph_img.size
            px = ox - gw2 / 2
            py = oy - gh2 / 2

            img.paste(glyph_img, (int(px), int(py)), glyph_img)
            lon += 30

        return alt, az
    except Exception as e:
        print(e)
        return None, None


def _draw_sigil_shadow(img, cx, cy, alt, az, size=82):
    if alt is not None and az is not None and alt > 0 and 90 < az < 270:
        overlay_shadow_tree(
            img,
            rune="\u16c7",
            cx=cx,
            cy=cy,
            azimuth=az,
            altitude=alt,
            size=size
        )
    return img

def _polar(cx, cy, radius, angle_deg):
    theta = math.radians(angle_deg)
    return (
        cx + radius * -math.sin(theta),
        cy + radius * math.cos(theta),
    )


def _draw_sigil_ticks(img, cx, cy, r, every=5, major_every=30):
    draw = ImageDraw.Draw(img)

    outer = r * 1.33
    minor_len = r * 0.025
    major_len = r * 0.055

    for deg in range(0, 360, every):
        is_major = deg % major_every == 0
        length = major_len if is_major else minor_len
        width = 2 if is_major else 1

        x1, y1 = _polar(cx, cy, outer - length, deg)
        x2, y2 = _polar(cx, cy, outer, deg)

        draw.line(
            (x1, y1, x2, y2),
            fill=(150, 115, 70, 150),
            width=width,
        )

    return img


def _draw_diamond(img, cx, cy, radius, angle_deg, scale=4, fill=(210, 165, 90, 210)):
    draw = ImageDraw.Draw(img)
    x, y = _polar(cx, cy, radius, angle_deg)

    pts = [
        (x, y - scale),
        (x + scale, y),
        (x, y + scale),
        (x - scale, y),
    ]

    draw.line(pts + [pts[0]], fill=fill, width=1)
    return img


def _draw_motto_brackets(img, cx, cy, r):
    ornament_r = r * 0.84

    # Bracket ornaments around TEMPUS FUGIT
    _draw_diamond(img, cx, cy, ornament_r, 38, scale=3)
    _draw_diamond(img, cx, cy, ornament_r, 52, scale=3)

    # Bracket ornaments around FESTINA LENTE
    _draw_diamond(img, cx, cy, ornament_r, 310, scale=3)
    _draw_diamond(img, cx, cy, ornament_r, 320, scale=3)

    # Small keel mark at bottom center
    _draw_diamond(img, cx, cy, ornament_r, 0, scale=4)

    return img


def _draw_sigil_ornaments(img, cx, cy, size, r):
    _draw_sigil_ticks(img, cx, cy, r)
    _draw_motto_brackets(img, cx, cy, r)
    return img

def _draw_curved_text(
    img,
    cx,
    cy,
    radius,
    text,
    center_angle,
    font,
    fill=(235, 205, 150, 235),
    stroke_fill=(20, 15, 10, 210),
    tracking_deg=2.0,
    reverse=False,
    rotation_offset=0,
    glyph_box=96,
):
    """
    Draw text along a circular arc with adjustable letter spacing.

    center_angle uses your south-facing clock convention:
      0°   = bottom / south
      90°  = left
      180° = top
      270° = right

    tracking_deg increases spacing between letters.
    reverse flips word order if the text reads backward.
    rotation_offset can be set to 180 if the letters face inward/upside down.
    """
    if not text:
        return img

    draw = ImageDraw.Draw(img)

    chars = list(text[::-1] if reverse else text)

    def _char_width(ch):
        try:
            return font.getlength(ch)
        except Exception:
            bb = font.getbbox(ch)
            return bb[2] - bb[0]

    # Convert approximate pixel width into degrees on this radius.
    circumference = 2 * math.pi * radius
    px_to_deg = 360.0 / circumference

    widths_px = [_char_width(ch) for ch in chars]
    widths_deg = [w * px_to_deg for w in widths_px]

    total_arc = sum(widths_deg) + tracking_deg * max(0, len(chars) - 1)
    cursor = center_angle - total_arc / 2

    for ch, ch_arc in zip(chars, widths_deg):
        angle_deg = cursor + ch_arc / 2
        cursor += ch_arc + tracking_deg

        theta = math.radians(angle_deg)

        x = cx + radius * -math.sin(theta)
        y = cy + radius * math.cos(theta)

        glyph = Image.new("RGBA", (glyph_box, glyph_box), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glyph)

        bb = font.getbbox(ch)
        gw = bb[2] - bb[0]
        gh = bb[3] - bb[1]

        gx = (glyph_box - gw) / 2
        gy = (glyph_box - gh) / 2

        if stroke_fill:
            for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                gd.text(
                    (gx + ox, gy + oy),
                    ch,
                    font=font,
                    fill=stroke_fill,
                )

        gd.text(
            (gx, gy),
            ch,
            font=font,
            fill=fill,
        )

        # Your current setup seems to like this orientation.
        # If letters face inward/upside-down, set rotation_offset=180.
        
        glyph = glyph.rotate(
            -angle_deg + rotation_offset,
            resample=Image.BICUBIC,
            expand=True,
        )
        #if reverse:
            #glyph = ImageOps.mirror(glyph)

        ww, hh = glyph.size
        img.alpha_composite(glyph, (int(x - ww / 2), int(y - hh / 2)))

    return img

def _draw_sigil_inscribe(img, cx, cy, size, r):
    try:
        motto_font = _load_motto_font(max(8, int(size * 12 / 400)))
        motto_r = r * 0.72
        tracking_deg=1.8
        latin_take = "LENTE"
        latin_late = "FESTINA"
        #latin_take = "FESTINA LENTE"
        #latin_late = "TEMPUS FUGIT"
        #latin_late = "SERIUS EST"
        # Bottom-right-ish
        _draw_curved_text(
            img,
            cx,
            cy,
            motto_r,
            latin_take,
            center_angle=315,
            #arc_degrees=42,
            font=motto_font,
            fill=(180, 150, 100, 220),
            stroke_fill=(20, 15, 10, 210),
            reverse=True,
            tracking_deg=tracking_deg,
            rotation_offset=0
        )
        # Southwest
        _draw_curved_text(
            img,
            cx,
            cy,
            motto_r,
            latin_late,
            center_angle=45,
            #arc_degrees=34,
            font=motto_font,
            fill=(180, 150, 100, 220),
            stroke_fill=(20, 15, 10, 210),
            reverse=True,
            tracking_deg=tracking_deg,
            rotation_offset=0
        )

        return img

    except Exception as e:
        print(e)
        return img

def _draw_vestal_ring(
    img,
    cx,
    cy,
    phase,
    waxing=True,
    r=100,
    color=(180, 150, 255, 180),
    width=3,
):
    """
    Draw a lunar phase ring.

    phase:
        0.0 = new moon
        1.0 = full moon

    waxing:
        True  = right-side illumination
        False = left-side illumination
    """

    draw = ImageDraw.Draw(img)

    # Convert phase into angular sweep.
    sweep = max(0.0, min(1.0, phase)) * 180.0

    if waxing:
        # Right side grows upward/downward from south.
        start = 0 - sweep
        end   = 0 + sweep

    else:
        # Left side.
        start = 180 - sweep
        end   = 180 + sweep

    bbox = (
        cx - r,
        cy - r,
        cx + r,
        cy + r,
    )

    draw.arc(
        bbox,
        start=start,
        end=end,
        fill=color,
        width=width,
    )

    return img

def _render_clock_sigil_frame(floor, observed_at, size=512, ornaments=True, inscription=True, glyph=True, tree=True, shadow=True, vestal=False):
    try:
        img = _draw_sigil_background(size)
        cx, cy = size // 2, size // 2
        tree_size = max(1, int(size * (82 / 400)))
        font = _load_sigil_font(max(1, int(size * (36 / 400))))
        r = int((size // 2) * 0.75)

        alt, az = _draw_sigil_glyphs(img, floor, font, cx, cy, r, observed_at)
        if shadow:
            _draw_sigil_shadow(img, cx, cy, alt, az, size=tree_size)
        if tree:
            _draw_sigil_tree_axis(img, cx, cy, size=tree_size)

        if ornaments:
            _draw_sigil_ornaments(img, cx, cy, size, r)
        if inscription:
            _draw_sigil_inscribe(img, cx, cy, size=size, r=r)
        if vestal:
            mt = floor.now_mt()
            def infer_waxing() -> bool | None:
                phase = getattr(mt, "moon_phase", None) or ""
                p = str(phase).lower()
                if p.startswith("wax"):
                    return True
                if p.startswith("wan"):
                    return False
                if "first quarter" in p:
                    return True
                if "last quarter" in p:
                    return False
                return None

            waxing = infer_waxing()
            illum_raw = mt.moon_illum / 100

            if illum_raw > 100:
                illum = illum_raw / 1000.0
            else:
                illum = illum_raw / 100.0
            moon_phase_fraction = max(0.0, min(1.0, float(illum)))

            _draw_vestal_ring(
                img,
                cx,
                cy,
                r=r * 1.15,
                color=_phase_outer_ring_color(floor),
                phase=moon_phase_fraction,
                waxing=waxing
            )

        return img
    except Exception as e:
        print(e)
        return img

def _clock_frame_duration_seconds(start, frame_count, moontime_hours):
    try:
        mt = MoonTime.from_datetime(start)
        if getattr(mt, "hour_length_seconds", None):
            return (mt.hour_length_seconds * moontime_hours) / frame_count
    except Exception:
        pass

    return (24 * 60 * 60) / frame_count


def tf_sigil(floor, size=400):
    if not PIL_EXISTS:
        return None

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = size // 2, size // 2
    r = int((size // 2) * 0.75)

    # Fonts
    font_path = "DejaVuSans.ttf"

    try:
        _bundle_load()
        _bytes = ASSET_BYTES.get(font_path)

        if _bytes:
            # Load from bundled bytes
            font = ImageFont.truetype(io.BytesIO(_bytes), 36)

        else:
            # Read file as raw bytes first
            with open(font_path, "rb") as f:
                raw_bytes = f.read()

            # Store raw bytes in bundle
            bundle_put_bytes(font_path, raw_bytes)

            # Create font from those same bytes
            font = ImageFont.truetype(io.BytesIO(raw_bytes), 36)

    except Exception as e:
        print(e)
        font = ImageFont.load_default()

    # 🌍 Horizon split (sky / ground)
    draw.pieslice((0, 0, size, size), start=0, end=180, fill=(10, 10, 35, 255))   # ground
    draw.pieslice((0, 0, size, size), start=180, end=360, fill=(20, 15, 10, 255)) # sky

    # Horizon line
    #draw.line((0, cy, size, cy), fill=(180, 120, 80, 180), width=2)
    # 🌞 Shadow using floor.observe()
    try:
        beam = floor.observe()
        sun = beam.get("sun")

        if sun:
            alt = sun["alt_apparent"]
            az  = sun["azimuth"]

        sign = floor.af.sign(floor.now(), "sun")
        lon = az
        signs = rotated_zodiac(sign)

        for sign in signs:

            theta = math.radians(lon)

            x = cx + r * -math.sin(theta)
            y = cy + r * math.cos(theta)

            glyph = next((k for k, v in SIGNS.items() if v == sign), '?')

            # Offset slightly outward
            dx = x - cx
            dy = y - cy
            mag = math.hypot(dx, dy) or 1
            ox = x + (dx / mag) * 12
            oy = y + (dy / mag) * 12

            bbox = font.getbbox(glyph)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]

            # Bright above, dim below
            if 90 < lon < 270:
                color = COLOR_PALLET.get(sign, (200, 200, 255, 240))
            else:
                color = tuple(int(c * 0.4) for c in COLOR_PALLET.get(sign, (200, 200, 255, 240)))

            # Create glyph image
            glyph_img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            glyph_draw = ImageDraw.Draw(glyph_img)

            bbox = font.getbbox(glyph)
            gw, gh = bbox[2] - bbox[0], bbox[3] - bbox[1]

            glyph_draw.text(
                ((64 - gw) / 2, (64 - gh) / 2),
                glyph,
                font=font,
                fill=color
            )

            # 🧭 Rotation angle (THIS is the magic)
            angle = -math.degrees(theta)



            # Optional: slight outward tilt (inscription like)
            angle -= 180

            # Optional: keep text upright-ish (less chaos)
            #if 90 < angle % 360 < 270:
            #    angle += 180

            # Rotate
            glyph_img = glyph_img.rotate(angle, resample=Image.BICUBIC, expand=True)

            # Paste centered at (ox, oy)
            gw2, gh2 = glyph_img.size
            px = ox - gw2 / 2
            py = oy - gh2 / 2

            img.paste(glyph_img, (int(px), int(py)), glyph_img)
            lon += 30

    except Exception as e:
        print(e)  
    # 🌳 Tree (axis)
    try:
        if not floor.current_phase:
            phase = floor.get_phase()
        else:
            phase = floor.current_phase
        if not phase == "Nigredo":
            if phase == "Albedo":
                rune, dark_rune = 'ᛁ', 'ᛁ'
            elif phase == "Citrinitas":
                rune, dark_rune = 'ᚲ', 'ᛞ'
            elif phase == "Rubedo":
                rune, dark_rune = 'ᚨ', 'ᛇ'
            rune, dark_rune = 'ᚨ', 'ᛇ'
            #rune, dark_rune = 'ᚲ', 'ᛞ'

            size = 82
            overlay_tree_sprite(
                img,
                rune,
                position=(cx - (size / 2), cy - size),
                size=size
            )


            if alt > 0 and 90 < az < 270: # Over the horizon and projecting downwards
            ## TOO HEAVY
            #if alt > floor.sun_delay().get("angle") and 90 < az < 270: # Over the horizon and projecting downwards 
                overlay_shadow_tree(
                    img,
                    rune=dark_rune,
                    cx=cx,
                    cy=cy,
                    azimuth=az,
                    altitude=alt,
                    size=size
                )
    except Exception as e:
        pass
    # Outer ring
    #draw.ellipse(
    #    (cx - r, cy - r, cx + r, cy + r),
    #    outline=(180, 150, 255, 180),
    #    width=3
    #)
        # Save final emotional disaster
    full_path = f"heather_sigils/tf_sig_{moonstamp()}.png"

    output_path = full_path.replace(".png", "_heathered.png")
    bundle_put_image(output_path, img, fmt="PNG")
    #show_sigil(output_path)
    return output_path


def show_sigil(image_key: str, floor=None) -> str:
    """
    Display a sigil animation from a bundle-aware key or file path,
    and save the resulting GIF both to disk (as animate_sigil returns)
    and into the asset bundle under the same logical key with .gif.
    Returns the logical bundle key to the GIF.
    """
    # Load image (bundle-first)
    img = _resolve_asset_to_pil(image_key).convert("RGBA")
    img = img.resize((512, 512), Image.NEAREST)

    # Tk setup
    root = tk.Tk()
    root.title("Heather's Latest Moon Ritual")
    canvas = tk.Canvas(root, width=512, height=512, highlightthickness=0, bd=0)
    canvas.pack()

    tk_img = ImageTk.PhotoImage(img)
    # keep a reference so Tk doesn't GC it
    canvas._sigil_img_ref = tk_img
    canvas.create_image(0, 0, anchor="nw", image=tk_img)

    # Make sure animate_sigil can read from a real file path
    local_png_path = _maybe_write_temp_png(image_key)

    # Run your existing animator (expects a canvas + path)
    gif_path = animate_sigil(canvas, local_png_path, floor=floor)

    # Persist GIF into the bundle under a stable logical key
    try:
        with open(gif_path, "rb") as gf:
            gif_bytes = gf.read()
        gif_key = _bundle_key_with_ext(image_key, ".gif")
        bundle_put_bytes(gif_key, gif_bytes, also_by_basename=True)
    except Exception:
        # If anything goes sideways, still try to provide a sensible key
        gif_key = _bundle_key_with_ext(image_key, ".gif")

    # Start UI loop (blocking until window close)
    root.mainloop()

    # Return the logical bundle key (not the temp disk path)
    return gif_key

def sigil_corruptor(img, passes=3, intensity=2):
    img = img.convert("RGBA")
    base = img.copy()

    # 1. Glow pass
    for _ in range(passes):
        base = base.filter(ImageFilter.GaussianBlur(intensity))
        img = Image.blend(img, base, 0.5)

    # 2. Static pass
    pixels = img.load()
    width, height = img.size
    for _ in range(1000):  # static specks
        x = np.random.randint(0, width)
        y = np.random.randint(0, height)
        gray = np.random.randint(180, 255)
        alpha = np.random.randint(50, 120)
        pixels[x, y] = (gray, gray, gray, alpha)

    # 3. VCR band overlay
    draw = ImageDraw.Draw(img)
    for i in range(0, height, 40):
        band_alpha = np.random.randint(30, 80)
        draw.rectangle((0, i, width, i + 1), fill=(255, 255, 255, band_alpha))

    return img

def animate_sigil(canvas, base_image_path, duration=4, floor=None, frame_count=24, moontime_hours=24):
    """Animate a sigil on the given canvas and save the frames as a GIF."""
    if not TK_EXISTS:
        return None
    base_img = Image.open(base_image_path).resize((512, 512))
    frames = []

    if floor is not None:
        start = floor.now()
        tick = timedelta(hours=moontime_hours / frame_count)
        frame_duration = _clock_frame_duration_seconds(start, frame_count, moontime_hours)

        for i in range(frame_count):
            observed_at = start + (tick * i)
            frame = _render_clock_sigil_frame(floor, observed_at, size=512, ornaments=True, inscription=True, glyph=True, tree=True, shadow=True, vestal=True)
            #frames.append(frame.copy())

            frames.append(glow_layer(frame.copy(), passes=1))
    else:
        # Build animation frames
        for i in range(5):
            shifted     = apply_color_shift(base_img.copy(), i * 5)
            #blurred     = apply_blur(shifted, i * 0.4)
            #pixelated   = apply_pixelation(blurred, max(1, 6 - i))
            # instead of blurred or pixelated, or also
            glowy = glow_layer(shifted.copy(), passes=2)
            frames.append(glowy)

        #frames.append(pixelated)

    # Add the reversed sequence so we “breathe” back to calm
        frames += frames[::-1]
        frame_duration = (get_frame_rhythm() * duration) / len(frames)

    # Display animation
    img_obj = canvas.create_image(0, 0, anchor='nw')
    tk_imgs = [ImageTk.PhotoImage(f) for f in frames]

    #frame_duration = duration / len(tk_imgs)

    gif_path = os.path.join("heather_sigils", f"{moonstamp()}.gif")
    buf = io.BytesIO()
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=min(int(frame_duration * 1000), 655350),
        loop=0,
    )
    bundle_put_bytes(gif_path, buf.getvalue())

    def update_frame(i=0):
        """Loop through frames endlessly, ping‑pong style."""
        canvas.itemconfig(img_obj, image=tk_imgs[i])
        # advance index and wrap around
        next_i = (i + 1) % len(tk_imgs)
        canvas.after(int(frame_duration * 1000), update_frame, next_i)

    update_frame()

    return gif_path

def apply_color_shift(image, shift_value):
    return image.convert('RGB').point(lambda p: p + shift_value)

def apply_zoom(image, zoom_factor):
    width, height = image.size
    new_size = (int(width * zoom_factor), int(height * zoom_factor))
    return image.resize(new_size, Image.LANCZOS)

def apply_blur(image, blur_radius):
    return image.filter(ImageFilter.GaussianBlur(blur_radius))

def glow_layer(image, passes=3, intensity=2):
    base = image.convert("RGB").copy()
    for i in range(passes):
        blurred = base.filter(ImageFilter.GaussianBlur(intensity))
        glitched = glitch_pass(blurred)
        with_static = add_static_overlay(glitched)
        base = Image.blend(base, with_static, 0.5)
    return base

def glitch_pass(img):
    """Simulates a frame glitch—lines, shifts, channel splitting."""
    w, h = img.size
    glitched = img.copy()
    draw = ImageDraw.Draw(glitched)

    # Add horizontal lines like VCR tracking issues
    for _ in range(random.randint(3, 8)):
        y = random.randint(0, h - 1)
        draw.line((0, y, w, y), fill=(random.randint(100, 255), 0, random.randint(100, 255)), width=1)

    # Shift channels slightly (RGB split effect)
    r, g, b = glitched.split()
    r = ImageChops.offset(r, random.randint(-2, 2), 0)
    b = ImageChops.offset(b, 0, random.randint(-2, 2))
    return Image.merge('RGB', (r, g, b))

def add_static_overlay(img):
    """Overlay white noise dots onto an image."""
    draw = ImageDraw.Draw(img)
    w, h = img.size
    h = h / 2 # Half height (they look like stars..)
    for _ in range(random.randint(500, 1000)):
        x = random.randint(0, w - 1)
        y = random.randint(0, h - 1)
        brightness = random.randint(100, 255)
        draw.point((x, y), fill=(brightness, brightness, brightness))
    return img

def get_frame_rhythm():
    mt = MoonTime.now()
    # 0 = New Moon, 100 = Full Moon
    if mt.phase == "Full Moon":
        return 1.4  # slow, dramatic
    elif mt.phase == "New Moon":
        return 0.6  # fast, anxious
    else:
        return 0.9  # default
