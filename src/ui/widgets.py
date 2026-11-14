"""Reusable building blocks for the mission-control UI.

Everything here is presentation-only: no widget in this module knows
anything about missions, spacecraft or scoring. Screens compose these
pieces and feed them data.
"""

from __future__ import annotations

import math
import random
import sys
import weakref
import tkinter as tk
import tkinter.font as tkfont
from typing import Callable

import customtkinter as ctk

from customtkinter.windows.widgets.scaling import ScalingTracker

from src.ui import glossary
from src.ui import theme as T


# ==========================================================================
# Text helpers
# ==========================================================================
def text(master, value: str = "", style: tuple = T.BODY, color: str = T.TEXT,
         **kwargs) -> ctk.CTkLabel:
    """A label using one of the named type styles from the theme."""
    kwargs.setdefault("anchor", "w")
    kwargs.setdefault("justify", "left")
    return ctk.CTkLabel(master, text=value, font=T.font(*style),
                        text_color=color, **kwargs)


def eyebrow(master, value: str, color: str = T.ACCENT, **kwargs) -> ctk.CTkLabel:
    """Small upper-case label that names a section."""
    return text(master, value.upper(), T.CAPTION, color, **kwargs)


def auto_wrap(label: ctk.CTkLabel, container: tk.Misc, padding: int = 32) -> None:
    """Keep `label` wrapped to the width of `container` as it resizes."""
    state = {"width": 0}

    def on_configure(event) -> None:
        if event.widget is not container or abs(event.width - state["width"]) < 4:
            return
        # Inside a hidden screen the scroll canvas is 1px wide, so frames
        # fall back to their *requested* width — which depends on this very
        # wraplength. Re-wrapping there loops forever; wait until visible
        # (a fresh <Configure> arrives when the screen is shown).
        if not container.winfo_viewable():
            return
        state["width"] = event.width
        # <Configure> reports real pixels; wraplength expects unscaled units
        width = label._reverse_widget_scaling(event.width) - padding
        label.configure(wraplength=max(80, int(width)))

    tk.Misc.bind(container, "<Configure>", on_configure, add="+")


# ==========================================================================
# Glossary: inline term links + definition pop-up
# ==========================================================================
def _surface_color(widget: tk.Misc) -> str:
    """Background colour a widget actually sits on: the fg_color of the
    nearest CustomTkinter ancestor that isn't transparent."""
    w = widget.master
    while w is not None:
        if isinstance(w, (ctk.CTkFrame, ctk.CTk, ctk.CTkToplevel)):
            color = w.cget("fg_color")
            if isinstance(color, (tuple, list)):
                color = color[1]          # dark-mode value
            if color and color != "transparent":
                return color
        w = w.master
    return T.BG


