from pydub.generators import WhiteNoise
import math
import random
import io, os, tempfile
from math import radians
from moontime import moonstamp, MoonTime
from .bundle import _bundle_key_with_ext, _maybe_write_temp_png, bundle_put_bytes, _bundle_load, ASSET_BYTES, bundle_put_image, _resolve_asset_to_pil

TK_EXISTS = False
PIL_EXISTS = False

try:
    import tkinter as tk
    TK_EXISTS = True
except Exception:
    pass
try:
    from PIL import Image, ImageChops, ImageOps, ImageFilter, ImageDraw, ImageFont, ImageTk, ImageEnhance
    PIL_EXISTS = True
except Exception:
    pass

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
    'Apple': "shrub",
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
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
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

      # flatten vertically
    if alt < 60:
        new_w = int(size * 0.375)
    elif alt < 45:
        new_w = int(size * 0.25)
    elif alt < 30:
        new_w = int(size * 0.175)
    elif alt < 20:
        new_w = int(size * 0.09)
    else:
        new_w = int(size * 0.50)
      # 🌿 Stretch length based on altitude (LOW sun = LONG shadow)
    stretch = min(6.0, 1 / math.tan(alt_rad))

    inc = size * stretch
    new_h = int(size + inc)  # flatten vertically

    sprite = sprite.resize((new_w, new_h), Image.LANCZOS)

    # 🧭 Rotate so it lays away from sun
    angle = azimuth#  + 180 % 360
    if azimuth > 180:
        diff = (azimuth - 180) * 2 # Switch
        angle -= diff 
    elif azimuth < 180:
        diff = (180 - azimuth) * 2 # Switch
        angle += diff 

    sprite = sprite.rotate(angle, resample=Image.BICUBIC, expand=True)

    # 🎯 Anchor correction (THIS is the magic)
    w, h = sprite.size

    # We want the "base" of the tree to stay at (cx, cy)
    # After rotation, base ≈ center-bottom of the image
    if azimuth >= 180:

        x = cx - w * min(1, diff / 40)
        #y = cy

    else:
        x = cx
        #y = cy - w

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

    sprite = sprite.resize((size, size), Image.LANCZOS)
    if position is None:
        x = base_img.width - size - 10
        y = base_img.height - size - 10
    else:
        x, y = position

    base_img.paste(sprite, (int(x), int(y)), sprite)
    return base_img


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

    # 🐍 Zodiac slices
    above = floor.as_above()
    below = floor.so_below()
    full = above + list(reversed(below))

    for entry in full:
        lon = entry["center_lon"]
        sign = entry["sign"]

        theta = math.radians(lon - 103)

        x = cx + r * -math.sin(theta)
        y = cy - r *  math.cos(theta)

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
        if entry in above:
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
        angle = math.degrees(theta)



        # Optional: slight outward tilt (inscription like)
        #angle -= 90

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
    # 🌳 Tree (axis)
    rune = 'ᚨ'
    size = 64
    overlay_tree_sprite(
        img,
        rune,
        position=(cx - 32, cy - size),
        size=size
    )

    # 🌞 Shadow using floor.observe()
    dark_rune = 'ᛇ'
    beam = floor.observe()
    sun = beam.get("sun")

    if sun:
        alt = sun["alt_apparent"]
        az  = sun["azimuth"]

        if alt > floor.sun_delay().get("angle") and 90 < az < 270: # Over the horizon and projecting downwards
            overlay_shadow_tree(
                img,
                rune='ᛇ',
                cx=cx,
                cy=cy,
                azimuth=az,
                altitude=alt,
                size=64
            )

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


def show_sigil(image_key: str) -> str:
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
    gif_path = animate_sigil(canvas, local_png_path)

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

def animate_sigil(canvas, base_image_path, duration=4):
    """Animate a sigil on the given canvas and save the frames as a GIF."""
    if not TK_EXISTS:
        return None
    base_img = Image.open(base_image_path).resize((512, 512))
    frames = []

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

    # Display animation
    img_obj = canvas.create_image(0, 0, anchor='nw')
    tk_imgs = [ImageTk.PhotoImage(f) for f in frames]

    frame_duration = (get_frame_rhythm() * duration) / len(tk_imgs)
    #frame_duration = duration / len(tk_imgs)

    gif_path = os.path.join("heather_sigils", f"{moonstamp()}.gif")
    buf = io.BytesIO()
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=int(frame_duration * 1000),
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