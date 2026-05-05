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

# --- Latin → Elder Futhark transliteration -----------------------------------
# Runes avoid horizontal strokes; this approximates Latin spelling using
# Elder Futhark Unicode runes (U+16A0..U+16FF) with simple, readable rules.

# Greedy multi-letter patterns first (lowercase, diacritics stripped)
_ELDER_DIGRAPHS: list[tuple[str, str]] = [
    ("ing", "ᛜ"),  # Ingwaz (preferred for the whole sequence)
    ("ng",  "ᛝ"),  # Ingwaz (alt glyph) for final -ng
    ("th",  "ᚦ"),  # Thurisaz
    ("qu",  "ᚲᚹ"),  # kaunan + wunjo (kw)
    ("ck",  "ᚲ"),   # treat "ck" as a single hard k
    ("ch",  "ᚲ"),   # approximate hard/affricate ch with kaunan
    ("sh",  "ᛋ"),   # sowilo for sh → s
    ("ph",  "ᚠ"),   # fehu for f
    ("ei",  "ᛇ"),   # eihwaz for ei/ey diphthongs
    ("ey",  "ᛇ"),
    ("gh",  "ᚷ"),   # simplify to gebo (g)
]

_ELDER_SINGLE: dict[str, str] = {
    "a": "ᚨ",  # ansuz
    "b": "ᛒ",  # berkano
    "c": "ᚲ",  # kaunan (context rule refines below)
    "d": "ᛞ",  # dagaz
    "e": "ᛖ",  # ehwaz
    "f": "ᚠ",  # fehu
    "g": "ᚷ",  # gebo
    "h": "ᚺ",  # hagalaz (ᚺ/ᚻ variants; pick ᚺ)
    "i": "ᛁ",  # isa
    "j": "ᛃ",  # jera (used for j/y glide)
    "k": "ᚲ",  # kaunan
    "l": "ᛚ",  # laguz
    "m": "ᛗ",  # mannaz
    "n": "ᚾ",  # naudiz
    "o": "ᛟ",  # othala (commonly used for o)
    "p": "ᛈ",  # pertho
    "q": "ᚲᚹ",  # kw fallback if not caught as qu
    "r": "ᚱ",  # raido
    "s": "ᛋ",  # sowilo
    "t": "ᛏ",  # tiwaz
    "u": "ᚢ",  # uruz
    "v": "ᚹ",  # approximate v with wunjo (w)
    "w": "ᚹ",  # wunjo
    "x": "ᚲᛋ",  # ks → kaunan+sowilo
    "y": "ᛃ",  # jera (y as consonant/vowel glide)
    "z": "ᛉ",  # algiz
}

def _strip_diacritics(text: str) -> str:
    """Return ``text`` with combining marks removed and common letterforms
    normalized (e.g., ß→ss, þ/ð→th, æ→ae, œ→oe).
    """
    # Normalize to compatibility form and drop combining marks
    decomposed = ud.normalize("NFKD", text)
    out: list[str] = []
    for ch in decomposed:
        if ud.combining(ch):
            continue
        # explicit common folds
        if ch == "ß":
            out.append("ss")
            continue
        if ch in ("þ", "Þ", "ð", "Ð"):
            out.append("th")
            continue
        if ch in ("æ", "Æ"):
            out.append("ae")
            continue
        if ch in ("œ", "Œ"):
            out.append("oe")
            continue
        if ch in ("ø", "Ø"):
            out.append("o")
            continue
        if ch in ("å", "Å"):
            out.append("a")
            continue
        out.append(ch)
    return "".join(out)

def is_elder_rune(ch: str) -> bool:
    """True if ``ch`` is within the Runic Unicode block U+16A0–U+16FF."""
    return len(ch) == 1 and "\u16A0" <= ch <= "\u16FF"

