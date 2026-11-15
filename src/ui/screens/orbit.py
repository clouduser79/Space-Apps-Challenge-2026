"""Orbit & Launch screen: pick an orbit, a launch vehicle and a destination.

The game rules are unchanged from the original UI:
  * orbits outside the scenario's allowed list can't be chosen,
  * the launch vehicle decides which destinations are reachable, and
    changing it clears a destination that is no longer reachable,
  * GMAT is queried in the background for real orbital parameters.
"""

from __future__ import annotations

import threading

import customtkinter as ctk

from src.game.gmat_bridge import get_bridge
from src.game.launch_vehicle import orbit_capacity_class
from src.game.shop import is_unlocked, price_of
from src.game.planets import (MAX_BUDGET_USD, MIN_BUDGET_USD, PLANETS, budget_for,
                               reachable_planets, score_orbit_for)
from src.ui import assets
from src.ui import theme as T
from src.ui.screens.base import Screen
from src.ui.widgets import (Badge, Card, Chip, Meter, ScrollFrame, SelectableCard,
                            StatusRow, eyebrow, glossary_text, text)


def lv_tier(lv) -> str:
    """Size class by price, used as a badge."""
    if lv.cost_usd < 50_000_000:
        return "Light"
    if lv.cost_usd < 500_000_000:
        return "Medium"
    return "Heavy"


def short_distance(label: str) -> str:
    """'~225 million km from Earth (at closest)' -> '~225 million km'."""
    return label.split(" from ")[0]


