"""Launch screen: run the simulation and fly it in 3D.

Game logic is the original: validate (blocked unless sandbox), simulate,
score, generate the report, append to the leaderboard — with two
additions for gameplay:

* Event cards. Twice per flight (once in cruise, once in operations) the
  flight pauses and the player makes a tactical choice. The simulation is
  run once up front with a random seed (to know whether the launch
  succeeds, so the 3D rocket can explode on cue), then again at the end
  with the *same* seed plus the chosen effects — so the launch outcome is
  identical and only the choices change what follows.
* Progression. Milestone toasts fire as the flight progresses; at the end
  the player earns XP, possibly a rank-up and a medal (src/game/profile.py).

A blocked design never flies, so its problems are listed right here.
"""

from __future__ import annotations

import random
import threading
import time

import customtkinter as ctk

from src.game.flight_events import EventCard, merge_effects, pick_events
from src.game.profile import award_flight, medal_for
from src.game.save_load import save_result
from src.game.scoring import ScoreEngine
from src.ui import theme as T
from src.ui.screens.base import Screen
from src.ui.screens.launch_viewport import DEFAULT_PLAN, FlightPlan, MissionViewport
from src.ui.telemetry import readiness
from src.ui.widgets import (Badge, Card, Chip, ScrollFrame, SelectableCard, StatusRow,
                            eyebrow, ghost_button, glossary_text, primary_button, text)

# One shared timeline per flight (FlightPlan, from the 3D viewport): its
# phase names and lengths follow the mission type and length, and every
# time below is a fraction of that same plan, so they always line up.
RESULTS_DELAY_MS = 1600  # let the player see the landing before moving on


def event_times(plan: FlightPlan) -> tuple[float, float]:
    """Mid-cruise, and mid-way through the orbits."""
    return plan.at(1, 0.5), plan.at(2, 0.5)


def failure_time(plan: FlightPlan) -> float:
    """Matches the 3D explosion (half-way through Launch)."""
    return plan.at(0, 0.5)


def milestones_for(plan: FlightPlan) -> list[tuple]:
    """(flight progress, message, tone, icon, only if the launch succeeded)"""
    n = plan.loops
    final = (n - 1) / n
    if plan.kind == "l1":
        arrive = ("Arrived at L1 — halo orbit locked in!", "☀️")
        mid = "Solar wind data streaming home"
        lap = f"Final halo loop ({n} of {n})"
        leave = "Leaving L1 — heading home"
    elif plan.kind == "earth":
        arrive = ("Orbit insertion — you made it!", "🛰")
        mid = "Images streaming down to the ground station"
        lap = f"Final orbit ({n} of {n})"
        leave = "Deorbit burn — coming home"
    else:
        arrive = ("Orbit insertion — you made it!", "🪐")
        mid = "Science data streaming home"
        lap = f"Final lap ({n} of {n})"
        leave = "Leaving orbit — heading home"
    return [
        (0.005, "Lift-off!", "accent", "🚀", False),
        (plan.at(0, 0.6), "Booster separation — clean!", "accent", "✓", True),
        (plan.at(2, 0.0), arrive[0], "success", arrive[1], True),
        (plan.at(2, min(0.34, final / 2)), mid, "success", "📡", True),
        (plan.at(2, final), lap, "success", "↻", True),
        (plan.at(3, 0.02), leave, "accent", "↩", True),
        (0.995, "Touchdown — welcome home!", "success", "🌍", True),
    ]


# Defaults for an interplanetary flight of the reference length
PHASES = DEFAULT_PLAN.names
EVENT_AT = event_times(DEFAULT_PLAN)
FAILURE_AT = failure_time(DEFAULT_PLAN)
MILESTONES = milestones_for(DEFAULT_PLAN)