class GlossaryText(tk.Text):
    """Read-only, auto-wrapping text in which glossary words are links.

    CTkLabel can't style part of its text, so this is a borderless
    tk.Text that looks like a label: it takes the theme font, matches its
    parent's background, wraps to whatever width the layout gives it and
    grows its height to fit. Words found by `glossary.find_terms` are drawn
    in the accent colour with an underline; clicking one opens
    `GlossaryPopup` and returns "break" so a surrounding SelectableCard
    does not also treat the click as "select this card".

    Always place it with fill="x" / sticky="ew": it requests almost no
    width of its own (which is also what keeps it out of resize loops).
    """

    _LINK_TAG = "glossary-link"
    _HOVER_TAG = "glossary-hover"

    def __init__(self, master, value: str = "", style: tuple = T.BODY,
                 color: str = T.TEXT, links: bool = True,
                 natural: bool = False) -> None:
        size, weight = style
        scale = ScalingTracker.get_widget_scaling(master)
        super().__init__(
            master, width=1, height=1, wrap="word", borderwidth=0,
            highlightthickness=0, padx=0, pady=0, takefocus=0, cursor="arrow",
            font=(T.FONT_FAMILY, round(-abs(size) * scale),
                  "bold" if weight == "bold" else "normal"),
            foreground=color, insertwidth=0, exportselection=False,
            spacing1=0, spacing2=2, spacing3=0)
        # Drop the "Text" class bindings: no editing, no text selection and
        # no wheel-scrolling inside the label (the page scrolls instead).
        self.bindtags((str(self), str(self.winfo_toplevel()), "all"))
        self._links = links
        self._natural = natural     # single-line: request the text's own width
        self._entries: dict[str, str] = {}     # tag name -> glossary entry
        self._hover: str | None = None
        self._idle_cursor = "arrow"
        self._last_width = 0

        self.tag_configure(self._LINK_TAG, foreground=T.ACCENT, underline=True)
        self.tag_configure(self._HOVER_TAG, foreground=T.ACCENT_HOVER)
        try:   # Tk 8.7+/9: a softer underline than the link colour itself
            self.tag_configure(self._LINK_TAG, underlinefg="#2B7FB0")
        except tk.TclError:
            pass

        self.bind("<Button-1>", self._on_click)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Configure>", self._on_resize)
        self.sync_bg()
        self.set_text(value)

    # --- content -----------------------------------------------------------
    def set_text(self, value: str, color: str | None = None) -> None:
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.insert("1.0", value)
        for tag in self._entries:
            self.tag_delete(tag)
        self._entries.clear()
        self._hover = None
        if self._links:
            for n, (start, end, entry) in enumerate(glossary.find_terms(value)):
                tag = f"term-{n}"
                span = (f"1.0 + {start} chars", f"1.0 + {end} chars")
                self.tag_add(tag, *span)
                self.tag_add(self._LINK_TAG, *span)
                self._entries[tag] = entry
            self.tag_raise(self._HOVER_TAG)
        if color is not None:
            self.configure(foreground=color)
        if self._natural:
            # Width is measured in "0" characters of the font
            font = tkfont.Font(font=self.cget("font"))
            chars = font.measure(value) / max(1, font.measure("0"))
            self.configure(width=max(1, math.ceil(chars) + 1))
        self.configure(state="disabled")
        self._fit_height()

    def sync_bg(self) -> None:
        """Match the surface underneath (call after the parent recolours)."""
        bg = _surface_color(self)
        self.configure(background=bg, selectbackground=bg,
                       inactiveselectbackground=bg)

    # --- layout --------------------------------------------------------------
    def _on_resize(self, event) -> None:
        if event.width != self._last_width:
            self._last_width = event.width
            self._fit_height()

    def _fit_height(self) -> None:
        """Grow/shrink to exactly the number of wrapped lines."""
        try:
            counted = self.count("1.0", "end-1c", "displaylines")
        except tk.TclError:
            return
        if isinstance(counted, tuple):
            counted = counted[0]
        lines = (counted or 0) + 1
        if int(self.cget("height")) != lines:
            self.configure(height=lines)

    # --- links ---------------------------------------------------------------
    def term_at(self, x: int, y: int) -> str | None:
        """Tag name of the glossary word under widget coordinates (x, y)."""
        if not self._entries:
            return None
        index = self.index(f"@{x},{y}")
        box = self.bbox(index)
        if box is None:
            return None
        bx, by, bw, bh = box
        # "@x,y" snaps to the nearest character; make sure we're really on it
        if not (bx <= x <= bx + bw and by <= y <= by + bh):
            return None
        return next((t for t in self.tag_names(index) if t in self._entries), None)

    def _set_hover(self, tag: str | None) -> None:
        if tag == self._hover:
            return
        self.tag_remove(self._HOVER_TAG, "1.0", "end")
        if tag is None:
            self.configure(cursor=self._idle_cursor)
        else:
            if self._hover is None:   # remember the card's own cursor
                self._idle_cursor = self.cget("cursor")
            first, last = self.tag_ranges(tag)[:2]
            self.tag_add(self._HOVER_TAG, first, last)
            self.configure(cursor="hand2")
        self._hover = tag

    def _on_motion(self, event) -> None:
        self._set_hover(self.term_at(event.x, event.y))

    def _on_leave(self, _event) -> None:
        self._set_hover(None)

    def _on_click(self, event):
        tag = self.term_at(event.x, event.y)
        if tag is None:
            return None            # plain text: let the card handle the click
        entry = self._entries[tag]
        GlossaryPopup.open(self, entry, glossary.define(entry),
                           event.x_root, event.y_root)
        return "break"             # stop the parent card from selecting


def glossary_text(master, value: str = "", style: tuple = T.BODY,
                  color: str = T.TEXT, natural: bool = False) -> GlossaryText:
    """Text block with clickable glossary words (see GlossaryText).
    `natural=True` sizes it to its text — for one-line titles that share a
    row with other widgets; otherwise place it with fill/sticky "ew"."""
    return GlossaryText(master, value, style, color, natural=natural)


