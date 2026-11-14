"""Launch screen: run the simulation and present the mission report.

Game logic is the original: validate (blocked unless sandbox), simulate,
score, generate the report, append to the leaderboard. The simulation
runs on a worker thread; the UI plays a short phase sequence meanwhile
and polls for the result from the main thread.
"""

from __future__ import annotations

import threading

import customtkinter as ctk

from src.game.save_load import save_result
from src.game.scoring import ScoreEngine
from src.game.simulation import EVENT_DECK
from src.ui import theme as T
from src.ui.screens.base import Screen
from src.ui.telemetry import readiness
from src.ui.widgets import (Badge, Card, Meter, ScoreRing, ScrollFrame, StatTile,
                            StatusRow, eyebrow, ghost_button, glossary_text,
                            primary_button, text)

PHASES = ["Launch", "Cruise", "Operations", "Scoring"]
PHASE_MS = 600
EVENT_INFO = {ev.name: ev.description for ev in EVENT_DECK}
WEIGHTS = {"science": ScoreEngine.SCIENCE_WEIGHT,
           "objectives": ScoreEngine.OBJECTIVE_WEIGHT,
           "efficiency": ScoreEngine.EFFICIENCY_WEIGHT,
           "reliability": ScoreEngine.RELIABILITY_WEIGHT,
           "innovation": ScoreEngine.INNOVATION_WEIGHT}