class LaunchScreen(Screen):
    key = "sim"
    title = "Launch"
    subtitle = ("Commit the design, light the engines and watch the mission fly. "
                "Your results come next.")
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
        self._flight: dict = {}
        self._prompt = None
        self.plan = DEFAULT_PLAN
        self._build_control()
        # Central 3D viewport: destination planet + Tharun's Rocket + minimap
        self.viewport = MissionViewport(self.body)
        self.viewport.grid(sticky="ew", padx=(0, T.PAD_SM), pady=(0, T.PAD))
        # Only used when the design is blocked (that flight never happens)
        self.notice = ctk.CTkFrame(self.body, fg_color="transparent")
        self.notice.grid(sticky="ew", padx=(0, T.PAD_SM))
        self.notice.grid_columnconfigure(0, weight=1)

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
        row = ctk.CTkFrame(right, fg_color="transparent")
        row.pack(fill="x", pady=(8, 0))
        row.grid_columnconfigure((0, 1), weight=1, uniform="b")
        # Replays the full round trip on the 2D transfer map
        self.preview_btn = ghost_button(row, "▶  Preview route", self.viewport_preview,
                                        height=34, font=T.font(12, "bold"))
        self.preview_btn.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.results_btn = ghost_button(row, "View results  →",
                                        lambda: self.app.show_screen("results"),
                                        height=34, font=T.font(12, "bold"))

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

    def on_show(self) -> None:
        super().on_show()
        self.viewport.start()

    def on_hide(self) -> None:
        self.viewport.stop()        # no 3D rendering while off-screen

    def _set_plan(self, plan: FlightPlan) -> None:
        """Use this flight plan for the tracker, milestones and events."""
        self.plan = plan
        for label, name in zip(self.phase_labels, plan.names):
            label.configure(text=f"○  {name}", text_color=T.TEXT_DIM)

    def viewport_preview(self) -> None:
        if not self._running:
            self.viewport.preview_route()

    def refresh(self) -> None:
        if self._running:
            return
        m = self.mission
        self.viewport.set_mission(m)
        self._set_plan(self.viewport.plan)
        if not self._has_results:
            self.viewport.abort()   # back to standby on the launch pad
        # After a flight, offer a way back to its results next to the preview
        if self._has_results and self.app.last_flight is not None:
            self.preview_btn.grid(row=0, column=0, columnspan=1, sticky="ew", padx=(0, 4))
            self.results_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        else:
            self.results_btn.grid_remove()
            self.preview_btn.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0)
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
        self.preview_btn.configure(state="disabled")
        self.results_btn.configure(state="disabled")
        self.app.set_navigation_enabled(False)
        for child in self.notice.winfo_children():
            child.destroy()
        self.tracker.grid()
        self.phase_bar.set(0)

        box: dict = {}
        threading.Thread(target=self._simulate, args=(box,), daemon=True).start()
        self._await_result(box)

    def _await_result(self, box: dict) -> None:
        """Wait (milliseconds) for the pre-flight run: blocked/crashed ends
        here; otherwise we know the launch outcome and can start flying."""
        if not self.winfo_exists():
            return
        if "out" in box:
            self._finish(*box["out"])
            return
        if "pre" not in box:
            self.after(20, self._await_result, box)
            return
        launch_ok, seed = box["pre"]
        cards = pick_events() if launch_ok else []
        plan = self.plan
        self._flight = dict(seed=seed, launch_ok=launch_ok, elapsed=0.0, plan=plan,
                            last=time.monotonic(), paused=False, index=-1,
                            events=list(zip(event_times(plan), cards)), effects=[],
                            decisions=[], milestones=milestones_for(plan),
                            failure_at=failure_time(plan), failure_told=False)
        self.viewport.play(plan.total, launch_ok)
        self._flight_tick()

    def _simulate(self, box: dict) -> None:
        """Worker thread (pre-flight). Touches only the game model."""
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
            seed = random.randrange(1 << 30)
            box["pre"] = (m.simulate(seed=seed).launch_success, seed)
        except Exception as exc:
            box["out"] = ("crashed", [str(exc)], None, 0, "")

    def _final_run(self, box: dict, seed: int, effects: dict) -> None:
        """Worker thread (post-flight): same seed + the player's choices."""
        m = self.mission
        m.reset_run_results()
        try:
            result = m.simulate(seed=seed, modifiers=effects)
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

    def _flight_tick(self) -> None:
        """Pausable flight clock: phases, milestones, event cards, finish."""
        if not self.winfo_exists():
            return
        f = self._flight
        now = time.monotonic()
        if not f["paused"]:
            f["elapsed"] += now - f["last"]
        f["last"] = now
        plan = f["plan"]
        progress = min(1.0, f["elapsed"] / plan.total)

        index = plan.phase_at(progress)[0]
        if index != f["index"]:
            f["index"] = index
            names = plan.names
            for i, label in enumerate(self.phase_labels):
                if i < index:
                    label.configure(text=f"✓  {names[i]}", text_color=T.SUCCESS)
                elif i == index:
                    label.configure(text=f"●  {names[i]}", text_color=T.ACCENT)
        self.phase_bar.set(progress)

        while f["milestones"] and f["milestones"][0][0] <= progress:
            _at, message, tone, icon, needs_ok = f["milestones"].pop(0)
            if f["launch_ok"] or not needs_ok:
                self.app.toast(message, tone, icon, 1700)
        if not f["launch_ok"] and not f["failure_told"] and progress >= f["failure_at"]:
            f["failure_told"] = True
            self.app.toast("Launch failure — signal lost!", "danger", "💥", 2400)

        if not f["paused"] and f["events"] and f["events"][0][0] <= progress:
            _at, card = f["events"].pop(0)
            self._show_event(card)

        if progress >= 1.0 and not f["paused"]:
            box: dict = {}
            threading.Thread(target=self._final_run,
                             args=(box, f["seed"], merge_effects(f["effects"])),
                             daemon=True).start()
            self._await_final(box)
            return
        self.after(40, self._flight_tick)

    def _await_final(self, box: dict) -> None:
        if not self.winfo_exists():
            return
        if "out" not in box:
            self.after(30, self._await_final, box)
            return
        self._finish(*box["out"])

    # ------------------------------------------------------------------
    # Event cards
    # ------------------------------------------------------------------
    def _show_event(self, card: EventCard) -> None:
        f = self._flight
        f["paused"] = True
        self.viewport.pause()
        phase = self.plan.names[1 if card.phase == "cruise" else 2]
        self._prompt = EventPrompt(self.body, card, self._choose, phase)
        self._prompt.place(in_=self.viewport, relx=0.5, rely=0.5, anchor="center")
        self._prompt.lift()

    def _choose(self, card: EventCard, choice) -> None:
        f = self._flight
        f["effects"].append(choice.effects)
        f["decisions"].append((card.icon, card.title, choice.label, choice.chips))
        if self._prompt is not None:
            self._prompt.destroy()
            self._prompt = None
        self.viewport.resume()
        f["paused"] = False
        f["last"] = time.monotonic()
        self.app.toast(f"Decision locked in: {choice.label}", "accent", "⚡", 1600)

    def _finish(self, status, notes, result, score, report) -> None:
        self.tracker.grid_remove()
        self._set_plan(self.plan)
        if status != "done":                # blocked / crashed: it never flew
            self._running = False
            self.viewport.abort()
            self._unlock()
            self._show_blocked(status, notes)
            self.app.on_design_changed()
            return
        # The flight is over: keep the final orbit (or debris) on screen for
        # a moment, then move on to the Results step.
        self.viewport.finish(result.launch_success)
        medal = medal_for(result, score, self.mission.scenario)
        award = award_flight(self.app.profile, result, score, medal, self.mission)
        self.app.on_profile_changed()           # header XP balance, sidebar rank
        self.app.last_flight = dict(result=result, score=score, tips=notes, report=report,
                                    medal=medal, award=award,
                                    decisions=self._flight["decisions"])
        self._has_results = True
        self.launch_btn.configure(text="Opening results…")
        self.after(RESULTS_DELAY_MS, self._to_results)

    def _to_results(self) -> None:
        if not self.winfo_exists():
            return
        self._running = False
        self._unlock()
        self.app.on_design_changed()       # time meter, header, badge
        self.app.show_screen("results")

    def _unlock(self) -> None:
        self.launch_btn.configure(state="normal",
                                  text="🚀  LAUNCH AGAIN" if self._has_results
                                  else "🚀  LAUNCH SIMULATION")
        self.preview_btn.configure(state="normal")
        self.results_btn.configure(state="normal")
        self.app.set_navigation_enabled(True)

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------
    def _show_blocked(self, status: str, problems: list[str]) -> None:
        card = Card(self.notice, border_color=T.DANGER)
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