class GlossaryPopup(ctk.CTkToplevel):
    """Floating definition card for one glossary word.

    Only one exists at a time: opening another replaces it. It closes on
    ✕ / "Got it!", on Esc, on any click outside it, or when the main
    window moves or resizes (it would otherwise be left floating).
    """

    WIDTH = 340
    _current: "GlossaryPopup | None" = None
    _installed_roots: set[str] = set()

    # --- public API ----------------------------------------------------------
    @classmethod
    def open(cls, source: tk.Misc, term: str, definition: str,
             x_root: int, y_root: int) -> "GlossaryPopup":
        cls.close()
        root = source._root()
        cls._install_global_handlers(root)
        cls._current = cls(root, term, definition, x_root, y_root)
        return cls._current

    @classmethod
    def close(cls, _event=None) -> None:
        popup, cls._current = cls._current, None
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass

    # --- construction --------------------------------------------------------
    def __init__(self, root, term: str, definition: str, x_root: int, y_root: int) -> None:
        corner = self._corner_color()
        super().__init__(root, fg_color=corner)
        self.withdraw()                    # build off-screen, then place
        self.overrideredirect(True)        # no title bar: it's a card
        self._make_corners_transparent(corner)

        card = ctk.CTkFrame(self, fg_color=T.CARD, corner_radius=T.RADIUS,
                            border_width=1, border_color=T.BORDER_STRONG,
                            width=self.WIDTH)
        card.pack(fill="both", expand=True)
        card.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(sticky="ew", padx=(T.PAD, T.PAD_SM), pady=(T.PAD_SM + 4, 0))
        head.grid_columnconfigure(0, weight=1)
        eyebrow(head, "Space word").grid(row=0, column=0, sticky="w")
        ctk.CTkButton(head, text="✕", width=28, height=28, corner_radius=14,
                      fg_color="transparent", hover_color=T.RAISED,
                      text_color=T.TEXT_MUTED, font=T.font(14, "bold"),
                      command=GlossaryPopup.close).grid(row=0, column=1, sticky="e")

        text(card, term, T.H2).grid(sticky="w", padx=T.PAD, pady=(2, 6))
        text(card, definition, (14, "normal"), T.TEXT,
             wraplength=self.WIDTH - 2 * T.PAD).grid(sticky="w", padx=T.PAD)
        primary_button(card, "Got it!", GlossaryPopup.close, height=34,
                       font=T.font(13, "bold")).grid(sticky="ew", padx=T.PAD,
                                                     pady=(T.PAD, T.PAD))
        self.bind("<Escape>", GlossaryPopup.close)

        self._place_near(root, x_root, y_root)
        self.deiconify()
        self.lift()
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass

    @staticmethod
    def _corner_color() -> str:
        """Window colour behind the rounded card corners."""
        if sys.platform == "darwin":
            return "systemTransparent"
        if sys.platform.startswith("win"):
            return "#010203"               # keyed out via -transparentcolor
        return T.BORDER_STRONG             # Linux: corners can't be clear

    def _make_corners_transparent(self, corner: str) -> None:
        try:
            if sys.platform == "darwin":
                self.wm_attributes("-transparent", True)
            elif sys.platform.startswith("win"):
                self.wm_attributes("-transparentcolor", corner)
        except tk.TclError:
            pass

    def _place_near(self, root, x_root: int, y_root: int) -> None:
        """Just below-right of the cursor, flipped and clamped so the whole
        card stays inside the main window."""
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        left, top = root.winfo_rootx(), root.winfo_rooty()
        right, bottom = left + root.winfo_width(), top + root.winfo_height()
        margin, gap = 12, 14

        x = x_root + gap
        if x + w > right - margin:          # no room on the right: go left
            x = x_root - w - gap
        y = y_root + gap
        if y + h > bottom - margin:         # no room below: go above
            y = y_root - h - gap
        x = max(left + margin, min(x, right - w - margin))
        y = max(top + margin, min(y, bottom - h - margin))
        # Raw Tk call: CTkToplevel.geometry() would rescale the coordinates
        tk.Wm.wm_geometry(self, f"+{int(x)}+{int(y)}")

    # --- closing behaviour ---------------------------------------------------
    @classmethod
    def _install_global_handlers(cls, root) -> None:
        """Bound once per root window (the root outlives every screen)."""
        if str(root) in cls._installed_roots:
            return
        cls._installed_roots.add(str(root))
        root.bind_all("<Button-1>", cls._click_anywhere, add="+")
        root.bind_all("<Escape>", cls.close, add="+")

        def on_root_configure(event) -> None:
            if event.widget is root and cls._current is not None:
                cls.close()
        tk.Misc.bind(root, "<Configure>", on_root_configure, add="+")

    @classmethod
    def _click_anywhere(cls, event) -> None:
        """Close when a click lands outside the pop-up. Clicks on glossary
        words never reach here (they return "break"), so clicking another
        word swaps the pop-up instead of just closing it."""
        popup = cls._current
        if popup is None:
            return
        try:
            inside = str(event.widget).startswith(str(popup))
        except Exception:
            inside = False
        if not inside:
            cls.close()