class OrbitLaunchScreen(Screen):
    key = "orbit"
    title = "Orbit & Launch"
    subtitle = ("Where will you operate, what will get you there, and which "
                "world is the target? All three are required to continue.")

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.page_header().grid(row=0, column=0, sticky="ew", pady=(0, T.PAD))
        self.body = ScrollFrame(self)
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.grid_columnconfigure(0, weight=1)

        self.orbit_cards: dict[str, SelectableCard] = {}
        self.orbit_badges: dict[str, Badge] = {}
        self.lv_cards: dict[str, SelectableCard] = {}
        self.lv_fit: dict[str, Badge] = {}
        self.planet_cards: dict[str, SelectableCard] = {}
        self.planet_badges: dict[str, Badge] = {}
        self._gmat_cache: dict[str, dict | None] = {}
        self._gmat_pending: set[str] = set()

        self._build_orbits()
        self._build_launchers()
        self._build_destinations()

    # ------------------------------------------------------------------
    # Section scaffolding
    # ------------------------------------------------------------------
    def _section(self, number: int, title: str, blurb: str) -> ctk.CTkFrame:
        head = ctk.CTkFrame(self.body, fg_color="transparent")
        head.grid(sticky="ew", pady=(0 if number == 1 else T.PAD_XL, 10),
                  padx=(0, T.PAD_SM))
        head.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(head, text=str(number), width=28, height=28, corner_radius=14,
                     fg_color=T.ACCENT_BG, text_color=T.ACCENT,
                     font=T.font(13, "bold")).grid(row=0, column=0, rowspan=2,
                                                   sticky="n", padx=(0, 12))
        glossary_text(head, title, T.H2).grid(row=0, column=1, sticky="ew")
        glossary_text(head, blurb, T.SMALL, T.TEXT_DIM).grid(row=1, column=1, sticky="ew")

        grid = ctk.CTkFrame(self.body, fg_color="transparent")
        grid.grid(sticky="ew", padx=(0, T.PAD_SM))
        return grid

    @staticmethod
    def _place(grid, cards, columns: int) -> None:
        for col in range(columns):
            grid.grid_columnconfigure(col, weight=1, uniform="c")
        for i, card in enumerate(cards):
            card.grid(row=i // columns, column=i % columns, sticky="nsew",
                      padx=(0 if i % columns == 0 else T.PAD_SM, 0), pady=(0, T.PAD_SM))

    # ------------------------------------------------------------------
    # 1. Orbit
    # ------------------------------------------------------------------
    def _build_orbits(self) -> None:
        grid = self._section(1, "Operating orbit", "Altitude and inclination set "
                             "coverage, drag, radiation and how often you can "
                             "talk to the ground.")
        cards = []
        for oid, o in self.app.orbits.items():
            card = SelectableCard(grid, command=lambda o=o: self._pick_orbit(o))
            card.grid_columnconfigure(0, weight=1)
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.grid(sticky="ew", padx=T.PAD, pady=(14, 0))
            top.grid_columnconfigure(0, weight=1)
            text(top, o.body.upper(), T.CAPTION, T.TEXT_DIM).grid(row=0, column=0, sticky="w")
            badge = Badge(top, "")
            badge.grid(row=0, column=1, sticky="e")
            self.orbit_badges[oid] = badge
            glossary_text(card, o.name, T.H3).grid(sticky="ew", padx=T.PAD, pady=(4, 0))
            glossary_text(card, o.description, T.SMALL, T.TEXT_MUTED).grid(
                sticky="ew", padx=T.PAD, pady=(4, 0))
            chips = ctk.CTkFrame(card, fg_color="transparent")
            chips.grid(sticky="w", padx=T.PAD, pady=(10, 14))
            Chip(chips, f"{o.altitude_km:,.0f} km").pack(side="left")
            Chip(chips, f"{o.inclination_deg:g}°").pack(side="left", padx=6)
            Chip(chips, f"{o.period_hours:g} h").pack(side="left")
            card.finalize()
            self.orbit_cards[oid] = card
            cards.append(card)
        self._place(grid, cards, 3)

        # Detail card for the chosen orbit (+ GMAT results)
        self.orbit_detail = Card(self.body)
        self.orbit_detail.grid(sticky="ew", padx=(0, T.PAD_SM), pady=(T.PAD_SM, 0))
        self.orbit_detail.grid_columnconfigure(0, weight=1)
        eyebrow(self.orbit_detail, "Orbit analysis").grid(sticky="w", padx=T.PAD,
                                                          pady=(T.PAD, 4))
        self.orbit_explain = glossary_text(self.orbit_detail, "", T.BODY)
        self.orbit_explain.grid(sticky="ew", padx=T.PAD)
        self.gmat_row = ctk.CTkFrame(self.orbit_detail, fg_color="transparent")
        self.gmat_row.grid(sticky="ew", padx=T.PAD, pady=(10, T.PAD))
        self.gmat_badge = Badge(self.gmat_row, "GMAT", "accent")
        self.gmat_badge.pack(side="left")
        self.gmat_text = text(self.gmat_row, "", T.SMALL, T.TEXT_MUTED)
        self.gmat_text.pack(side="left", padx=10)

    def _shop_locked(self, item_id: str, in_use: bool) -> bool:
        """True (and opens the shop on that item) if it must be bought first."""
        if in_use or is_unlocked(self.app.profile, item_id):
            return False
        self.app.open_shop(focus=item_id)
        return True

    def _pick_orbit(self, orbit) -> None:
        m = self.mission
        if self._shop_locked(orbit.id, m.orbit is not None and m.orbit.id == orbit.id):
            return
        allowed = self.mission.scenario.allowed_orbits
        if allowed and orbit.id not in allowed:
            self.app.toast(f"{orbit.name} is not allowed in this scenario.")
            return
        try:
            self.mission.set_orbit(orbit)
        except ValueError as exc:
            self.app.toast(str(exc), "danger")
            return
        self._fetch_gmat(orbit)
        self.app.on_design_changed()

    def _fetch_gmat(self, orbit) -> None:
        """Run GMAT off the UI thread; results are picked up by polling
        (Tk widgets must only be touched from the main thread)."""
        if orbit.id in self._gmat_cache or orbit.id in self._gmat_pending:
            return
        self._gmat_pending.add(orbit.id)
        box: dict = {}

        def worker() -> None:
            try:
                box["data"] = get_bridge().orbit_properties(
                    orbit.body, orbit.altitude_km, orbit.inclination_deg)
            except Exception:          # GMAT problems must never crash the game
                box["data"] = None

        def poll() -> None:
            if "data" not in box:
                self.after(150, poll)
                return
            self._gmat_pending.discard(orbit.id)
            self._gmat_cache[orbit.id] = box["data"]
            if self.winfo_exists():
                self._refresh_orbit_detail()

        threading.Thread(target=worker, daemon=True).start()
        self.after(150, poll)

    def _refresh_orbit_detail(self) -> None:
        o = self.mission.orbit
        if o is None:
            self.orbit_explain.set_text(
                "Select an orbit to see what it means for your mission.", T.TEXT_DIM)
            self.gmat_row.grid_remove()
            return
        self.orbit_explain.set_text(o.educational_explanation(), T.TEXT)
        self.gmat_row.grid()
        if o.id in self._gmat_pending:
            self.gmat_badge.set("GMAT", "accent")
            self.gmat_text.configure(text="Propagating orbit with GMAT…")
        elif self._gmat_cache.get(o.id):
            d = self._gmat_cache[o.id]
            self.gmat_badge.set("GMAT", "success")
            self.gmat_text.configure(
                text=f"Velocity {d['velocity_km_s']:.2f} km/s   ·   Period "
                     f"{d['period_min']:.1f} min   ·   SMA {d['sma_km']:,.0f} km   ·   "
                     f"Ecc {d['ecc']:.4f}")
        else:
            self.gmat_badge.set("Catalogue", "neutral")
            self.gmat_text.configure(
                text=f"GMAT unavailable on this machine — using catalogue values "
                     f"(coverage: {o.coverage}, radiation {o.radiation_level}/5, "
                     f"{o.comms_passes_per_day} ground passes/day).")

    # ------------------------------------------------------------------
    # 2. Launch vehicle
    # ------------------------------------------------------------------
    def _build_launchers(self) -> None:
        grid = self._section(2, "Launch vehicle", "Bigger rockets lift more and "
                             "reach farther — at a steep price. Reliability is "
                             "your odds of reaching orbit at all.")
        cards = []
        for lv in sorted(self.app.launch_vehicles.values(), key=lambda v: v.cost_usd):
            card = SelectableCard(grid, command=lambda v=lv: self._pick_lv(v))
            card.grid_columnconfigure(0, weight=1)
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.grid(sticky="ew", padx=T.PAD, pady=(14, 0))
            top.grid_columnconfigure(0, weight=1)
            text(top, lv_tier(lv).upper() + " LIFT", T.CAPTION, T.TEXT_DIM).grid(
                row=0, column=0, sticky="w")
            fit = Badge(top, "")
            fit.grid(row=0, column=1, sticky="e")
            self.lv_fit[lv.id] = fit
            glossary_text(card, lv.name, T.H3).grid(sticky="ew", padx=T.PAD, pady=(4, 0))
            glossary_text(card, lv.description, T.SMALL, T.TEXT_MUTED).grid(
                sticky="ew", padx=T.PAD, pady=(4, 0))
            chips = ctk.CTkFrame(card, fg_color="transparent")
            chips.grid(sticky="w", padx=T.PAD, pady=(10, 0))
            Chip(chips, T.money(lv.cost_usd)).pack(side="left")
            Chip(chips, f"{lv.reliability:.0%} reliable",
                 "success" if lv.reliability >= 0.95 else "warning").pack(side="left", padx=6)
            caps = "   ".join(f"{k} {v / 1000:g} t" for k, v in lv.payload_capacity_kg.items())
            glossary_text(card, caps, (11, "bold"), T.TEXT_DIM).grid(
                sticky="ew", padx=T.PAD, pady=(8, 14))
            card.finalize()
            self.lv_cards[lv.id] = card
            cards.append(card)
        self._place(grid, cards, 3)

    def _pick_lv(self, lv) -> None:
        m = self.mission
        if self._shop_locked(lv.id, m.launch_vehicle is not None and m.launch_vehicle.id == lv.id):
            return
        self.mission.set_launch_vehicle(lv)
        # A new rocket may not reach the current destination: clear it
        dest = self.mission.destination
        if dest and dest.id not in {p.id for p in reachable_planets(lv)}:
            self.mission.set_destination(None)
            self.app.toast(f"{dest.name} is out of range for the {lv.name} — "
                           "pick a new destination.")
        self.app.on_design_changed()

    def _refresh_launchers(self) -> None:
        m = self.mission
        for lv_id, card in self.lv_cards.items():
            lv = self.app.launch_vehicles[lv_id]
            selected = m.launch_vehicle is not None and m.launch_vehicle.id == lv_id
            card.set_selected(selected)
            badge = self.lv_fit[lv_id]
            locked = not selected and not is_unlocked(self.app.profile, lv_id)
            card.set_locked(locked)
            if locked:
                badge.set(f"🔒 {price_of(lv_id)} XP", "violet")
                continue
            if m.orbit is None:
                badge.set("Pick orbit", "neutral")
                continue
            ok, _reason = lv.can_launch(m.spacecraft.total_mass_kg, m.orbit)
            cap = lv.capacity_for(m.orbit)
            if ok:
                badge.set(f"Lifts {cap / 1000:g} t", "success")
            elif cap is None:
                badge.set(f"No {orbit_capacity_class(m.orbit)}", "danger")
            else:
                badge.set("Too heavy", "danger")

    # ------------------------------------------------------------------
    # 3. Destination
    # ------------------------------------------------------------------
    def _build_destinations(self) -> None:
        grid = self._section(3, "Destination", "Your launch vehicle decides which "
                             "worlds are in range. Farther worlds come with bigger "
                             f"budgets — from {T.money(MIN_BUDGET_USD)} for the Moon "
                             f"to {T.money(MAX_BUDGET_USD)} for Neptune.")
        cards = []
        for pid, planet in PLANETS.items():
            card = SelectableCard(grid, command=lambda p=planet: self._pick_destination(p))
            card.grid_columnconfigure(0, weight=1)
            image = assets.planet_image(pid, 64)
            art = ctk.CTkLabel(card, text="" if image else "●", image=image,
                               height=72, text_color=planet.color,
                               font=T.font(48, "bold"))
            art.grid(pady=(T.PAD, 4))
            ctk.CTkLabel(card, text=planet.name, font=T.font(*T.H3),
                         text_color=T.TEXT).grid()
            ctk.CTkLabel(card, text=short_distance(planet.distance_label),
                         font=T.font(11), text_color=T.TEXT_DIM).grid()
            ctk.CTkLabel(card, text=f"Budget {T.money(budget_for(planet))}",
                         font=T.font(12, "bold"), text_color=T.SUCCESS).grid(pady=(2, 0))
            badge = Badge(card, "")
            badge.grid(pady=(8, 14))
            self.planet_badges[pid] = badge
            card.finalize()
            self.planet_cards[pid] = card
            cards.append(card)
        self._place(grid, cards, 4)

        # Suitability of the chosen orbit for the chosen destination
        self.fit_card = Card(self.body)
        self.fit_card.grid(sticky="ew", padx=(0, T.PAD_SM), pady=(T.PAD_SM, T.PAD))
        self.fit_card.grid_columnconfigure(0, weight=1)
        eyebrow(self.fit_card, "Orbit suitability").grid(sticky="w", padx=T.PAD,
                                                         pady=(T.PAD, 8))
        self.fit_meter = Meter(self.fit_card, "Orbit vs destination")
        self.fit_meter.grid(sticky="ew", padx=T.PAD)
        self.fit_reasons = ctk.CTkFrame(self.fit_card, fg_color="transparent")
        self.fit_reasons.grid(sticky="ew", padx=T.PAD, pady=(10, T.PAD))
        self.fit_reasons.grid_columnconfigure(0, weight=1)

    def _pick_destination(self, planet) -> None:
        lv = self.mission.launch_vehicle
        if lv is None:
            self.app.toast("Choose a launch vehicle first — it decides which "
                           "destinations you can reach.")
            return
        if planet.id not in {p.id for p in reachable_planets(lv)}:
            self.app.toast(f"{planet.name} is out of range for the {lv.name}.")
            return
        self.mission.set_destination(planet)
        self.app.on_design_changed()

    def _refresh_destinations(self) -> None:
        m = self.mission
        reachable = {p.id for p in reachable_planets(m.launch_vehicle)}
        for pid, card in self.planet_cards.items():
            card.set_selected(m.destination is not None and m.destination.id == pid)
            if m.launch_vehicle is None:
                self.planet_badges[pid].set("Need rocket", "neutral")
            elif pid in reachable:
                self.planet_badges[pid].set("In range", "success")
            else:
                self.planet_badges[pid].set("Out of range", "danger")

        for child in self.fit_reasons.winfo_children():
            child.destroy()
        if m.destination is None or m.orbit is None:
            self.fit_card.grid_remove()
            return
        self.fit_card.grid()
        score, reasons = score_orbit_for(m.orbit, m.destination)
        tone = T.score_tone(score)
        self.fit_meter.set(score / 100, f"{score:.0f} / 100", tone,
                           f"{m.orbit.name} for a mission to {m.destination.name}")
        for reason in reasons:
            good = any(w in reason for w in ("matches", "excellent"))
            row = StatusRow(self.fit_reasons, reason)
            row.set("success" if good else "warning")
            row.grid(sticky="ew", pady=1)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        m = self.mission
        allowed = m.scenario.allowed_orbits
        for oid, card in self.orbit_cards.items():
            selected = m.orbit is not None and m.orbit.id == oid
            card.set_selected(selected)
            ok = not allowed or oid in allowed
            shop_locked = not selected and not is_unlocked(self.app.profile, oid)
            card.set_locked(not ok or shop_locked)
            if shop_locked:
                self.orbit_badges[oid].set(f"🔒 {price_of(oid)} XP", "violet")
            else:
                self.orbit_badges[oid].set("Allowed" if ok else "Not in scenario",
                                           "success" if ok else "neutral")
        if m.orbit is not None and m.orbit.id not in self._gmat_cache:
            self._fetch_gmat(m.orbit)      # e.g. after loading a saved design
        self._refresh_orbit_detail()
        self._refresh_launchers()
        self._refresh_destinations()