class EventPrompt(Card):
    """Modal event card shown over the 3D view while the flight is paused:
    what happened, and two choices with their trade-offs spelled out."""

    WIDTH = 600

    def __init__(self, master, card: EventCard, on_choose, phase: str | None = None) -> None:
        super().__init__(master, fg_color=T.SURFACE, border_width=2,
                         border_color=T.WARNING, width=self.WIDTH)
        self.grid_columnconfigure((0, 1), weight=1, uniform="choice")
        phase = phase or ("Cruise" if card.phase == "cruise" else "Operations")
        eyebrow(self, f"⚠  Incoming event · {phase} · flight paused", T.WARNING).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=T.PAD_LG, pady=(T.PAD_LG, 4))
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=1, column=0, columnspan=2, sticky="ew", padx=T.PAD_LG)
        text(head, card.icon, (30, "normal")).pack(side="left", padx=(0, 10))
        text(head, card.title, T.H1).pack(side="left")
        glossary_text(self, card.story, T.BODY, T.TEXT_MUTED).grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=T.PAD_LG, pady=(6, T.PAD))

        for i, choice in enumerate(card.choices):
            option = SelectableCard(self, command=lambda c=choice: on_choose(card, c))
            option.grid(row=3, column=i, sticky="nsew",
                        padx=(T.PAD_LG if i == 0 else 6, 6 if i == 0 else T.PAD_LG))
            option.grid_columnconfigure(0, weight=1)
            text(option, f"{i + 1}", (11, "bold"), T.ACCENT).grid(sticky="w", padx=T.PAD,
                                                                  pady=(12, 0))
            glossary_text(option, choice.label, T.H3).grid(sticky="ew", padx=T.PAD)
            chips = ctk.CTkFrame(option, fg_color="transparent")
            chips.grid(sticky="w", padx=T.PAD, pady=(8, 14))
            for chip_text, tone in choice.chips:
                Chip(chips, chip_text, tone).pack(anchor="w", pady=2)
            option.finalize()
        text(self, "Choose wisely — your call changes the mission's score.", T.SMALL,
             T.TEXT_DIM).grid(row=4, column=0, columnspan=2, sticky="w",
                              padx=T.PAD_LG, pady=(T.PAD, T.PAD_LG))