# ==========================================================================
# Containers
# ==========================================================================
class Card(ctk.CTkFrame):
    """Rounded panel with a hairline border — the basic layout container."""

    def __init__(self, master, **kwargs) -> None:
        kwargs.setdefault("fg_color", T.CARD)
        kwargs.setdefault("corner_radius", T.RADIUS)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", T.BORDER)
        super().__init__(master, **kwargs)


class ScrollFrame(ctk.CTkScrollableFrame):
    """Themed scrollable area.

    CustomTkinter registers global `bind_all` wheel/Shift handlers *on each
    scrollable frame*. When such a frame is destroyed (e.g. on restart) the
    handlers dangle and Tk prints errors on every scroll. It also decides
    whether to scroll from the widget the event hit, which misses nested
    children. Instead, all ScrollFrames share one dispatcher bound on the
    Tk root, which scrolls whichever live frame is under the pointer and
    also understands Tk 9 trackpad events.
    """

    _live: "weakref.WeakSet[ScrollFrame]" = weakref.WeakSet()
    _GLOBAL_SEQUENCES = ("<MouseWheel>", "<Button-4>", "<Button-5>",
                         "<KeyPress-Shift_L>", "<KeyPress-Shift_R>",
                         "<KeyRelease-Shift_L>", "<KeyRelease-Shift_R>")

    def __init__(self, master, **kwargs) -> None:
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("scrollbar_button_color", T.RAISED)
        kwargs.setdefault("scrollbar_button_hover_color", T.BORDER_STRONG)
        super().__init__(master, **kwargs)
        self._touch_remainder = 0.0
        ScrollFrame._live.add(self)
        self._install_dispatcher()

    def _install_dispatcher(self) -> None:
        # Drop the per-instance handlers CTk just added, then (re)bind the
        # shared dispatcher on the root, which outlives every screen.
        for sequence in self._GLOBAL_SEQUENCES:
            self.unbind_all(sequence)
        root = self._root()
        if sys.platform.startswith("linux"):
            root.bind_all("<Button-4>", ScrollFrame._dispatch_wheel)
            root.bind_all("<Button-5>", ScrollFrame._dispatch_wheel)
        else:
            root.bind_all("<MouseWheel>", ScrollFrame._dispatch_wheel)
        try:  # Tk 9+: two-finger trackpad scrolling has its own event
            root.bind_all("<TouchpadScroll>", ScrollFrame._dispatch_touchpad)
        except tk.TclError:
            pass

    @classmethod
    def _target(cls) -> "ScrollFrame | None":
        for frame in list(cls._live):
            try:
                if frame._pointer_inside() and frame._can_scroll():
                    return frame
            except tk.TclError:          # frame is mid-destruction
                continue
        return None

    @classmethod
    def _dispatch_wheel(cls, event) -> None:
        frame = cls._target()
        if frame is not None:
            frame._wheel(event)

    @classmethod
    def _dispatch_touchpad(cls, event) -> None:
        frame = cls._target()
        if frame is not None:
            frame._touchpad(event)

    def destroy(self) -> None:
        ScrollFrame._live.discard(self)
        super().destroy()

    def _pointer_inside(self) -> bool:
        canvas = self._parent_canvas
        if not canvas.winfo_exists() or not canvas.winfo_viewable():
            return False
        x, y = canvas.winfo_pointerxy()
        left, top = canvas.winfo_rootx(), canvas.winfo_rooty()
        return (left <= x <= left + canvas.winfo_width()
                and top <= y <= top + canvas.winfo_height())

    def _can_scroll(self) -> bool:
        return self._parent_canvas.yview() != (0.0, 1.0)

    def _wheel(self, event) -> None:
        if sys.platform.startswith("win"):
            units = -int(event.delta / 6)
        elif sys.platform == "darwin":
            # Tk 8.6 reports small deltas, Tk 9 reports multiples of 120
            delta = event.delta / 12 if abs(event.delta) >= 120 else event.delta
            units = -int(delta)
        else:
            units = -1 if getattr(event, "num", 0) == 4 else 1
        if units:
            self._parent_canvas.yview_scroll(units, "units")

    def _touchpad(self, event) -> None:
        try:
            _dx, dy = self.tk.call("tk::PreciseScrollDeltas", event.delta)
        except (tk.TclError, ValueError):
            return
        increment = float(self._parent_canvas.cget("yscrollincrement") or 1) or 1.0
        self._touch_remainder += -float(dy) / increment
        units = int(self._touch_remainder)
        if units:
            self._touch_remainder -= units
            self._parent_canvas.yview_scroll(units, "units")

    def scroll_to_top(self) -> None:
        self._parent_canvas.yview_moveto(0)