def latin_to_elder_runes(text: str, use_word_divider: bool = False) -> str:
    """Transliterate Latin text to Elder Futhark runes.

    - Greedy digraphs: th, ng/ing, ch, sh, ph, qu, ck, ei/ey.
    - Contextual ``c``: before e/i/y → ᛋ (s), else ᚲ (k).
    - Approximations: v→ᚹ (w), x→ᚲᛋ (ks), q→ᚲᚹ (kw).
    - Spaces preserved by default; set ``use_word_divider=True`` to
      render spaces as runic dividers: ᛫ for normal word gaps, ᛭ when the
      next non-space character is a capital ("capital space").
    - When ``use_word_divider`` is enabled, common punctuation maps to runic
      separators (and suppresses any divider immediately after the punctuation):
        , → ᛬   ; → ⁝   . → ᛫᛫   …/… → ᛫᛫᛫   ? → ᛫   ! → ᛬᛬

    This aims for legibility and the rune aesthetic (no horizontal strokes),
    not historical phonology.
    """
    # 1) Normalize diacritics and special letterforms
    base = _strip_diacritics(text)

    # 2) Walk input greedily
    out: list[str] = []
    i = 0
    n = len(base)
    while i < n:
        ch = base[i]

        # whitespace
        if ch.isspace():
            if use_word_divider:
                # Lookahead to decide if this is a capital-space (᛭)
                j = i + 1
                nxt_cap = False
                while j < n and base[j].isspace():
                    j += 1
                if j < n:
                    nxt = base[j]
                    if nxt.isalpha() and nxt.isupper():
                        nxt_cap = True
                out.append("᛭" if nxt_cap else "᛫")
            else:
                out.append(ch)
            i += 1
            continue

        # punctuation / digits
        if not ch.isalpha():
            if use_word_divider:
                rest = base[i:]
                if rest.startswith("..."):
                    out.append("᛫᛫᛫")
                    i += 3
                    # swallow following whitespace; do not emit divider after punctuation
                    while i < n and base[i].isspace():
                        i += 1
                    continue
                if ch == "…":  # unicode ellipsis
                    out.append("᛫᛫᛫")
                    i += 1
                    while i < n and base[i].isspace():
                        i += 1
                    continue
                if ch == ".":
                    out.append("᛫᛫")
                    i += 1
                    while i < n and base[i].isspace():
                        i += 1
                    continue
                if ch == "!":
                    out.append("᛬᛬")
                    i += 1
                    while i < n and base[i].isspace():
                        i += 1
                    continue
                if ch == "?":
                    out.append("᛫")
                    i += 1
                    while i < n and base[i].isspace():
                        i += 1
                    continue
                if ch == ";":
                    out.append("⁝")
                    i += 1
                    while i < n and base[i].isspace():
                        i += 1
                    continue
                if ch == ",":
                    out.append("᛬")
                    i += 1
                    while i < n and base[i].isspace():
                        i += 1
                    continue
            out.append(ch)
            i += 1
            continue

        # normalize to lowercase for matching, but keep original for pass-through
        rest = base[i:].lower()

        # tri/di-graph handling (greedy order as defined)
        matched = False
        for pat, rune in _ELDER_DIGRAPHS:
            if rest.startswith(pat):
                out.append(rune)
                i += len(pat)
                matched = True
                break
        if matched:
            continue

        c = rest[0]
        # contextual 'c'
        if c == "c":
            nxt = rest[1:2]
            out.append("ᛋ" if nxt in ("e", "i", "y") else "ᚲ")
            i += 1
            continue

        # q/x handled here if they slipped past digraphs
        if c == "q":
            out.append("ᚲᚹ")
            i += 1
            continue
        if c == "x":
            out.append("ᚲᛋ")
            i += 1
            continue

        rune = _ELDER_SINGLE.get(c)
        out.append(rune if rune is not None else base[i])
        i += 1

    return "".join(out)

def elder_runes(text: str) -> str:
    """Alias for ``latin_to_elder_runes`` (default settings)."""
    return latin_to_elder_runes(text)

# --- Appearance-first rune selection -----------------------------------------
# Choose runes purely by visual resemblance to Latin letters.
# You can customize by editing RUNE_APPEARANCE_CUSTOM below.

