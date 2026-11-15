"""Planet Facts screen."""

from __future__ import annotations

import customtkinter as ctk

from src.game.planets import score_orbit_for
from src.ui import assets
from src.ui import theme as T
from src.ui.screens.base import Screen
from src.ui.widgets import (Card, Meter, ScrollFrame, StatTile, StatusRow, eyebrow,
                            ghost_button, glossary_text, text)


def _day_length(hours: float) -> str:
    return f"{hours:.1f} h" if hours < 48 else f"{hours / 24:,.1f} Earth days"


class FactsScreen(Screen):
    key = "facts"
    title = "Planet Facts"
    subtitle = "Know your target before you commit to flying there."
    show_telemetry = False

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.page_header().grid(row=0, column=0, sticky="ew", pady=(0, T.PAD))
        self.body = ScrollFrame(self)
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.grid_columnconfigure(0, weight=1)
        self._shown = object()      # destination currently rendered

    def refresh(self) -> None:
        m = self.mission
        key = (m.destination.id if m.destination else None,
               m.orbit.id if m.orbit else None)
        if key == self._shown:
            return
        self._shown = key
        for child in self.body.winfo_children():
            child.destroy()
        if m.destination is None:
            self._empty()
        else:
            self._render(m.destination)
        self.body.scroll_to_top()

    def _empty(self) -> None:
        card = Card(self.body)
        card.grid(sticky="ew", padx=(0, T.PAD_SM))
        text(card, "No destination selected yet", T.H2).pack(pady=(T.PAD_XL, 4))
        text(card, "Pick a launch vehicle in “Orbit & Launch”, then choose a "
                   "world within its range.", T.BODY, T.TEXT_MUTED).pack()
        ghost_button(card, "Go to Orbit & Launch",
                     lambda: self.app.show_screen("orbit"), width=220).pack(
            pady=(T.PAD, T.PAD_XL))

    def _render(self, p) -> None:
        hero = Card(self.body)
        hero.grid(sticky="ew", padx=(0, T.PAD_SM))
        hero.grid_columnconfigure(1, weight=1)
        image = assets.planet_image(p.id, 168)
        ctk.CTkLabel(hero, text="" if image else "●", image=image,
                     text_color=p.color, font=T.font(120, "bold")).grid(
            row=0, column=0, rowspan=3, padx=T.PAD_LG, pady=T.PAD_LG)
        eyebrow(hero, "Destination").grid(row=0, column=1, sticky="sw", pady=(T.PAD_LG, 0))
        text(hero, p.name, T.DISPLAY).grid(row=1, column=1, sticky="w")
        text(hero, p.distance_label, T.BODY, T.TEXT_MUTED).grid(
            row=2, column=1, sticky="nw", pady=(0, T.PAD_LG))

        tiles = ctk.CTkFrame(self.body, fg_color="transparent")
        tiles.grid(sticky="ew", pady=T.PAD, padx=(0, T.PAD_SM))
        tiles.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="t")
        for i, (caption, value) in enumerate([
                ("Diameter", f"{p.diameter_km:,.0f} km"),
                ("Length of day", _day_length(p.day_hours)),
                ("Moons", f"{p.moons}"),
                ("From the Sun", f"{p.distance_au:g} AU")]):
            StatTile(tiles, caption, value, fg_color=T.CARD).grid(
                row=0, column=i, sticky="ew", padx=(0 if i == 0 else T.PAD_SM, 0))

        eyebrow(self.body, "Fun facts", T.VIOLET_TEXT).grid(sticky="w", pady=(T.PAD_SM, 8))
        for i, fact in enumerate(p.facts, 1):
            card = Card(self.body)
            card.grid(sticky="ew", pady=(0, T.PAD_SM), padx=(0, T.PAD_SM))
            card.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(card, text=f"{i:02d}", width=40, height=40, corner_radius=10,
                         fg_color=T.VIOLET_BG, text_color=T.VIOLET_TEXT,
                         font=T.font(14, "bold")).grid(row=0, column=0, padx=T.PAD,
                                                       pady=14)
            glossary_text(card, fact, (14, "normal")).grid(
                row=0, column=1, sticky="ew", padx=(0, T.PAD))

        if self.mission.orbit is not None:
            orbit = self.mission.orbit
            score, reasons = score_orbit_for(orbit, p)
            card = Card(self.body)
            card.grid(sticky="ew", pady=(T.PAD_SM, T.PAD), padx=(0, T.PAD_SM))
            card.grid_columnconfigure(0, weight=1)
            eyebrow(card, "Your orbit choice").grid(sticky="w", padx=T.PAD, pady=(T.PAD, 8))
            meter = Meter(card, orbit.name)
            meter.grid(sticky="ew", padx=T.PAD)
            meter.set(score / 100, f"{score:.0f} / 100", T.score_tone(score))
            rows = ctk.CTkFrame(card, fg_color="transparent")
            rows.grid(sticky="ew", padx=T.PAD, pady=(10, T.PAD))
            rows.grid_columnconfigure(0, weight=1)
            for reason in reasons:
                good = any(w in reason for w in ("matches", "excellent"))
                row = StatusRow(rows, reason)
                row.set("success" if good else "warning")
                row.grid(sticky="ew", pady=1)