# ==========================================================================
# Buttons
# ==========================================================================
def primary_button(master, label: str, command: Callable, **kwargs) -> ctk.CTkButton:
    """Filled accent button — the one main action on a screen."""
    kwargs.setdefault("height", 40)
    kwargs.setdefault("font", T.font(14, "bold"))
    return ctk.CTkButton(
        master, text=label, command=command, corner_radius=T.RADIUS_SM,
        fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
        text_color=T.TEXT_ON_ACCENT, text_color_disabled=T.TEXT_DIM, **kwargs)


def ghost_button(master, label: str, command: Callable, **kwargs) -> ctk.CTkButton:
    """Outlined secondary button."""
    kwargs.setdefault("height", 40)
    kwargs.setdefault("font", T.font(13, "bold"))
    return ctk.CTkButton(
        master, text=label, command=command, corner_radius=T.RADIUS_SM,
        fg_color="transparent", hover_color=T.RAISED, border_width=1,
        border_color=T.BORDER_STRONG, text_color=T.TEXT,
        text_color_disabled=T.TEXT_DIM, **kwargs)


def style_toggle(button: ctk.CTkButton, active: bool) -> None:
    """Restyle an Add/Remove toggle to match its current state."""
    if active:
        button.configure(text="Remove", fg_color="transparent",
                         hover_color=T.DANGER_BG, border_color=T.DANGER,
                         text_color=T.DANGER)
    else:
        button.configure(text="+  Add", fg_color=T.ACCENT_BG,
                         hover_color=T.ACCENT, border_color=T.ACCENT,
                         text_color=T.ACCENT)


# ==========================================================================
# Status indicators
# ==========================================================================
class Badge(ctk.CTkLabel):
    """Small tinted pill: REQUIRED, INSTALLED, CADET, FLIGHT READY..."""

    def __init__(self, master, value: str = "", tone: str = "neutral", **kwargs) -> None:
        fg, bg = T.TONES[tone]
        super().__init__(master, text=value.upper(), font=T.font(10, "bold"),
                         text_color=fg, fg_color=bg, corner_radius=6,
                         height=20, padx=8, **kwargs)

    def set(self, value: str, tone: str = "neutral") -> None:
        fg, bg = T.TONES[tone]
        self.configure(text=value.upper(), text_color=fg, fg_color=bg)


class Chip(ctk.CTkLabel):
    """Compact stat pill used inside catalogue cards (mass, power, cost...)."""

    def __init__(self, master, value: str, tone: str = "neutral", **kwargs) -> None:
        fg = T.TEXT if tone == "neutral" else T.TONES[tone][0]
        super().__init__(master, text=value, font=T.font(12, "bold"),
                         text_color=fg, fg_color=T.RAISED, corner_radius=6,
                         height=24, padx=8, **kwargs)


