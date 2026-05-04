from pathlib import Path
import io, os, tempfile
import pickle
from PIL import Image
import importlib.resources as res

ASSET_BYTES = {}
_LOADED = False

def _save_image_bundle_and_or_disk(img: Image.Image, out_path: Optional[str] = None, bundle_key: Optional[str] = None, fmt: str = "PNG") -> str:
    """
    If both out_path and bundle_key are given, writes both.
    Returns a string key/path preferring bundle_key if provided, else out_path.
    """
    if out_path:
        out_dir = os.path.dirname(out_path)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        img.save(out_path, format=fmt)

    if bundle_key:
        bundle_put_image(bundle_key, img, fmt=fmt)

    return bundle_key or (out_path or "")

def _bundle_load():
    global ASSET_BYTES, _LOADED
    if _LOADED:
        return
    try:
        # Try primary name
        try:
            with res.files("thresholdfloor").joinpath("assets_bundle.pkl").open("rb") as f:
                bundle = pickle.load(f)
        except FileNotFoundError:
            # Fallback for the typo (you lovable chaos gremlin)
            with res.files("thresholdfloor").joinpath("assets_bunle.pkl").open("rb") as f:
                bundle = pickle.load(f)

        if isinstance(bundle, dict) and "assets" in bundle:
            ASSET_BYTES = dict(bundle["assets"])
            _LOADED = True
        else:
            ASSET_BYTES = {}

    except Exception as e:
        print(f"[bundle_load] failed: {e}")
        ASSET_BYTES = {}

_bundle_load()

def _bundle_flush():
    try:
        payload = {"version": 1, "assets": ASSET_BYTES}
        with _BUNDLE_PATH.open("wb") as _f:
            pickle.dump(payload, _f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        pass

def _norm_key(path_like: str) -> str:
    key = path_like.replace("\\", "/")
    if key.startswith("./"):
        key = key[2:]
    if key.startswith(".\\"):
        key = key[3:]
    return key

def bundle_has(path_like: str) -> bool:
    if not ASSET_BYTES:
        return False
    key = _norm_key(path_like)
    return key in ASSET_BYTES or os.path.basename(key) in ASSET_BYTES

def bundle_get_bytes(path_like: str):
    if not ASSET_BYTES:
        return None
    key = _norm_key(path_like)
    return ASSET_BYTES.get(key) or ASSET_BYTES.get(os.path.basename(key))

def bundle_put_bytes(path_like: str, data: bytes, also_by_basename: bool = True):
    _bundle_load()
    key = _norm_key(path_like)
    ASSET_BYTES[key] = data
    if also_by_basename:
        ASSET_BYTES[os.path.basename(key)] = data
    _bundle_flush()

def bundle_put_image(path_like: str, img: Image.Image, fmt: str = "PNG"):
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    bundle_put_bytes(path_like, buf.getvalue())

def _resolve_asset_to_pil(path_like: str) -> Image.Image:
    """Return a PIL image from bundle if present, else from disk."""
    _bundle_load()
    data = bundle_get_bytes(path_like)
    if data is not None:
        return Image.open(io.BytesIO(data))
    # fallback to disk
    return Image.open(path_like)

def _maybe_write_temp_png(path_like: str) -> str:
    """
    Ensure we have a real PNG file on disk for code that requires a path.
    If the asset is only in the bundle, write it to a temp file and return that path.
    If the file exists on disk already, return the original path.
    """
    _bundle_load()
    data = bundle_get_bytes(path_like)
    if data is not None:
        # write to a temp file
        fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="sigil_")
        os.close(fd)
        with open(tmp_path, "wb") as f:
            f.write(data)
        return tmp_path
    # else assume path_like is an on-disk path
    return path_like

def _bundle_key_with_ext(path_like: str, new_ext: str) -> str:
    base = os.path.splitext(_norm_key(path_like))[0]
    if not new_ext.startswith("."):
        new_ext = "." + new_ext
    return f"{base}{new_ext}"