RUNE_APPEARANCE_DEFAULT: dict[str, str] = {
    # Core shapes that resemble Latin letters
    "a": "ᛃ", 
    "b": "ᛒ", 
    "c": "ᛈ", 
    "d": "ᚦ", 
    "e": "ᛊ",
    "f": "ᚨ",
    "g": "ᛟ",
    "h": "ᚺ", 
    "i": "ᛁ", 
    "j": "ᚾ",
    "k": "ᚲ", 
    "l": "ᛚ", 
    "m": "ᛖ", 
    "n": "ᚢ", 
    "o": "ᛜ", 
    "p": "ᚹ", 
    "q": "ᛟ", 
    "r": "ᚱ", 
    "s": "ᛋ", 
    "t": "ᛏ", 
    "u": "ᚠ", 
    "v": "ᛞ",  
    "w": "ᛗ", 
    "x": "ᚷ", 
    "y": "ᛉ", 
    "z": "ᛋ", 
}

# Your explicit preferences (pure shape picks). These override defaults.
RUNE_APPEARANCE_CUSTOM: dict[str, str] = {
    # Examples provided by you:
    "y": "ᛉ",  # Y→Algiz
    "t": "ᚾ",  # T→Naudiz
}

# Build the working map, allowing later code to update RUNE_APPEARANCE_CUSTOM.
RUNE_APPEARANCE: dict[str, str] = {**RUNE_APPEARANCE_DEFAULT, **RUNE_APPEARANCE_CUSTOM}
# Common misspelling alias so imports like `rune_apperance` work too
RUNE_APPERANCE = RUNE_APPEARANCE

def set_rune_appearance_override(letter: str, rune: str) -> None:
    """Override the appearance mapping for a single Latin letter."""
    if not letter:
        return
    key = letter.lower()[0]
    RUNE_APPEARANCE_CUSTOM[key] = rune
    RUNE_APPEARANCE[key] = rune

def latin_to_elder_by_appearance(
    text: str,
    use_word_divider: bool = False,
    mapping: Optional[dict[str, str]] = None,
) -> str:
    """Render text using runes chosen by visual resemblance only.

    - Letters map via ``mapping`` (defaults to ``RUNE_APPEARANCE``).
    - Spaces preserved, or replaced with ᛫ (or ᛭ when followed by a
      capital) if ``use_word_divider``.
    - With ``use_word_divider``, punctuation maps to runic separators
      and suppresses any divider immediately after the punctuation:
      , → ᛬   ; → ⁝   . → ᛫᛫   …/… → ᛫᛫᛫   ? → ᛫   ! → ᛬᛬
    """
    mp = (mapping or RUNE_APPEARANCE)
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        # spaces → ᛫ or ᛭ depending on next capital
        if ch.isspace():
            if use_word_divider:
                j = i + 1
                nxt_cap = False
                while j < n and text[j].isspace():
                    j += 1
                if j < n:
                    nxt = text[j]
                    if nxt.isalpha() and nxt.isupper():
                        nxt_cap = True
                out.append("᛭" if nxt_cap else "᛫")
            else:
                out.append(ch)
            i += 1
            continue

        # punctuation mapping when enabled
        if not ch.isalpha():
            if use_word_divider:
                rest = text[i:]
                if rest.startswith("..."):
                    out.append("᛫᛫᛫")
                    i += 3
                    while i < n and text[i].isspace():
                        i += 1
                    continue
                if ch == "…":
                    out.append("᛫᛫᛫")
                    i += 1
                    while i < n and text[i].isspace():
                        i += 1
                    continue
                if ch == ".":
                    out.append("᛫᛫")
                    i += 1
                    while i < n and text[i].isspace():
                        i += 1
                    continue
                if ch == "!":
                    out.append("᛬᛬")
                    i += 1
                    while i < n and text[i].isspace():
                        i += 1
                    continue
                if ch == "?":
                    out.append("᛫~")
                    i += 1
                    while i < n and text[i].isspace():
                        i += 1
                    continue
                if ch == ";":
                    out.append("⁝")
                    i += 1
                    while i < n and text[i].isspace():
                        i += 1
                    continue
                if ch == ",":
                    out.append("᛬")
                    i += 1
                    while i < n and text[i].isspace():
                        i += 1
                    continue
            out.append(ch)
            i += 1
            continue

        # letters
        out.append(mp.get(ch.lower(), ch))
        i += 1
    return "".join(out)