class StatTile(ctk.CTkFrame):
    """Caption over a large value — the 'headline number' component."""

    def __init__(self, master, caption: str, value: str = "—",
                 tone: str = "neutral", **kwargs) -> None:
        kwargs.setdefault("fg_color", T.RAISED)
        kwargs.setdefault("corner_radius", 10)
        super().__init__(master, **kwargs)
        self._caption = text(self, caption.upper(), (10, "bold"), T.TEXT_DIM)
        self._caption.pack(anchor="w", padx=12, pady=(8, 0))
        self._value = text(self, value, (17, "bold"))
        self._value.pack(anchor="w", padx=12, pady=(0, 8))
        self.set(value, tone)

    def set(self, value: str, tone: str = "neutral") -> None:
        color = T.TEXT if tone == "neutral" else T.TONES[tone][0]
        self._value.configure(text=value, text_color=color)


class Meter(ctk.CTkFrame):
    """Labelled progress bar: caption on the left, reading on the right,
    an optional hint underneath. Colour communicates health."""

    def __init__(self, master, caption: str, **kwargs) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self.grid_columnconfigure(1, weight=1)
        text(self, caption, T.SMALL, T.TEXT_MUTED).grid(row=0, column=0, sticky="w")
        self._value = text(self, "", (12, "bold"), anchor="e")
        self._value.grid(row=0, column=1, sticky="e")
        self._bar = ctk.CTkProgressBar(self, height=8, corner_radius=4,
                                       fg_color=T.RAISED, progress_color=T.ACCENT)
        self._bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self._bar.set(0)
        self._hint = text(self, "", (11, "normal"), T.TEXT_DIM)

    def set(self, fraction: float, value: str, tone: str = "accent",
            hint: str = "") -> None:
        self._bar.set(max(0.0, min(1.0, fraction)))
        self._bar.configure(progress_color=T.TONES[tone][0])
        self._value.configure(
            text=value, text_color=T.TEXT if tone == "accent" else T.TONES[tone][0])
        if hint:
            self._hint.configure(text=hint)
            self._hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))
        else:
            self._hint.grid_remove()


class StatusRow(ctk.CTkFrame):
    """One line of a checklist: coloured marker, label, right-aligned detail."""

    _MARKS = {"success": "✓", "danger": "✕", "warning": "!", "neutral": "•",
              "accent": "•"}

    def __init__(self, master, label: str, **kwargs) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self.grid_columnconfigure(2, weight=1)
        self._mark = text(self, "•", (12, "bold"), T.TEXT_DIM, width=16, anchor="center")
        self._mark.grid(row=0, column=0, padx=(0, 6))
        self._label = text(self, label, T.SMALL, T.TEXT_MUTED)
        self._label.grid(row=0, column=1, sticky="w")
        self._detail = text(self, "", T.SMALL, T.TEXT_DIM, anchor="e")
        self._detail.grid(row=0, column=2, sticky="e", padx=(8, 0))

    def set(self, tone: str, detail: str = "", label: str | None = None) -> None:
        color = T.TONES[tone][0]
        if label is not None:
            self._label.configure(text=label)
        self._mark.configure(text=self._MARKS.get(tone, "•"), text_color=color)
        self._label.configure(text_color=T.TEXT if tone == "success" else T.TEXT_MUTED)
        self._detail.configure(text=detail,
                               text_color=color if tone != "success" else T.TEXT_MUTED)


# ==========================================================================
# Interactive cards
# ==========================================================================
def _descendants(widget: tk.Misc, skip=(ctk.CTkButton, ctk.CTkEntry)):
    """Yield widget and all children, not descending into real controls
    (so a button inside a clickable card keeps its own click)."""
    yield widget
    for child in widget.winfo_children():
        if isinstance(child, skip):
            continue
        yield from _descendants(child, skip)


