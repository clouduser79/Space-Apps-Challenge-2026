"""Flight Path (animated trajectory) and Planet Facts screens."""

from __future__ import annotations

import customtkinter as ctk

from src.game.planets import score_orbit_for
from src.ui import assets
from src.ui import theme as T
from src.ui.screens.base import Screen
from src.ui.screens.orbit import short_distance
from src.ui.trajectory_view import TrajectoryCanvas
from src.ui.widgets import (Card, Meter, ScrollFrame, StatTile, StatusRow, eyebrow,
                            ghost_button, glossary_text, primary_button, text)


def _day_length(hours: float) -> str:
    return f"{hours:.1f} h" if hours < 48 else f"{hours / 24:,.1f} Earth days"


class FlightScreen(Screen):
    key = "flight"
    title = "Flight Path"
    subtitle = ("Your 2D transfer: out along the blue arc, two laps of a parking "
                "orbit, a spiral departure, then home on the violet arc.")
    show_telemetry = False

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, T.PAD))
        head.grid_columnconfigure(0, weight=1)
        self.page_header(head).grid(row=0, column=0, sticky="ew")
        self.fly_btn = primary_button(head, "▶  Animate transfer", self._animate,
                                      width=200, height=44)
        self.fly_btn.grid(row=0, column=1, sticky="e", padx=(T.PAD, 0))

        tiles = ctk.CTkFrame(self, fg_color="transparent")
        tiles.grid(row=1, column=0, sticky="ew", pady=(0, T.PAD))
        tiles.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="t")
        self.tiles = {}
        for i, (key, caption) in enumerate([("dest", "Destination"),
                                            ("dist", "Distance"),
                                            ("lv", "Launch vehicle"),
                                            ("orbit", "Parking orbit")]):
            tile = StatTile(tiles, caption, fg_color=T.CARD)
            tile.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else T.PAD_SM, 0))
            self.tiles[key] = tile

        frame = Card(self, fg_color=T.BG)
        frame.grid(row=2, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        self.trajectory = TrajectoryCanvas(frame)
        self.trajectory.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

        self.status = text(self, "", T.SMALL, T.TEXT_MUTED)
        self.status.grid(row=3, column=0, sticky="ew", pady=(10, 0))

    def refresh(self) -> None:
        m = self.mission
        d = m.destination
        self.tiles["dest"].set(d.name if d else "—", "accent" if d else "neutral")
        self.tiles["dist"].set(short_distance(d.distance_label) if d else "—")
        self.tiles["lv"].set(m.launch_vehicle.name if m.launch_vehicle else "—")
        self.tiles["orbit"].set(m.orbit.name.split(" (")[0] if m.orbit else "—")
        if self.trajectory.is_animating:
            return
        if d is None:
            self.trajectory.show_empty()
            self.fly_btn.configure(state="disabled")
            self.status.configure(text="No destination yet — choose one in "
                                       "“Orbit & Launch”.")
        else:
            self.trajectory.plot(d)
            self.fly_btn.configure(state="normal")
            self.status.configure(text=f"Trajectory plotted to {d.name}. Press "
                                       "Animate to fly it.")

    def on_hide(self) -> None:
        self.trajectory.cancel_animation()

    def _animate(self) -> None:
        dest = self.mission.destination
        if dest is None:
            return
        self.fly_btn.configure(state="disabled", text="In flight…")
        self.status.configure(text="Rocket in transit — outbound → orbit → return.",
                              text_color=T.ACCENT)
        self.trajectory.animate(dest, on_done=lambda: self.after(0, self._landed))

    def _landed(self) -> None:
        if not self.winfo_exists():
            return
        self.fly_btn.configure(state="normal", text="▶  Fly again")
        if self.trajectory.flight_completed:
            self.status.configure(text=f"✓  Round trip to {self.mission.destination.name} "
                                       "complete. Welcome home!", text_color=T.SUCCESS)
        else:
            self.status.configure(text="Flight interrupted.", text_color=T.TEXT_MUTED)


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

        eyebrow(self.body, "Fun facts", T.VIOLET).grid(sticky="w", pady=(T.PAD_SM, 8))
        for i, fact in enumerate(p.facts, 1):
            card = Card(self.body)
            card.grid(sticky="ew", pady=(0, T.PAD_SM), padx=(0, T.PAD_SM))
            card.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(card, text=f"{i:02d}", width=40, height=40, corner_radius=10,
                         fg_color=T.VIOLET_BG, text_color=T.VIOLET,
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
