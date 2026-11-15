"""Results screen: the mission report, shown after the launch finishes.

The Launch screen runs the simulation and flies the 3D mission; when the
flight ends it stores the outcome on the app (`app.last_flight`) and moves
here automatically. This screen only renders that stored outcome.
"""

from __future__ import annotations

import customtkinter as ctk

from src.game.scoring import ScoreEngine
from src.game.simulation import EVENT_DECK
from src.ui import theme as T
from src.ui.screens.base import Screen
from src.game.simulation import CHOICE_EVENTS
from src.ui.widgets import (Badge, Card, Chip, MedalBadge, Meter, ScoreRing, ScrollFrame,
                            StatTile, StatusRow, eyebrow, ghost_button, glossary_text,
                            primary_button, text)

EVENT_INFO = {ev.name: ev.description for ev in EVENT_DECK + CHOICE_EVENTS}
MEDAL_TEXT = {"gold": "Gold medal", "silver": "Silver medal", "bronze": "Bronze medal"}
MEDAL_SHORT = {"gold": "🥇 Gold", "silver": "🥈 Silver", "bronze": "🥉 Bronze"}
WEIGHTS = {"science": ScoreEngine.SCIENCE_WEIGHT,
           "objectives": ScoreEngine.OBJECTIVE_WEIGHT,
           "efficiency": ScoreEngine.EFFICIENCY_WEIGHT,
           "reliability": ScoreEngine.RELIABILITY_WEIGHT,
           "innovation": ScoreEngine.INNOVATION_WEIGHT}