class SelectableCard(Card):
    """A card that behaves like a big button.

    Hover lifts the surface, selection draws an accent border, and a
    locked card stays visible (so players see what exists) but dimmed.
    Call `finalize()` once all child widgets have been added.
    """

    def __init__(self, master, command: Callable[[], None] | None = None,
                 **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._command = command
        self._selected = False
        self._locked = False
        self._hovered = False

    def finalize(self) -> None:
        """Route clicks and hover from every child to the card itself."""
        self._glossary_texts = []
        for widget in _descendants(self):
            if isinstance(widget, GlossaryText):
                self._glossary_texts.append(widget)
            tk.Misc.bind(widget, "<Button-1>", self._on_click, add="+")
            tk.Misc.bind(widget, "<Enter>", self._on_enter, add="+")
            tk.Misc.bind(widget, "<Leave>", self._on_leave, add="+")
            try:
                widget.configure(cursor="hand2")
            except (tk.TclError, ValueError, NotImplementedError):
                pass
        self._restyle()

    # --- state -----------------------------------------------------------
    def set_selected(self, selected: bool) -> None:
        if selected != self._selected:
            self._selected = selected
            self._restyle()

    def set_locked(self, locked: bool) -> None:
        if locked != self._locked:
            self._locked = locked
            self._restyle()

    @property
    def locked(self) -> bool:
        return self._locked

    def _restyle(self) -> None:
        if self._selected:
            fg, border, width = T.ACCENT_BG, T.ACCENT, 2
        elif self._hovered and not self._locked:
            fg, border, width = T.CARD_HOVER, T.BORDER_STRONG, 1
        else:
            fg, border, width = T.CARD, T.BORDER, 1
        self.configure(fg_color=fg, border_color=border, border_width=width)
        # tk.Text isn't a CTk widget, so it doesn't follow fg_color changes
        for widget in getattr(self, "_glossary_texts", ()):
            widget.sync_bg()

    # --- events ----------------------------------------------------------
    def _on_click(self, event) -> None:
        # A click on a glossary word opens its definition, not the card.
        # (GlossaryText already returns "break"; this is a second guard.)
        widget = event.widget
        if isinstance(widget, GlossaryText) and widget.term_at(event.x, event.y):
            return
        if self._command:
            self._command()

    def _on_enter(self, _event) -> None:
        if not self._hovered:
            self._hovered = True
            self._restyle()

    def _on_leave(self, _event) -> None:
        # <Leave> also fires when moving onto a child: only un-hover once
        # the pointer has really left the card's rectangle.
        x, y = self.winfo_pointerxy()
        inside = (self.winfo_rootx() <= x < self.winfo_rootx() + self.winfo_width()
                  and self.winfo_rooty() <= y < self.winfo_rooty() + self.winfo_height())
        if not inside and self._hovered:
            self._hovered = False
            self._restyle()


class Stepper(ctk.CTkFrame):
    """Numbered wizard steps. Completed steps show a check, the current
    step is filled, and any step can be clicked to jump to it."""

    def __init__(self, master, steps: list[tuple[str, str]],
                 command: Callable[[str], None], **kwargs) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._steps = steps
        self._buttons: list[ctk.CTkButton] = []
        for index, (key, title) in enumerate(steps):
            self.grid_columnconfigure(index, weight=1, uniform="step")
            button = ctk.CTkButton(
                self, text=title, height=36, corner_radius=T.RADIUS_SM,
                font=T.font(12, "bold"), border_width=1,
                command=lambda k=key: command(k))
            button.grid(row=0, column=index, sticky="ew",
                        padx=(0 if index == 0 else 6, 0))
            self._buttons.append(button)
        self._progress = ctk.CTkProgressBar(self, height=3, corner_radius=2,
                                            fg_color=T.RAISED, progress_color=T.ACCENT)
        self._progress.grid(row=1, column=0, columnspan=len(steps), sticky="ew",
                            pady=(10, 0))

    def set_current(self, index: int) -> None:
        for i, (button, (_key, title)) in enumerate(zip(self._buttons, self._steps)):
            if i == index:
                button.configure(text=f"{i + 1}   {title}", fg_color=T.ACCENT,
                                 hover_color=T.ACCENT_HOVER, border_color=T.ACCENT,
                                 text_color=T.TEXT_ON_ACCENT)
            elif i < index:
                button.configure(text=f"✓   {title}", fg_color=T.SURFACE,
                                 hover_color=T.RAISED, border_color=T.BORDER,
                                 text_color=T.SUCCESS)
            else:
                button.configure(text=f"{i + 1}   {title}", fg_color=T.SURFACE,
                                 hover_color=T.RAISED, border_color=T.BORDER,
                                 text_color=T.TEXT_MUTED)
        self._progress.set((index + 1) / len(self._steps))


# ==========================================================================
# Canvas-drawn pieces
# ==========================================================================
def draw_stars(canvas: tk.Canvas, width: int, height: int, count: int,
               seed: int = 7, tag: str = "star") -> None:
    """Scatter a deterministic star field over a canvas."""
    rng = random.Random(seed)
    shades = ["#2B3A57", "#44557A", "#6B7FA8", "#A9B8D8", "#E8EEFA"]
    for _ in range(count):
        x, y = rng.uniform(0, width), rng.uniform(0, height)
        # Most stars are faint pinpricks; a few are bright and larger
        level = min(4, int(rng.random() ** 2 * 5))
        r = 0.6 if level < 3 else (1.0 if level == 3 else 1.5)
        canvas.create_oval(x - r, y - r, x + r, y + r, fill=shades[level],
                           outline="", tags=tag)


def draw_vertical_gradient(canvas: tk.Canvas, width: int, height: int,
                           top: str, bottom: str, steps: int = 48,
                           tag: str = "gradient") -> None:
    """Paint a top-to-bottom gradient as thin horizontal bands."""
    def channels(color: str) -> tuple[int, int, int]:
        return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))

    c0, c1 = channels(top), channels(bottom)
    band = height / steps
    for i in range(steps):
        t = i / (steps - 1)
        r, g, b = (round(c0[k] + (c1[k] - c0[k]) * t) for k in range(3))
        canvas.create_rectangle(0, i * band, width, (i + 1) * band + 1,
                                fill=f"#{r:02x}{g:02x}{b:02x}", outline="", tags=tag)


