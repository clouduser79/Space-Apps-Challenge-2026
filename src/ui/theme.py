"""Design tokens for the mission-control UI.

Every colour, font and spacing value used by the interface lives here so
the whole app reads as one system. Screens never hard-code a hex value or
a font family — they pull from this module.

Palette: deep-space navy surfaces, a single cyan accent for "you can act
on this", and three status colours (green / amber / red) that are reserved
for telling the player how healthy the design is.
"""

from __future__ import annotations

import sys

import customtkinter as ctk

# --------------------------------------------------------------------------
# Surfaces (darkest -> lightest). Each step up is one level of elevation.
# --------------------------------------------------------------------------
BG = "#060A13"            # window background / deep space
SURFACE = "#0C1322"       # large panels (sidebar, header)
CARD = "#111A2C"          # cards
CARD_HOVER = "#17233A"    # card under the pointer
RAISED = "#1B2942"        # chips, progress-bar tracks, inputs
BORDER = "#22304A"        # hairline borders
BORDER_STRONG = "#3A4F78" # hovered / emphasised borders

# --------------------------------------------------------------------------
# Text
# --------------------------------------------------------------------------
TEXT = "#E8EEFA"
TEXT_MUTED = "#9AA8C4"
TEXT_DIM = "#62718F"
TEXT_ON_ACCENT = "#03131F"

# --------------------------------------------------------------------------
# Accent + status colours, each with a dark tint used as a badge background
# --------------------------------------------------------------------------
ACCENT = "#38BDF8"
ACCENT_HOVER = "#7DD3FC"
ACCENT_BG = "#0B2A40"

VIOLET = "#A78BFA"
VIOLET_BG = "#221B45"

SUCCESS = "#34D399"
SUCCESS_BG = "#0C2C25"

WARNING = "#FBBF24"
WARNING_BG = "#33270B"

DANGER = "#F87171"
DANGER_HOVER = "#FCA5A5"
DANGER_BG = "#3A191D"

# tone name -> (foreground, tinted background)
TONES: dict[str, tuple[str, str]] = {
    "accent": (ACCENT, ACCENT_BG),
    "violet": (VIOLET, VIOLET_BG),
    "success": (SUCCESS, SUCCESS_BG),
    "warning": (WARNING, WARNING_BG),
    "danger": (DANGER, DANGER_BG),
    "neutral": (TEXT_MUTED, RAISED),
}

# Trajectory view
SUN = "#FCD34D"
OUTBOUND = ACCENT
RETURN = VIOLET
ORBIT_RING = WARNING
LANDING = SUCCESS

# --------------------------------------------------------------------------
# Spacing + shape
# --------------------------------------------------------------------------
PAD_XS = 4
PAD_SM = 8
PAD = 16
PAD_LG = 24
PAD_XL = 32

RADIUS = 14       # cards
RADIUS_SM = 8     # buttons, chips

# --------------------------------------------------------------------------
# Typography
# --------------------------------------------------------------------------
if sys.platform == "darwin":
    FONT_FAMILY, MONO_FAMILY = "Helvetica Neue", "Menlo"
elif sys.platform.startswith("win"):
    FONT_FAMILY, MONO_FAMILY = "Segoe UI", "Consolas"
else:
    FONT_FAMILY, MONO_FAMILY = "DejaVu Sans", "DejaVu Sans Mono"

_font_cache: dict[tuple, ctk.CTkFont] = {}


def font(size: int = 13, weight: str = "normal", mono: bool = False) -> ctk.CTkFont:
    """Cached CTkFont. Must be called after the root window exists."""
    key = (size, weight, mono)
    if key not in _font_cache:
        _font_cache[key] = ctk.CTkFont(
            family=MONO_FAMILY if mono else FONT_FAMILY, size=size, weight=weight)
    return _font_cache[key]


def canvas_font(size: int, bold: bool = False) -> tuple:
    """Font tuple for raw tk.Canvas text items."""
    return (FONT_FAMILY, size, "bold") if bold else (FONT_FAMILY, size)


# Named type ramp — (size, weight). Use these instead of ad-hoc sizes.
DISPLAY = (30, "bold")
H1 = (22, "bold")
H2 = (16, "bold")
H3 = (14, "bold")
BODY = (13, "normal")
SMALL = (12, "normal")
CAPTION = (11, "bold")    # upper-case eyebrow labels


def apply_theme() -> None:
    """Global CustomTkinter settings. Call once before creating the root."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")


# --------------------------------------------------------------------------
# Small formatting helpers shared by every screen
# --------------------------------------------------------------------------
def money(usd: float) -> str:
    """$8M, $7.5M, $2B, $4T — compact, no trailing zeros."""
    if abs(usd) >= 1e12:
        value, unit = usd / 1e12, "T"
    elif abs(usd) >= 1e9:
        value, unit = usd / 1e9, "B"
    else:
        value, unit = usd / 1e6, "M"
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return f"${text}{unit}"


def usage_tone(fraction: float, warn: float = 0.75, danger: float = 0.90) -> str:
    """Tone for a 'how much of the limit is used' meter."""
    if fraction >= danger:
        return "danger"
    if fraction >= warn:
        return "warning"
    return "accent"


def score_tone(score: float) -> str:
    """Tone for a 0-100 'higher is better' score."""
    if score >= 75:
        return "success"
    if score >= 50:
        return "warning"
    return "danger"