class LaunchScreen(Screen):
    key = "sim"
    title = "Launch"
    subtitle = "Commit the design, light the engines and see how your mission performs."
    show_telemetry = False

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.page_header().grid(row=0, column=0, sticky="ew", pady=(0, T.PAD))
        self.body = ScrollFrame(self)
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.grid_columnconfigure(0, weight=1)
        self._running = False
        self._has_results = False   # a finished flight is shown below
        self._build_control()
        self.results = ctk.CTkFrame(self.body, fg_color="transparent")
        self.results.grid(sticky="ew", padx=(0, T.PAD_SM))
        self.results.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------------
    # Launch control panel
    # ------------------------------------------------------------------
    def _build_control(self) -> None:
        card = Card(self.body)
        card.grid(sticky="ew", padx=(0, T.PAD_SM), pady=(0, T.PAD))
        card.grid_columnconfigure(0, weight=1)

        left = ctk.CTkFrame(card, fg_color="transparent")
        left.grid(row=0, column=0, sticky="ew", padx=T.PAD_LG, pady=T.PAD_LG)
        left.grid_columnconfigure(0, weight=1)
        eyebrow(left, "Launch control").grid(sticky="w")
        self.ready_text = text(left, "", T.H1)
        self.ready_text.grid(sticky="w", pady=(4, 2))
        self.brief = glossary_text(left, "", T.BODY, T.TEXT_MUTED)
        self.brief.grid(sticky="ew")

        right = ctk.CTkFrame(card, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e", padx=T.PAD_LG)
        self.ready_badge = Badge(right, "—")
        self.ready_badge.pack(anchor="e", pady=(0, 10))
        self.launch_btn = primary_button(right, "🚀  LAUNCH SIMULATION", self._launch,
                                         width=260, height=54, font=T.font(15, "bold"))
        self.launch_btn.pack()

        # Phase tracker, shown while the simulation runs
        self.tracker = ctk.CTkFrame(card, fg_color="transparent")
        self.tracker.grid(row=1, column=0, columnspan=2, sticky="ew",
                          padx=T.PAD_LG, pady=(0, T.PAD_LG))
        self.tracker.grid_columnconfigure(tuple(range(len(PHASES))), weight=1, uniform="p")
        self.phase_labels = []
        for i, phase in enumerate(PHASES):
            label = text(self.tracker, f"○  {phase}", (12, "bold"), T.TEXT_DIM)
            label.grid(row=0, column=i, sticky="w")
            self.phase_labels.append(label)
        self.phase_bar = ctk.CTkProgressBar(self.tracker, height=6, corner_radius=3,
                                            fg_color=T.RAISED, progress_color=T.ACCENT)
        self.phase_bar.grid(row=1, column=0, columnspan=len(PHASES), sticky="ew",
                            pady=(8, 0))
        self.tracker.grid_remove()

    def refresh(self) -> None:
        if self._running:
            return
        m = self.mission
        label, tone = readiness(m)
        self.ready_badge.set(label, tone)
        sandbox = m.scenario.sandbox_mode
        again = self._has_results
        self.ready_text.configure(text={
            "success": "Ready to fly again." if again else "Ready for launch.",
            "warning": "Ready to fly again, with cautions." if again
                       else "Ready, with cautions.",
            "danger": "Sandbox: fly it anyway?" if sandbox
                      else "Design changed — fix issues to fly again." if again
                      else "Launch blocked."}[tone])
        lv = m.launch_vehicle
        self.brief.set_text((
            f"{lv.name} · {lv.reliability:.0%} launch reliability · " if lv else
            "No launch vehicle · ")
            + f"{m.scenario.mission_months}-month mission · Objective: {m.objective}")

    # ------------------------------------------------------------------
    # Running the simulation
    # ------------------------------------------------------------------
    def _launch(self) -> None:
        if self._running:
            return
        self._running = True
        self.launch_btn.configure(state="disabled", text="Mission in progress…")
        self.app.set_navigation_enabled(False)
        for child in self.results.winfo_children():
            child.destroy()
        self.tracker.grid()
        self.phase_bar.set(0)

        box: dict = {}
        threading.Thread(target=self._simulate, args=(box,), daemon=True).start()
        self._advance_phase(0, box)

    def _simulate(self, box: dict) -> None:
        """Worker thread. Touches only the game model, never Tk widgets."""
        m = self.mission
        # Each launch is a fresh run: clear the previous run's elapsed time
        # and data volumes, otherwise "time limit reached" from the last
        # run would block every re-launch.
        m.reset_run_results()
        try:
            errors, _ = m.validate_design()
            if errors and not m.scenario.sandbox_mode:
                box["out"] = ("blocked", errors, None, -1, "")
                return
            result = m.simulate()
            engine = ScoreEngine()
            score = engine.score(result)
            report = engine.generate_report(result)
            try:
                save_result(result, score)
            except Exception:
                pass
            box["out"] = ("done", engine._feedback(result), result, score, report)
        except Exception as exc:
            box["out"] = ("crashed", [str(exc)], None, 0, "")

    def _advance_phase(self, index: int, box: dict) -> None:
        if not self.winfo_exists():
            return
        blocked = box.get("out", ("",))[0] in ("blocked", "crashed")
        if index < len(PHASES) and not blocked:
            for i, label in enumerate(self.phase_labels):
                if i < index:
                    label.configure(text=f"✓  {PHASES[i]}", text_color=T.SUCCESS)
                elif i == index:
                    label.configure(text=f"●  {PHASES[i]}", text_color=T.ACCENT)
            self.phase_bar.set((index + 1) / len(PHASES))
            self.after(PHASE_MS, self._advance_phase, index + 1, box)
            return
        if "out" not in box:                    # simulation still running
            self.after(100, self._advance_phase, index, box)
            return
        self._finish(*box["out"])

    def _finish(self, status, notes, result, score, report) -> None:
        self._running = False
        self.app.set_navigation_enabled(True)
        self.tracker.grid_remove()
        for label, phase in zip(self.phase_labels, PHASES):
            label.configure(text=f"○  {phase}", text_color=T.TEXT_DIM)
        self.launch_btn.configure(state="normal", text="🚀  LAUNCH AGAIN")
        self.app.on_design_changed()       # time meter etc. reflect the run
        self._has_results = status == "done"
        self.refresh()                     # header reflects the new state
        if status == "done":
            self._show_results(result, score, notes, report)
        else:
            self._show_blocked(status, notes)
        self.body.scroll_to_top()

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------
    def _show_blocked(self, status: str, problems: list[str]) -> None:
        card = Card(self.results, border_color=T.DANGER)
        card.grid(sticky="ew", pady=(0, T.PAD))
        card.grid_columnconfigure(0, weight=1)
        title = ("Simulation blocked" if status == "blocked" else "Simulation crashed")
        Badge(card, title, "danger").grid(sticky="w", padx=T.PAD_LG, pady=(T.PAD_LG, 6))
        text(card, "Mission control won't clear this design for launch."
             if status == "blocked" else "Something went wrong while simulating.",
             T.H2).grid(sticky="w", padx=T.PAD_LG)
        rows = ctk.CTkFrame(card, fg_color="transparent")
        rows.grid(sticky="ew", padx=T.PAD_LG, pady=(10, 0))
        rows.grid_columnconfigure(0, weight=1)
        for problem in problems:
            row = StatusRow(rows, problem)
            row.set("danger")
            row.grid(sticky="ew", pady=1)
        ghost_button(card, "Open Mission Review", lambda: self.app.show_screen("dash"),
                     width=220).grid(sticky="w", padx=T.PAD_LG, pady=T.PAD_LG)

    def _show_results(self, r, score: float, tips: list[str], report: str) -> None:
        parent = self.results

        # Outcome banner: score ring + headline + key numbers
        top = Card(parent)
        top.grid(sticky="ew", pady=(0, T.PAD))
        top.grid_columnconfigure(1, weight=1)
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
        eyebrow(card, "Engineering feedback", T.VIOLET).grid(
            sticky="w", padx=T.PAD_LG, pady=(T.PAD, 8))
        for tip in tips:
            row = ctk.CTkFrame(card, fg_color=T.VIOLET_BG, corner_radius=8)
            row.grid(sticky="ew", padx=T.PAD_LG, pady=(0, 8))
            row.grid_columnconfigure(1, weight=1)
            text(row, "→", (14, "bold"), T.VIOLET).grid(row=0, column=0, padx=(12, 8),
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
        primary_button(actions, "Tweak the design", lambda: self.app.show_screen("bus"),
                       width=200).pack(side="left")
        ghost_button(actions, "Start a new mission", self.app.restart,
                     width=200).pack(side="left", padx=T.PAD_SM)

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