class ScoreRing(tk.Canvas):
    """Circular gauge that counts up to the final mission score."""

    def __init__(self, master, size: int = 168, bg: str = T.CARD) -> None:
        super().__init__(master, width=size, height=size, bg=bg,
                         highlightthickness=0)
        self._size = size
        self._after_id = None
        self._draw(0, T.TEXT_DIM, "—")

    def _draw(self, fraction: float, color: str, label: str) -> None:
        self.delete("all")
        pad, width = 14, 12
        box = (pad, pad, self._size - pad, self._size - pad)
        self.create_oval(*box, outline=T.RAISED, width=width)
        if fraction > 0:
            self.create_arc(*box, start=90, extent=-359.9 * min(1.0, fraction),
                            style="arc", outline=color, width=width)
        mid = self._size / 2
        self.create_text(mid, mid - 6, text=label, fill=T.TEXT,
                         font=T.canvas_font(34, bold=True))
        self.create_text(mid, mid + 26, text="OUT OF 100", fill=T.TEXT_DIM,
                         font=T.canvas_font(10, bold=True))

    def show(self, score: float, animate: bool = True) -> None:
        """Animate the ring from zero up to `score` (0-100)."""
        self.cancel()
        color = T.TONES[T.score_tone(score)][0]
        if not animate:
            self._draw(score / 100, color, f"{score:g}")
            return
        frames = 30

        def step(frame: int) -> None:
            eased = 1 - (1 - frame / frames) ** 3      # ease-out cubic
            value = score * eased
            label = f"{score:g}" if frame == frames else f"{value:.0f}"
            self._draw(value / 100, color, label)
            if frame < frames:
                self._after_id = self.after(22, step, frame + 1)

        step(0)

    def cancel(self) -> None:
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None

    def destroy(self) -> None:
        self.cancel()
        super().destroy()


class Toast(ctk.CTkFrame):
    """Non-blocking notification that slides in at the top-right of the
    window and dismisses itself (replaces modal 'Notice' pop-ups)."""

    _current: "Toast | None" = None

    def __init__(self, root, message: str, tone: str = "warning",
                 duration_ms: int = 3800) -> None:
        if Toast._current is not None and Toast._current.winfo_exists():
            Toast._current.destroy()
        fg, bg = T.TONES[tone]
        super().__init__(root, fg_color=bg, corner_radius=T.RADIUS_SM,
                         border_width=1, border_color=fg)
        Toast._current = self
        icon = {"danger": "✕", "success": "✓", "accent": "i"}.get(tone, "!")
        text(self, icon, (13, "bold"), fg, width=18, anchor="center").pack(
            side="left", padx=(14, 6), pady=12)
        text(self, message, (13, "normal"), T.TEXT, wraplength=340).pack(
            side="left", padx=(0, 16), pady=12)
        self.place(relx=1.0, y=T.PAD, x=-T.PAD_LG, anchor="ne")
        self.lift()
        self.after(duration_ms, self._dismiss)

    def _dismiss(self) -> None:
        if self.winfo_exists():
            self.destroy()
        if Toast._current is self:
            Toast._current = None
