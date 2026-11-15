"""Welcome screen: hero artwork on the left, mission setup on the right."""

from __future__ import annotations

import math
import tkinter as tk
from typing import Callable

import customtkinter as ctk

from src.game.planets import MAX_BUDGET_USD, MIN_BUDGET_USD
from src.ui import assets
from src.ui import theme as T
from src.ui.widgets import (Badge, Card, Chip, ScrollFrame, SelectableCard,
                            StatusRow, draw_stars, draw_vertical_gradient,
                            eyebrow, glossary_text, primary_button, text)


class WelcomeView(ctk.CTkFrame):
    """Pick a commander name and a scenario, then start designing."""

    PANEL_WIDTH = 520

    def __init__(self, master, scenarios: dict, on_start: Callable) -> None:
        super().__init__(master, fg_color=T.BG, corner_radius=0)
        self.scenarios = scenarios
        self.on_start = on_start
        self.selected = None
        self._cards: dict[str, SelectableCard] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, minsize=self.PANEL_WIDTH)
        self.grid_rowconfigure(0, weight=1)

        self.hero = tk.Canvas(self, bg=T.BG, highlightthickness=0)
        self.hero.grid(row=0, column=0, sticky="nsew")
        self.hero.bind("<Configure>", lambda e: self._draw_hero(e.width, e.height))

        self._build_panel()

    # ------------------------------------------------------------------
    # Hero artwork (pure canvas drawing, redrawn on resize)
    # ------------------------------------------------------------------
    def _draw_hero(self, w: int, h: int) -> None:
        c = self.hero
        c.delete("all")
        draw_vertical_gradient(c, w, h, "#1A0F45", T.BG)   # electric-violet dusk
        draw_stars(c, w, h, count=w * h // 2600, seed=11)

        # The copy goes in first so the artwork can be laid out *around* it:
        # nothing decorative is allowed inside the text's bounding box.
        keep_out = self._draw_copy(w, h)
        self._draw_artwork(w, h, keep_out)
        c.tag_raise("copy")

    def _draw_copy(self, w: int, h: int) -> tuple[float, float, float, float]:
        """Draw the headline block; return its padded bounding box."""
        c = self.hero
        left, top = 56, max(48, h * 0.11)
        eyebrow_id = c.create_text(left, top, anchor="nw", tags="copy",
                                   text="SPACE MISSION DESIGN GAME", fill=T.ACCENT,
                                   font=T.canvas_font(12, bold=True))
        # Each block sits under the *measured* bottom of the one above
        # (c.bbox), never an estimated line height — font metrics differ
        # per platform, so estimates overlap.
        title_size = 54 if w > 760 else 40
        title = c.create_text(left, c.bbox(eyebrow_id)[3] + 12, anchor="nw", tags="copy",
                              text="Design.\nBuild.\nLaunch.", fill=T.TEXT,
                              font=T.canvas_font(title_size, bold=True))
        body = c.create_text(left, c.bbox(title)[3] + 24, anchor="nw", tags="copy",
                             width=min(460, w - 2 * left),
                             text="Plan a real science mission under real constraints — "
                                  "budget, launch mass, power and data — then fly it "
                                  "and learn from every trade-off.",
                             fill=T.TEXT_MUTED, font=T.canvas_font(15))
        c.create_text(left, c.bbox(body)[3] + 28, anchor="nw", tags="copy",
                      text="15 BUS COMPONENTS   ·   6 INSTRUMENTS   ·   8 DESTINATIONS",
                      fill=T.TEXT_DIM, font=T.canvas_font(11, bold=True))
        x0, y0, x1, y1 = c.bbox("copy")
        pad = 28
        return x0 - pad, y0 - pad, x1 + pad, y1 + pad

    def _draw_artwork(self, w: int, h: int, keep_out) -> None:
        """Earth, a transfer arc to Mars, the Moon and a rocket — all
        positioned so they never cross the `keep_out` text box."""
        c = self.hero
        kx0, ky0, kx1, ky1 = keep_out

        def hits_text(x: float, y: float, r: float = 0.0) -> bool:
            return kx0 - r < x < kx1 + r and ky0 - r < y < ky1 + r

        # Big Earth rising from the bottom-left corner
        earth_h = int(min(w, h) * 0.62)
        ex, ey = w * 0.16, h + earth_h * 0.18
        # Dedicated high-res art for the hero; falls back to the small sprite
        art = assets.PLANET_DIR / "earth_welcome.png"
        if not art.exists():
            art = assets.PLANET_DIR / "earth.png"
        earth = assets.canvas_photo(art, earth_h)
        if earth:
            c.create_image(ex, ey, image=earth)
        start = (ex + earth_h * 0.30, ey - earth_h * 0.42)   # on Earth's limb

        # Mars: right of the text if there is room, otherwise below it.
        # The arc bows toward the bottom-right (control point under Mars),
        # i.e. away from the text in the top-left.
        mars_h = max(24, int(h * 0.09))
        mars_r = mars_h / 2
        mx = min(w - mars_r - 24, max(w * 0.84, kx1 + mars_r + 24))
        my = h * 0.30

        def arc(end_x: float, end_y: float) -> list[tuple[float, float]]:
            ctrl = (end_x, start[1])
            return [((1 - t) ** 2 * start[0] + 2 * (1 - t) * t * ctrl[0] + t ** 2 * end_x,
                     (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * ctrl[1] + t ** 2 * end_y)
                    for t in (i / 60 for i in range(61))]

        pts = arc(mx, my)
        while (hits_text(mx, my, mars_r) or any(hits_text(x, y, 6) for x, y in pts)) \
                and my < start[1] - mars_h:
            my += 12                    # slide Mars down until everything clears
            pts = arc(mx, my)

        c.create_line(*[v for p in pts for v in p], fill=T.OUTBOUND, width=2, dash=(6, 5))
        mars = assets.canvas_photo(assets.PLANET_DIR / "mars.png", mars_h)
        if mars:
            c.create_image(mx, my, image=mars)

        # Rocket two-thirds of the way along the arc, nose along the path
        (x0, y0), (x1, y1) = pts[38], pts[40]
        heading = math.degrees(math.atan2(-(y1 - y0), x1 - x0))   # CCW from +x
        rocket = assets.canvas_photo(assets.ROCKET_PATH, max(28, int(h * 0.07)),
                                     rotate_deg=heading - 90)
        if rocket:
            c.create_image(x0, y0, image=rocket)

        # Moon: first free spot that clears the text and stays off the arc
        moon_h = max(16, int(h * 0.045))
        for px, py in ((w * 0.58, h * 0.60), (w * 0.46, h * 0.72), (w * 0.70, h * 0.84)):
            clear_of_arc = all(math.hypot(px - x, py - y) > moon_h + 18 for x, y in pts)
            if not hits_text(px, py, moon_h) and clear_of_arc:
                moon = assets.canvas_photo(assets.PLANET_DIR / "moon.png", moon_h)
                if moon:
                    c.create_image(px, py, image=moon)
                break

    # ------------------------------------------------------------------
    # Setup panel
    # ------------------------------------------------------------------
    def _build_panel(self) -> None:
        panel = ctk.CTkFrame(self, fg_color=T.SURFACE, corner_radius=0,
                             width=self.PANEL_WIDTH)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        body = ScrollFrame(panel)
        body.grid(row=0, column=0, sticky="nsew", padx=(T.PAD_LG, T.PAD_SM),
                  pady=(T.PAD_LG, 0))
        body.grid_columnconfigure(0, weight=1)

        eyebrow(body, "New mission").grid(sticky="w", pady=(T.PAD_SM, 2))
        text(body, "Mission setup", T.H1).grid(sticky="w")

        text(body, "Commander name", T.SMALL, T.TEXT_MUTED).grid(
            sticky="w", pady=(T.PAD_LG, 6))
        self.name_entry = ctk.CTkEntry(
            body, height=42, placeholder_text="Commander", font=T.font(14),
            fg_color=T.RAISED, border_color=T.BORDER, border_width=1,
            text_color=T.TEXT, placeholder_text_color=T.TEXT_DIM,
            corner_radius=T.RADIUS_SM)
        self.name_entry.grid(sticky="ew", padx=(0, T.PAD_SM))
        self.name_entry.bind("<Return>", lambda _e: self._start())

        text(body, "Choose a scenario", T.SMALL, T.TEXT_MUTED).grid(
            sticky="w", pady=(T.PAD_LG, 6))
        for scenario in self.scenarios.values():
            card = self._scenario_card(body, scenario)
            card.grid(sticky="ew", pady=(0, 10), padx=(0, T.PAD_SM))
            self._cards[scenario.id] = card

        # Mission brief appears once a scenario is picked
        self.brief = Card(body, fg_color=T.CARD)
        self.brief.grid_columnconfigure(0, weight=1)
        eyebrow(self.brief, "Mission brief", T.VIOLET_TEXT).grid(
            sticky="w", padx=T.PAD, pady=(T.PAD, 4))
        self.brief_objective = glossary_text(self.brief, "", (14, "bold"))
        self.brief_objective.grid(sticky="ew", padx=T.PAD)
        self.brief_rows = ctk.CTkFrame(self.brief, fg_color="transparent")
        self.brief_rows.grid(sticky="ew", padx=T.PAD, pady=(10, T.PAD))
        self.brief_rows.grid_columnconfigure(0, weight=1)

        # Footer: start button pinned below the scroll area
        footer = ctk.CTkFrame(panel, fg_color="transparent")
        footer.grid(row=1, column=0, sticky="ew", padx=T.PAD_LG, pady=T.PAD_LG)
        footer.grid_columnconfigure(0, weight=1)
        self.start_btn = primary_button(footer, "Select a scenario to begin",
                                        self._start, height=48, state="disabled")
        self.start_btn.grid(sticky="ew")

    def _scenario_card(self, parent, scenario) -> SelectableCard:
        card = SelectableCard(parent, command=lambda s=scenario: self._select(s))
        card.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(sticky="ew", padx=T.PAD, pady=(14, 0))
        top.grid_columnconfigure(0, weight=1)
        glossary_text(top, scenario.name, T.H3).grid(row=0, column=0, sticky="ew",
                                                     padx=(0, T.PAD_SM))
        Badge(top, *assets.difficulty_tone(scenario)).grid(row=0, column=1, sticky="e")

        glossary_text(card, scenario.description, T.SMALL, T.TEXT_MUTED).grid(
            sticky="ew", padx=T.PAD, pady=(4, 0))

        chips = ctk.CTkFrame(card, fg_color="transparent")
        chips.grid(sticky="w", padx=T.PAD, pady=(10, 14))
        budget = (f"Budget {T.money(MIN_BUDGET_USD)}–{T.money(MAX_BUDGET_USD)}"
                  if scenario.sandbox_mode
                  else f"Budget {T.money(scenario.effective_budget())}")
        Chip(chips, budget).pack(side="left")
        Chip(chips, f"{scenario.mission_months} months").pack(side="left", padx=6)
        goals = len(scenario.required_objectives)
        Chip(chips, f"{goals} objective{'s' if goals != 1 else ''}" if goals
             else "Free play").pack(side="left")
        card.finalize()
        return card

    def _select(self, scenario) -> None:
        self.selected = scenario
        for sid, card in self._cards.items():
            card.set_selected(sid == scenario.id)

        self.brief_objective.set_text(scenario.objective)
        for child in self.brief_rows.winfo_children():
            child.destroy()
        lines = [f"Objective: {o.replace('_', ' ')}" for o in scenario.required_objectives]
        lines += [f"Payload capability: {c.replace('_', ' ')}"
                  for c in scenario.required_capabilities]
        if scenario.allowed_orbits:
            lines.append("Allowed orbits: " + ", ".join(o.upper() for o in scenario.allowed_orbits))
        if scenario.sandbox_mode:
            lines.append("Sandbox: rule violations become warnings")
            lines.append("Pick any destination — farther worlds get bigger budgets")
        else:
            lines.append(f"Budget: {T.money(scenario.effective_budget())} "
                         f"({scenario.difficulty} difficulty)")
        for line in lines or ["No hard requirements"]:
            row = StatusRow(self.brief_rows, line)
            row.set("accent")
            row.grid(sticky="ew", pady=1)
        self.brief.grid(sticky="ew", pady=(T.PAD_SM, T.PAD), padx=(0, T.PAD_SM))
        self.start_btn.configure(state="normal", text=f"Begin {scenario.name}  →")

    def _start(self) -> None:
        if self.selected is None:
            return
        name = self.name_entry.get().strip() or "Commander"
        self.on_start(name, self.selected)
