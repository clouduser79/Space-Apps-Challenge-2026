"""Image assets (planet art, rocket) for CustomTkinter widgets.

Pillow is optional: every loader returns None when it is missing and the
callers fall back to a coloured glyph, so the game always runs.
"""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:  # pragma: no cover - depends on the environment
    HAS_PIL = False

ROOT = Path(__file__).resolve().parents[2]
PLANET_DIR = ROOT / "planetImages"
ROCKET_PATH = ROOT / "rocket.png"

_cache: dict[tuple[str, int], ctk.CTkImage | None] = {}


def _load(path: Path, height: int) -> ctk.CTkImage | None:
    """Load an image scaled to `height`, preserving its aspect ratio."""
    key = (str(path), height)
    if key not in _cache:
        image = None
        if HAS_PIL and path.exists():
            try:
                pil = Image.open(path).convert("RGBA")
                width = max(1, round(height * pil.width / pil.height))
                image = ctk.CTkImage(light_image=pil, dark_image=pil,
                                     size=(width, height))
            except OSError:
                image = None
        _cache[key] = image
    return _cache[key]


def planet_image(planet_id: str, height: int) -> ctk.CTkImage | None:
    return _load(PLANET_DIR / f"{planet_id}.png", height)


def rocket_image(height: int) -> ctk.CTkImage | None:
    return _load(ROCKET_PATH, height)


# --------------------------------------------------------------------------
# Raw Tk images for tk.Canvas drawing (CTkImage only works in CTk widgets)
# --------------------------------------------------------------------------
_photo_cache: dict[tuple, object] = {}


def canvas_photo(path: Path, height: int, rotate_deg: float = 0.0):
    """ImageTk.PhotoImage scaled to `height` (optionally rotated), cached.
    Returns None without Pillow. Keep using the cached object: Tk drops
    images whose Python reference is garbage-collected."""
    if not HAS_PIL or not path.exists() or height < 2:
        return None
    key = (str(path), height, round(rotate_deg))
    if key not in _photo_cache:
        from PIL import ImageTk
        pil = Image.open(path).convert("RGBA")
        width = max(1, round(height * pil.width / pil.height))
        pil = pil.resize((width, height), Image.LANCZOS)
        if rotate_deg:
            pil = pil.rotate(rotate_deg, expand=True, resample=Image.BICUBIC)
        _photo_cache[key] = ImageTk.PhotoImage(pil)
    return _photo_cache[key]


def difficulty_tone(scenario) -> tuple[str, str]:
    """(badge label, tone) for a scenario's difficulty."""
    if getattr(scenario, "sandbox_mode", False):
        return "Sandbox", "violet"
    return scenario.difficulty, {"cadet": "success", "engineer": "accent",
                                 "expert": "danger"}.get(scenario.difficulty, "neutral")