def rune_appearance(ch: str) -> str:
    """Single-character helper: best visual-match rune for ``ch``.
    Falls back to original if not a-z.
    """
    return RUNE_APPEARANCE.get(ch.lower(), ch)

# Keep the misspelled helper as an alias for convenience
def rune_apperance(ch: str) -> str:  # noqa: D401
    return rune_appearance(ch)

PHASES = {'☊': 'ascending', '☋': 'descending'}
PLANETS = {
    '☿': 'Mercury',
    '♀': 'Venus',
    '♂': 'Mars',
    '♃': 'Jupiter',
    '♄': 'Saturn',
    '♅': 'Uranus',
    '♆': 'Neptune',
    '♇': 'Pluto',
    '☉': 'Sun',
    '☽': 'Moon'
}
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

ELEMENTS = {
    'Δ': 'Air',
    '▽': 'Water',
    '△': 'Fire',
    '♁': 'Earth',
    '⚶': 'Spirit',
}
HEBREW_LOOKUP = {
    'Δ':  'א',   # Aleph
    '☿': 'ב',   # Beth
    '☽': 'ג',   # Gimel
    '♀': 'ד',   # Daleth
    '♈': 'ה',   # Heh
    '♉': 'ו',   # Vav
    '♊': 'ז',   # Zayin
    '♋': 'ח',   # Cheth
    '♌': 'ט',   # Teth
    '♍': 'י',   # Yod
    '♃': 'כ',   # Kaph
    '♎': 'ל',   # Lamed
    '▽': 'מ',   # Mem
    '♏': 'נ',   # Nun
    '♐': 'ס',   # Samekh
    '♑': 'ע',   # Ayin
    '♂': 'פ',   # Peh
    '♒': 'צ',   # Tzaddi
    '♓': 'ק',   # Qoph
    '☉': 'ר',   # Resh
    '△': 'ש',   # Shin
    '♄': 'ת',   # Tav
    '♁': 'ת',   # Tav (Earth row duplicates Tav)
    # Rows 24 – 27 (Spirit, Uranus, Neptune, Pluto) have “n/a” in the book.
}
LATIN_TO_HEBREW = {
    'a': ('א', 'ע'),
    'b': 'ב',
    'c': ('כ', 'ק'),
    'd': 'ד',
    'e': 'ה',
    'f': 'פ',
    'g': 'ג',
    'h': ('ה', 'ח'),
    'i': 'י',
    'j': 'י',
    'k': ('כ', 'ק'),
    'l': 'ל',
    'm': 'מ',
    'n': 'נ',
    'o': 'ע',
    'p': 'פ',
    'q': 'ק',
    'r': 'ר',
    's': ('ס', 'ש'),
    't': ('ת', 'ט', 'צ'),
    'u': 'ו',
    'v': 'ו',
    'w': 'ו',
    'x': 'ס',
    'y': 'י',
    'z': 'ז',
}
HEBREW_TO_EARLY = {
    # 1  Ox head          →  𓃾  (Gardiner F001)                                       :contentReference[oaicite:0]{index=0}
    'א': '𓃾',
    # 2  Tent / house-plan →  𓉐  (O001)                                              :contentReference[oaicite:1]{index=1}
    'ב': '𓉐',
    # 3  Foot              →  𓃀  (D058)                                              :contentReference[oaicite:2]{index=2}
    'ג': '𓃀',
    # 4  Door / door-bolt  →  𓊃  (O034)                                              :contentReference[oaicite:3]{index=3}
    'ד': '𓊃',
    # 5  Man, arms raised  →  𓀠  (A028)                                              :contentReference[oaicite:4]{index=4}
    'ה': '𓀠',
    # 6  Tent-peg / stake  →  𓌡  (T21 “harpoon”)                                     :contentReference[oaicite:5]{index=5}
    'ו': '𓌡',
    # 7  Mattock / weapon  →  𓌔  (T14 axe-type weapon)                               :contentReference[oaicite:6]{index=6}
    'ז': '𓌔',
    # 8  Tent-wall / fence →  𓉻  (O029 “wall of mats”)                               :contentReference[oaicite:7]{index=7}
    'ח': '𓉻',
    # 9  Basket            →  𓎟  (V30)                                              :contentReference[oaicite:8]{index=8}
    'ט': '𓎟',
    #10  Arm & closed hand →  𓂧  (D041 “arm”)                                       :contentReference[oaicite:9]{index=9}
    'י': '𓂧',
    #11  Open palm         →  𓂝  (D036 “open hand/palm”)                            :contentReference[oaicite:10]{index=10}
    'כ': '𓂝',  'ך': '𓂝',
    #12  Shepherd’s staff  →  𓌳  (S039 arrow-staff)                                 :contentReference[oaicite:11]{index=11}
    'ל': '𓌳',
    #13  Water             →  𓈖  (N035 “water”)                                     :contentReference[oaicite:12]{index=12}
    'מ': '𓈖',  'ם': '𓈖',
    #14  Seed / sprout     →  𓆓  (M23 “grain”)                                      :contentReference[oaicite:13]{index=13}
    'נ': '𓆓',  'ן': '𓆓',
    #15  Thorn / grabber   →  𓊩  (T22 “thorn branch”)                               :contentReference[oaicite:14]{index=14}
    'ס': '𓊩',
    #16  Eye               →  𓂀  (D004 “eye”)                                       :contentReference[oaicite:15]{index=15}
    'ע': '𓂀',
    #17  Mouth             →  𓂋  (D021 “mouth”)                                     :contentReference[oaicite:16]{index=16}
    'פ': '𓂋',  'ף': '𓂋',
    #18  Trail / path      →  𓊪  (T12 “sling; path”)                                :contentReference[oaicite:17]{index=17}
    'צ': '𓊪',  'ץ': '𓊪',
    #19  Sun-on-horizon    →  𓇳  (N005 sun-disk)                                    :contentReference[oaicite:18]{index=18}
    'ק': '𓇳',
    #20  Human head        →  𓁶  (C001 “head”)                                      :contentReference[oaicite:19]{index=19}
    'ר': '𓁶',
    #21  Two teeth         →  𓏏  (X001 loaf—Egyptian used for ‘t’; looks like teeth) :contentReference[oaicite:20]{index=20}
    'ש': '𓏏',
    #22  Crossed sticks    →  𓎼  (V31 basket-with-handle crossed)                   :contentReference[oaicite:21]{index=21}
    'ת': '𓎼',
}
HIEROGLYPH_LOOKUP = {
    'Δ':  '𓄿',   # G1 – vulture  (Air)
    '☿': '𓇋',   # M17 – reed leaf (Mercury)
    '☽': '𓏌',   # W24 – ripple / lunar bowl (Moon)
    '♀': '𓊵',   # R4  – mouth / boat (Venus)
    '♈': '𓊄',   # O35 – square seat (Aries)
    '♉': '𓅱',   # G43 – quail chick (Taurus)
    '♊': '𓏭',   # Z4  – doubles / twin strokes (Gemini)
    '♋': '𓆓',   # I10 – backbone (Cancer)
    '♌': '𓉽',   # O30 – throne (Leo)
    '♍': '𓂋',   # D21 – hand (Virgo)
    '♃': '𓂉',   # D19 – cupped hand (Jupiter)
    '♎': '𓁩',   # C12 – placenta / scales (Libra)
    '▽': '𓈖',   # N35 – pool of water (Water)
    '♏': '𓇓',   # M23 – zig-zag water / scorpion’s tail (Scorpio)
    '♐': '𓋿',   # S39 – arrow (Sagittarius)
    '♑': '𓋔',   # S3  – tethering rope (Capricorn)
    '♂': '𓇼',   # N14 – square enclosure (Mars)
    '♒': '𓆑',   # I9  – twisted flax (Aquarius)
    '♓': '𓆓',   # I10 – fish (Pisces)  [same char as Cancer row in many tables]
    '☉': '𓇳',   # N5  – sun disc (Sol)  ← U+131F3
    '△': '𓊈',   # Q7  – flame (Fire)    ← U+13288
    '♄': '𓋬',   # S29 – half cord (Saturn)
    '♁': '𓇴',   # N16 – mound of earth (Earth)
    '⚶': '𓊵',   # reuse R4 (Spirit had its own “solar disc inside serpent” in Crowley)
    # Special planetary glyphs (rows 25–27) were custom in Crowley’s table:
}
RUNE_LOOKUP = {
    '♈': ['ᚠ', 'ᚢ'],
    '♉': ['ᚦ', 'ᚨ'],
    '♊': ['ᚱ', 'ᚲ'],
    '♋': ['ᚷ', 'ᚹ'],
    '♌': ['ᚺ', 'ᚾ'],
    '♍': ['ᛁ', 'ᛃ'],
    '♎': ['ᛇ', 'ᛈ'],
    '♏': ['ᛉ', 'ᛊ'],
    '♐': ['ᛏ', 'ᛒ'],
    '♑': ['ᛖ', 'ᛗ'],
    '♒': ['ᛚ', 'ᛜ'],
    '♓': ['ᛞ', 'ᛟ'],
    '☿': ['ᚺ', 'ᛃ'],
    '♀': ['ᚠ', 'ᚲ', 'ᚹ', 'ᚾ', 'ᛁ', 'ᛈ', 'ᛒ', 'ᛖ', 'ᛚ'],
    '♂': ['ᚢ', 'ᚦ', 'ᚨ', 'ᚱ', 'ᚷ', 'ᛇ', 'ᛉ', 'ᛊ', 'ᛏ', 'ᛗ', 'ᛜ', 'ᛞ', 'ᛟ'],
    '♃': ['ᚢ', 'ᚦ', 'ᚨ', 'ᚱ', 'ᚷ', 'ᛇ', 'ᛉ', 'ᛊ', 'ᛏ', 'ᛗ', 'ᛜ', 'ᛞ', 'ᛟ'],
    '♄': ['ᚺ', 'ᛃ'],
    '☉': ['ᚢ', 'ᚦ', 'ᚨ', 'ᚱ', 'ᚷ', 'ᛇ', 'ᛉ', 'ᛊ', 'ᛏ', 'ᛗ', 'ᛜ', 'ᛞ', 'ᛟ'],
    '☽': ['ᚠ', 'ᚲ', 'ᚹ', 'ᚺ', 'ᚾ', 'ᛁ', 'ᛃ', 'ᛈ', 'ᛒ', 'ᛖ', 'ᛚ'],
    '☊': ['ᚠ', 'ᚲ', 'ᚹ', 'ᚺ', 'ᚾ', 'ᛁ', 'ᛃ', 'ᛈ', 'ᛒ', 'ᛖ', 'ᛚ'],
    '☋': ['ᚺ', 'ᛃ'],
    'Δ': ['ᚨ', 'ᚷ', 'ᚾ', 'ᛃ', 'ᛖ', 'ᛞ'],
    '▽': ['ᛚ', 'ᚺ', 'ᛁ', 'ᛇ', 'ᛈ', 'ᛚ'],
    '△': ['ᚠ', 'ᚦ', 'ᚱ', 'ᚲ', 'ᛉ', 'ᛊ', 'ᛏ', 'ᛗ'],
    '♁': ['ᚢ', 'ᚹ', 'ᛒ', 'ᛜ', 'ᛟ']
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

HEBREW_TO_PHOENICIAN = {
    # ── regular letters 1-22 ────────────────────────
    'א': '𐤀',  # Aleph   → ʾĀlep
    'ב': '𐤁',  # Bet     → Bēt
    'ג': '𐤂',  # Gimel   → Gīmel
    'ד': '𐤃',  # Dalet   → Dālet
    'ה': '𐤄',  # He      → Hē
    'ו': '𐤅',  # Vav     → Wāw
    'ז': '𐤆',  # Zayin   → Zayin
    'ח': '𐤇',  # Ḥet    → Ḥēt
    'ט': '𐤈',  # Tet     → Tēt
    'י': '𐤉',  # Yod     → Yōd
    'כ': '𐤊',  # Kaf     → Kāf
    'ל': '𐤋',  # Lamed   → Lāmed
    'מ': '𐤌',  # Mem     → Mēm
    'נ': '𐤍',  # Nun     → Nūn
    'ס': '𐤎',  # Samekh  → Sāmek
    'ע': '𐤏',  # Ayin    → ʿAyin
    'פ': '𐤐',  # Pe      → Pē/Phē
    'צ': '𐤑',  # Tsade   → Ṣādē
    'ק': '𐤒',  # Qof     → Qōp
    'ר': '𐤓',  # Resh    → Rēš
    'ש': '𐤔',  # Shin    → Šīn
    'ת': '𐤕',  # Tav     → Tāw

    # ── sofit (final) forms – map to the same Phoenician letter ──
    'ך': '𐤊',  # Kaf-sofit
    'ם': '𐤌',  # Mem-sofit
    'ן': '𐤍',  # Nun-sofit
    'ף': '𐤐',  # Pe-sofit
    'ץ': '𐤑',  # Tsade-sofit
}

HEBREW_TO_ARABIC = {
    # ── regular letters 1-22 ────────────────────────
    'א': 'ا',  # Alif
    'ב': 'ب',  # Bāʾ
    'ג': 'ج',  # Jīm
    'ד': 'د',  # Dāl
    'ה': 'ه',  # Hāʾ
    'ו': 'و',  # Wāw
    'ז': 'ز',  # Zāy
    'ח': 'ح',  # Ḥāʾ
    'ט': 'ط',  # Ṭāʾ
    'י': 'ي',  # Yāʾ
    'כ': 'ك',  # Kāf
    'ל': 'ل',  # Lām
    'מ': 'م',  # Mīm
    'נ': 'ن',  # Nūn
    'ס': 'س',  # Sīn
    'ע': 'ع',  # ʿAyn
    'פ': 'ف',  # Fāʾ
    'צ': 'ص',  # Ṣād
    'ק': 'ق',  # Qāf
    'ר': 'ر',  # Rāʾ
    'ש': 'ش',  # Shīn
    'ת': 'ت',  # Tāʾ

    # ── sofit forms – point to the “same sound” Arabic letter ──
    'ך': 'ك',  # Kāf
    'ם': 'م',  # Mīm
    'ן': 'ن',  # Nūn
    'ף': 'ف',  # Fāʾ
    'ץ': 'ص',  # Ṣād
}


def letters_alpha(text: str) -> list[str]:
    """
    Return a list of the alphabetic characters in *text*.
    Works with accented letters and other scripts.
    """
    return [ch for ch in text if ud.category(ch).startswith("L")]

def letters_alpha_with_spaces(text: str) -> list[str]:
    return [ch if ch == ' ' or ud.category(ch).startswith("L") else '' for ch in text]

def generate_fake_glyphs(phrase):
    clean = letters_alpha_with_spaces(phrase)
    glyphs = []
    #usable = list(HIEROGLYPH_LOOKUP.values())
    usable = list(HEBREW_TO_EARLY.values())

    for ch in clean:
        if ch == ' ':
            glyphs.append(' ')  # preserve spacing
        else:
            glyphs.append(random.choice(usable))
    return glyphs

def generate_true_glyphs(phrase, output="phoen"):
    clean = letters_alpha_with_spaces(phrase)
    result = []
    for ch in clean:
        if ch == ' ':
            result.append(' ')
        else:
            heb = latin_from(ch.lower())
            symbo = hebrew_to_symbol(heb)

            if output == "phoen":
            
                out = to_phoenician(heb)

            elif output == "symbo":
                out = symbo
            elif output == "rune":
                #out = latin_to_elder_by_appearance(ch.lower()) # Also works
                out = rune_for(symbo)
            elif output == "hyro":
                #out = HEBREW_TO_EARLY(heb) # Also works
                out = HIEROGLYPH_LOOKUP(symbo)
            elif output == "arab":
                out = HEBREW_TO_ARABIC(heb)[::-1]
            else:
                out = heb[::-1]
            result.append(out)
    return result


def most_matched_rune(symbols: str, lookup: dict[str, list[str]] = RUNE_LOOKUP) -> str | None:
    """
    Given a string of zodiac / planetary symbols, return the rune that appears
    most often across their lookup lists.  If there’s a tie, choose randomly.

    Returns None if no symbol in the string has a lookup entry.
    """
    counts = Counter()
    for s in symbols:
        counts.update(lookup.get(s, []))   # silently ignore unknown symbols

    if not counts:
        return None                        # nothing matched

    max_freq = max(counts.values())
    top = [r for r, c in counts.items() if c == max_freq]
    return random.choice(top)

# ── tiny helpers, same pattern as before ─────────────────────────
LATIN_TO_EARLY = {
    lat: [HEBREW_TO_EARLY[h] for h in heb] if isinstance(heb, tuple)
          else HEBREW_TO_EARLY.get(heb, heb)
    for lat, heb in LATIN_TO_HEBREW.items()
}

# ───────────  tiny helpers  ───────────
def hebrew_to_symbol(ch: str):
    return next((k for k, v in HEBREW_LOOKUP.items() if v == ch.lower()), None)

def latin_to_hebrew(ch: str):
    return LATIN_TO_HEBREW.get(ch.lower(), ch)

def latin_to_early(ch: str):
    return LATIN_TO_EARLY.get(ch.lower(), ch)

def latin_to_hebrew(ch: str):
    """Best-guess Modern-Hebrew for a Latin letter (falls back to original)."""
    return LATIN_TO_HEBREW.get(ch.lower(), ch)

def hebrew_to_early(ch: str):
    """Phoenician glyph for a Hebrew letter (falls back to original)."""
    return HEBREW_TO_EARLY.get(ch, ch)

def to_phoenician(hebrew: str) -> str:
    """Look up the Phoenician equivalent of a Hebrew letter (falls back to original)."""
    return HEBREW_TO_PHOENICIAN.get(hebrew, hebrew)

def to_arabic(hebrew: str) -> str:
    """Look up the Arabic equivalent of a Hebrew letter (falls back to original)."""
    return HEBREW_TO_ARABIC.get(hebrew, hebrew)

def hebrew_for(glyph: str) -> str:
    """Return the Hebrew letter (symbol) for *glyph*, or the glyph itself if unknown."""
    return HEBREW_LOOKUP.get(glyph, glyph)

def hieroglyph_for(glyph: str) -> str:
    """Return the Egyptian hieroglyph symbol for *glyph*, or the glyph itself if unknown."""
    return HIEROGLYPH_LOOKUP.get(glyph, glyph)

def rune_for(glyph: str) -> str:
    """Return the rune (symbol) for *glyph*, or the glyph itself if unknown."""
    variants = RUNE_LOOKUP.get(glyph)
    if not variants:
        # no entry or empty list → just return the glyph unchanged
        return glyph

    # if it’s stored as a single string, return that
    if isinstance(variants, str):
        return variants

    # otherwise it’s a non-empty list
    return random.choice(variants)

def latin_from(glyph: str) -> str:
    variants = LATIN_TO_HEBREW.get(glyph)
    if not variants:
        # no entry or empty list → just return the glyph unchanged
        return glyph

    # if it’s stored as a single string, return that
    if isinstance(variants, str):
        return variants

    # otherwise it’s a non-empty list
    return random.choice(variants)

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


        phase_offset = entry.get("phase", 0.0)
        theta = math.radians(lon + phase_offset * 30 - 90)
        #theta = math.radians(lon - 103)

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

            # 🌞 Shadow using floor.observe()
            beam = floor.observe()
            sun = beam.get("sun")

            if sun:
                alt = sun["alt_apparent"]
                az  = sun["azimuth"]
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