class ResultsScreen(Screen):
    key = "results"
    title = "Mission Results"
    subtitle = "How your mission performed — and what to try next."
    show_telemetry = False

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.page_header().grid(row=0, column=0, sticky="ew", pady=(0, T.PAD))
        self.body = ScrollFrame(self)
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.grid_columnconfigure(0, weight=1)
        self.results = ctk.CTkFrame(self.body, fg_color="transparent")
        self.results.grid(sticky="ew", padx=(0, T.PAD_SM))
        self.results.grid_columnconfigure(0, weight=1)
        self._shown = None          # which flight is currently rendered

    def refresh(self) -> None:
        flight = self.app.last_flight
        if flight is None or flight is self._shown:
            return
        self._shown = flight
        self._flight = flight
        for child in self.results.winfo_children():
            child.destroy()
        self._render(flight["result"], flight["score"], flight["tips"], flight["report"])
        self.body.scroll_to_top()
        self._celebrate(flight)

    def _celebrate(self, flight: dict) -> None:
        """Milestone toasts for the medal, XP and any rank-up."""
        award, medal = flight.get("award"), flight.get("medal")
        if medal:
            self.app.toast(f"{MEDAL_TEXT[medal]} earned!", "warning", "🏅", 2400)
        if award:
            self.app.toast(f"+{award['xp_gained']} XP", "accent", "⭐", 1800)
            if award["ranked_up"]:
                self.app.toast(f"Rank up! You're now a {award['rank_after']['name']}",
                               "success", "🎖", 3000)

    def _render(self, r, score: float, tips: list[str], report: str) -> None:
        parent = self.results

        # Outcome banner: score ring + headline + key numbers
        top = Card(parent)
        top.grid(sticky="ew", pady=(0, T.PAD))
        top.grid_columnconfigure(1, weight=1)
        medal = self._flight.get("medal")
        if medal:                                   # medal pops in at the right
            badge = MedalBadge(top, medal, size=140, bg=T.CARD)
            badge.grid(row=0, column=2, rowspan=2, padx=(0, T.PAD_LG), pady=T.PAD_LG)
            self.after(450, badge.pop)
        ring = ScoreRing(top, size=176, bg=T.CARD)
        ring.grid(row=0, column=0, rowspan=2, padx=T.PAD_LG, pady=T.PAD_LG)
        ring.show(score)

        if not r.launch_success:
            outcome, tone, headline = "Launch failure", "danger", "The rocket didn't make it."
        elif r.success:
            outcome, tone, headline = "Success", "success", "Mission accomplished."
        else:
            outcome, tone, headline = "Partial success", "warning", "The mission flew — with gaps."
        head = ctk.CTkFrame(top, fg_color="transparent")
        head.grid(row=0, column=1, sticky="sew", padx=(0, T.PAD_LG), pady=(T.PAD_LG, 0))
        Badge(head, outcome, tone).pack(anchor="w")
        text(head, headline, T.H1).pack(anchor="w", pady=(6, 0))
        if score >= 90:
            text(head, "★  SUCCESS!  Outstanding mission design, Commander.", T.H3,
                 T.SUCCESS).pack(anchor="w", pady=(4, 0))
        elif r.failure_reason:
            text(head, r.failure_reason, T.BODY, T.TEXT_MUTED).pack(anchor="w", pady=(4, 0))
        self._xp_strip(head)

        tiles = ctk.CTkFrame(top, fg_color="transparent")
        tiles.grid(row=1, column=1, sticky="new", padx=(0, T.PAD_LG), pady=(T.PAD, T.PAD_LG))
        tiles.grid_columnconfigure(tuple(range(5)), weight=1, uniform="t")
        backlog_tone = "danger" if r.data_backlog_gb > 1000 else (
            "warning" if r.data_backlog_gb > 500 else "neutral")
        for i, (caption, value, t) in enumerate([
                ("Science", f"{r.science_return:.0f}", "violet"),
                ("Months operated", f"{r.months_operated:.0f}", "neutral"),
                ("Data generated", f"{r.data_generated_gb:,.0f} GB", "neutral"),
                ("Downlinked", f"{r.data_downlinked_gb:,.0f} GB", "neutral"),
                ("Backlog", f"{r.data_backlog_gb:,.0f} GB", backlog_tone)]):
            StatTile(tiles, caption, value, t).grid(
                row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))

        self._decisions(parent)
        self._leaderboard(parent)

        # Breakdown + objectives side by side
        mid = ctk.CTkFrame(parent, fg_color="transparent")
        mid.grid(sticky="ew", pady=(0, T.PAD))
        mid.grid_columnconfigure((0, 1), weight=1, uniform="m")
        self._breakdown(mid, r).grid(row=0, column=0, sticky="nsew", padx=(0, T.PAD_SM))
        self._objectives(mid, r).grid(row=0, column=1, sticky="nsew", padx=(T.PAD_SM, 0))

        # Engineering feedback
        card = Card(parent)
        card.grid(sticky="ew", pady=(0, T.PAD))
        card.grid_columnconfigure(0, weight=1)
        eyebrow(card, "Engineering feedback", T.VIOLET_TEXT).grid(
            sticky="w", padx=T.PAD_LG, pady=(T.PAD, 8))
        for tip in tips:
            row = ctk.CTkFrame(card, fg_color=T.VIOLET_BG, corner_radius=8)
            row.grid(sticky="ew", padx=T.PAD_LG, pady=(0, 8))
            row.grid_columnconfigure(1, weight=1)
            text(row, "→", (14, "bold"), T.VIOLET_TEXT).grid(row=0, column=0, padx=(12, 8),
                                                        pady=10, sticky="n")
            glossary_text(row, tip, T.BODY).grid(row=0, column=1, sticky="ew",
                                                 padx=(0, 12), pady=10)
        ctk.CTkFrame(card, fg_color="transparent", height=T.PAD_SM).grid()

        # Full text report, for the curious (and for copying)
        log = Card(parent)
        log.grid(sticky="ew", pady=(0, T.PAD))
        log.grid_columnconfigure(0, weight=1)
        eyebrow(log, "Mission log", T.TEXT_DIM).grid(sticky="w", padx=T.PAD_LG,
                                                     pady=(T.PAD, 8))
        box = ctk.CTkTextbox(log, height=220, font=T.font(12, mono=True),
                             fg_color=T.BG, text_color=T.TEXT_MUTED, corner_radius=8,
                             border_width=0, wrap="word")
        box.grid(sticky="ew", padx=T.PAD_LG, pady=(0, T.PAD_LG))
        box.insert("end", report + f"\n\nFINAL SCORE: {score} / 100\n")
        box.configure(state="disabled")

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(sticky="ew", pady=(0, T.PAD_LG))
        primary_button(actions, "🚀  Fly again", lambda: self.app.show_screen("sim"),
                       width=180).pack(side="left")
        ghost_button(actions, "🛒  Spend XP in the shop", self.app.open_shop,
                     width=220).pack(side="left", padx=(T.PAD_SM, 0))
        ghost_button(actions, "Tweak the design", lambda: self.app.show_screen("bus"),
                     width=180).pack(side="left", padx=T.PAD_SM)
        ghost_button(actions, "Start a new mission", self.app.restart,
                     width=200).pack(side="left")

    def _breakdown(self, parent, r) -> Card:
        card = Card(parent)
        card.grid_columnconfigure(0, weight=1)
        eyebrow(card, "Score breakdown").grid(sticky="w", padx=T.PAD_LG, pady=(T.PAD, 10))
        if not r.score_breakdown:
            text(card, "Launch failed — only participation credit was awarded.",
                 T.SMALL, T.TEXT_MUTED).grid(sticky="w", padx=T.PAD_LG, pady=(0, T.PAD))
            return card
        for key, value in r.score_breakdown.items():
            meter = Meter(card, f"{key.capitalize()}  ·  {WEIGHTS.get(key, 0):.0%} weight")
            meter.grid(sticky="ew", padx=T.PAD_LG, pady=(0, 12))
            meter.set(value / 100, f"{value:.0f}", T.score_tone(value))
        return card

    def _objectives(self, parent, r) -> Card:
        card = Card(parent)
        card.grid_columnconfigure(0, weight=1)
        eyebrow(card, "Objectives").grid(sticky="w", padx=T.PAD_LG, pady=(T.PAD, 8))
        rows = ctk.CTkFrame(card, fg_color="transparent")
        rows.grid(sticky="ew", padx=T.PAD_LG)
        rows.grid_columnconfigure(0, weight=1)
        if not r.objectives_met and not r.objectives_failed:
            text(rows, "No scored objectives in this scenario.", T.SMALL,
                 T.TEXT_DIM).grid(sticky="w")
        for obj in r.objectives_met:
            row = StatusRow(rows, obj.replace("_", " ").capitalize())
            row.set("success", "pass")
            row.grid(sticky="ew", pady=1)
        for obj in r.objectives_failed:
            row = StatusRow(rows, obj.replace("_", " ").capitalize())
            row.set("danger", "fail")
            row.grid(sticky="ew", pady=1)

        eyebrow(card, "Anomalies", T.WARNING).grid(sticky="w", padx=T.PAD_LG,
                                                   pady=(T.PAD, 8))
        events = ctk.CTkFrame(card, fg_color="transparent")
        events.grid(sticky="ew", padx=T.PAD_LG, pady=(0, T.PAD))
        events.grid_columnconfigure(0, weight=1)
        if not r.events_triggered:
            row = StatusRow(events, "None — a clean mission.")
            row.set("success")
            row.grid(sticky="ew")
        for name in r.events_triggered:
            good = name == "Bonus science window"
            row = StatusRow(events, name)
            row.set("success" if good else "warning")
            row.grid(sticky="ew", pady=(2, 0))
            info = EVENT_INFO.get(name)
            if info:
                glossary_text(events, info, (11, "normal"), T.TEXT_DIM).grid(
                    sticky="ew", padx=(22, 0))
        return card

    # ------------------------------------------------------------------
    # Gamification extras
    # ------------------------------------------------------------------
    def _xp_strip(self, parent) -> None:
        """'+180 XP' badge, medal name, and progress to the next rank."""
        award = self._flight.get("award")
        if not award:
            return
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(anchor="w", fill="x", pady=(10, 0))
        Badge(row, f"+{award['xp_gained']} XP", "violet").pack(side="left")
        medal = self._flight.get("medal")
        if medal:
            Badge(row, MEDAL_TEXT[medal], "warning").pack(side="left", padx=(6, 0))
        rank = award["rank_after"]
        label = (f"LV {rank['level']} {rank['name']}" + (
            f"  ·  {rank['next_floor'] - self.app.profile.xp:,} XP to {rank['next_name']}"
            if rank["next_floor"] else "  ·  max rank"))
        text(row, label, (12, "bold"), T.TEXT_MUTED).pack(side="left", padx=(10, 0))
        bar = ctk.CTkProgressBar(parent, height=8, corner_radius=4, fg_color=T.RAISED,
                                 progress_color=T.VIOLET)
        bar.pack(anchor="w", fill="x", pady=(8, 0))
        bar.set(rank["progress"])

    def _decisions(self, parent) -> None:
        """Recap of the event-card choices made during the flight."""
        decisions = self._flight.get("decisions") or []
        if not decisions:
            return
        card = Card(parent)
        card.grid(sticky="ew", pady=(0, T.PAD))
        card.grid_columnconfigure(1, weight=1)
        eyebrow(card, "Your in-flight calls", T.ACCENT).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=T.PAD_LG, pady=(T.PAD, 8))
        for i, (icon, title, label, chips) in enumerate(decisions, start=1):
            text(card, icon, (18, "normal")).grid(row=i, column=0, padx=(T.PAD_LG, 10),
                                                  pady=(0, 8), sticky="n")
            body = ctk.CTkFrame(card, fg_color="transparent")
            body.grid(row=i, column=1, sticky="ew", pady=(0, 8))
            text(body, title, (12, "bold"), T.TEXT_MUTED).pack(anchor="w")
            text(body, f"→ {label}", T.H3).pack(anchor="w")
            chip_row = ctk.CTkFrame(card, fg_color="transparent")
            chip_row.grid(row=i, column=2, sticky="e", padx=(8, T.PAD_LG), pady=(0, 8))
            for chip_text, tone in chips:
                Chip(chip_row, chip_text, tone).pack(side="left", padx=(6, 0))

    def _leaderboard(self, parent) -> None:
        """Every flight this pilot has flown, ranked by score, with lifetime
        totals on top. Grows by one row per simulation."""
        from src.game.profile import rank_for

        profile = self.app.profile
        history = list(profile.history)
        card = Card(parent)
        card.grid(sticky="ew", pady=(0, T.PAD))
        card.grid_columnconfigure(0, weight=1)
        eyebrow(card, "Pilot leaderboard — every flight you've flown", T.ACCENT).grid(
            sticky="w", padx=T.PAD_LG, pady=(T.PAD, 10))

        # Lifetime totals
        rank = rank_for(profile.xp)
        medals = profile.medals
        totals = ctk.CTkFrame(card, fg_color="transparent")
        totals.grid(sticky="ew", padx=T.PAD_LG, pady=(0, T.PAD))
        totals.grid_columnconfigure(tuple(range(6)), weight=1, uniform="tot")
        for i, (caption, value, tone) in enumerate([
                ("Total XP earned", f"{profile.xp:,}", "violet"),
                ("XP to spend", f"{profile.balance:,}", "accent"),
                ("Pilot rank", f"LV {rank['level']} {rank['name']}", "neutral"),
                ("Flights", f"{profile.flights}", "neutral"),
                ("Medals", f"🥇{medals.get('gold', 0)} 🥈{medals.get('silver', 0)} "
                           f"🥉{medals.get('bronze', 0)}", "neutral"),
                ("Best score", f"{profile.best_score:.1f}", "success")]):
            StatTile(totals, caption, value, tone).grid(row=0, column=i, sticky="ew",
                                                         padx=(0 if i == 0 else 6, 0))

        if not history:
            text(card, "No flights logged yet.", T.SMALL, T.TEXT_DIM).grid(
                sticky="w", padx=T.PAD_LG, pady=(0, T.PAD))
            return

        table = ctk.CTkFrame(card, fg_color="transparent")
        table.grid(sticky="ew", padx=T.PAD_LG, pady=(0, T.PAD))
        columns = [("#", 0), ("Flight", 0), ("Mission", 3), ("Destination", 2), ("Score", 1),
                   ("Objectives", 1), ("XP gained", 1), ("Award", 2), ("Pilot rank", 2)]
        for col, (_title, weight) in enumerate(columns):
            table.grid_columnconfigure(col, weight=weight)
        for col, (title, _w) in enumerate(columns):
            text(table, title.upper(), (10, "bold"), T.TEXT_DIM).grid(
                row=0, column=col, sticky="w", padx=(0, 12), pady=(0, 6))

        latest = history[-1]["flight"]
        ranked = sorted(history, key=lambda e: (-e["score"], -e["flight"]))
        for row, entry in enumerate(ranked, start=1):
            current = entry["flight"] == latest
            bg = T.ACCENT_BG if current else "transparent"
            if not entry.get("launch_ok", True):
                award = "💥 Launch failed"
            else:
                award = MEDAL_SHORT.get(entry.get("medal"), "—")
            score_tone = T.TONES[T.score_tone(entry["score"])][0]
            cells = [
                (f"{row}", (12, "bold"), (T.GOLD, T.SILVER, T.BRONZE)[row - 1] if row <= 3
                 else T.TEXT_MUTED),
                (f"#{entry['flight']}" + ("  NEW" if current else ""), (12, "bold"),
                 T.ACCENT if current else T.TEXT_MUTED),
                (entry["mission"], T.SMALL, T.TEXT),
                (entry.get("destination", "—"), T.SMALL, T.TEXT_MUTED),
                (f"{entry['score']:.1f}", (12, "bold"), score_tone),
                (entry.get("objectives", "—"), T.SMALL, T.TEXT_MUTED),
                (f"+{entry['xp']}", (12, "bold"), T.VIOLET_TEXT),
                (award, T.SMALL, T.TEXT),
                (f"LV {entry.get('level', 1)} {entry.get('rank', '')}", T.SMALL, T.TEXT_MUTED),
            ]
            for col, (value, style, colour) in enumerate(cells):
                text(table, value, style, colour, fg_color=bg, corner_radius=0).grid(
                    row=row, column=col, sticky="ew", padx=(0, 0), pady=1, ipadx=6)
        text(card, f"{len(history)} flight{'s' if len(history) != 1 else ''} logged · "
                   "ranked by score · your newest flight is highlighted",
             (11, "normal"), T.TEXT_DIM).grid(sticky="w", padx=T.PAD_LG, pady=(0, T.PAD))
