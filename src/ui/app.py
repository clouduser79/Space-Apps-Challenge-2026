"""Main game application — CustomTkinter "mission control" GUI.

Flow:
  Welcome (commander name + scenario)
    -> Designer wizard, one screen at a time:
       Bus -> Payload -> Orbit & Launch -> Planet Facts -> Mission Review
       -> Launch (simulation, flown in 3D) -> Results (mission report)

This module is only the shell: window, header, step navigation, the live
telemetry sidebar and notifications. Each step lives in src/ui/screens/,
and all visual constants live in src/ui/theme.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import customtkinter as ctk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.game.instruments import get_catalog as get_instruments
from src.game.launch_vehicle import get_catalog as get_launch_vehicles
from src.game.mission import Mission
from src.game.orbit import Orbit
from src.game.players import Player
from src.game.profile import load_profile, save_profile
from src.game.scenarios import get_scenarios
from src.ui import assets
from src.ui import theme as T
from src.ui.screens.base import Screen
from src.ui.screens.design import BusScreen, PayloadScreen
from src.ui.screens.explore import FactsScreen
from src.ui.screens.launch import LaunchScreen
from src.ui.screens.orbit import OrbitLaunchScreen
from src.ui.screens.results import ResultsScreen
from src.ui.screens.review import ReviewScreen
from src.ui.screens.welcome import WelcomeView
from src.ui.telemetry import TelemetryPanel
from src.ui.widgets import (Badge, Stepper, Toast, eyebrow, ghost_button,
                            glossary_text, primary_button, text)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Wizard order: (screen class, short label for the stepper)
SCREENS: list[tuple[type[Screen], str]] = [
    (BusScreen, "Bus"),
    (PayloadScreen, "Payload"),
    (OrbitLaunchScreen, "Orbit & Launch"),
    (FactsScreen, "Planet Facts"),
    (ReviewScreen, "Review"),
    (LaunchScreen, "Launch"),
    (ResultsScreen, "Results"),
]
GATE_KEY = "orbit"   # can't move past this step without orbit + LV + destination


def load_orbits() -> dict[str, Orbit]:
    raw = json.loads((DATA_DIR / "orbits.json").read_text(encoding="utf-8"))
    orbits = {}
    for e in raw["orbits"]:
        o = Orbit(
            id=e["id"], name=e["name"], body=e["body"],
            altitude_km=float(e["altitude_km"]),
            inclination_deg=float(e["inclination_deg"]),
            period_hours=float(e["period_hours"]),
            description=e.get("description", ""),
            coverage=e.get("coverage", "global"),
            eclipse_fraction=float(e.get("eclipse_fraction", 0.0)),
            drag_factor=float(e.get("drag_factor", 0.0)),
            comms_passes_per_day=int(e.get("comms_passes_per_day", 0)),
            radiation_level=int(e.get("radiation_level", 0)),
            revisit_days=float(e.get("revisit_days", 7.0)),
            comms_pass_minutes=float(e.get("comms_pass_minutes", 10.0)),
            station_keeping_dv_m_s_per_year=float(
                e.get("station_keeping_dv_m_s_per_year", 0.0)),
        )
        orbits[o.id] = o
    return orbits


class GameApp(ctk.CTk):
    def __init__(self) -> None:
        T.apply_theme()
        super().__init__(fg_color=T.BG)
        self.title("Space Mission Design Game")
        width = min(1440, self.winfo_screenwidth() - 80)
        height = min(920, self.winfo_screenheight() - 100)
        self.geometry(f"{width}x{height}+40+30")
        self.minsize(1120, 720)

        self.mission: Mission | None = None
        self.last_flight: dict | None = None   # set by Launch, shown by Results
        self.profile = load_profile()           # XP + medals, saves/profile.json
        self.orbits = load_orbits()
        self.instruments = get_instruments()
        self.launch_vehicles = get_launch_vehicles()
        self.scenarios = get_scenarios()

        self.shell: ctk.CTkFrame | None = None
        self.screens: dict[str, Screen] = {}
        self.order: list[str] = []
        self.current: str | None = None
        self._show_welcome()

    # ==================================================================
    # Welcome <-> designer
    # ==================================================================
    def _show_welcome(self) -> None:
        self.welcome = WelcomeView(self, self.scenarios, self._start_mission)
        self.welcome.pack(fill="both", expand=True)

    def _start_mission(self, name: str, scenario) -> None:
        mission = Mission(name=f"{scenario.name} Mission", scenario=scenario)
        mission.players = [Player(name, "Commander")]
        mission.set_objective(scenario.objective)
        self.mission = mission
        self.profile.name = name
        save_profile(self.profile)
        self.welcome.destroy()
        self._build_shell()
        self.show_screen(self.order[0])

    def restart(self) -> None:
        """Tear down the designer and return to the welcome screen."""
        if self.current:
            self.screens[self.current].on_hide()   # stops any flight animation
        self.mission = None
        self.last_flight = None
        self.current = None
        self.screens.clear()
        if self.shell is not None:
            self.shell.destroy()
            self.shell = None
        self._show_welcome()

    def replace_mission(self, mission: Mission) -> None:
        """Swap in a loaded design and re-sync every view."""
        if not mission.players and self.mission is not None:
            mission.players = self.mission.players
        self.mission = mission
        self.last_flight = None                # results belonged to the old design
        self._refresh_header()
        self.on_design_changed()

    # ==================================================================
    # Shell layout
    # ==================================================================
    def _build_shell(self) -> None:
        shell = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        shell.pack(fill="both", expand=True)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(2, weight=1)
        self.shell = shell

        self._build_header(shell)

        self.order = [cls.key for cls, _ in SCREENS]
        self.stepper = Stepper(shell, [(cls.key, label) for cls, label in SCREENS],
                               command=self.show_screen)
        self.stepper.grid(row=1, column=0, sticky="ew", padx=T.PAD_XL, pady=(T.PAD, 0))

        body = ctk.CTkFrame(shell, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=T.PAD_XL, pady=T.PAD_LG)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.content = ctk.CTkFrame(body, fg_color="transparent")
        self.content.grid(row=0, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.telemetry = TelemetryPanel(body, self)
        self.telemetry.grid(row=0, column=1, sticky="ns", padx=(T.PAD_LG, 0))

        for cls, _label in SCREENS:
            self.screens[cls.key] = cls(self.content, self)

        self._build_footer(shell)
        self._refresh_header()

    def _build_header(self, shell) -> None:
        header = ctk.CTkFrame(shell, fg_color=T.SURFACE, corner_radius=0, height=76)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(2, weight=1)
        header.grid_propagate(False)
        header.grid_rowconfigure(0, weight=1)

        icon = assets.rocket_image(34)
        ctk.CTkLabel(header, text="" if icon else "▲", image=icon, width=40,
                     text_color=T.ACCENT).grid(row=0, column=0, padx=(T.PAD_XL, 10))
        title = ctk.CTkFrame(header, fg_color="transparent")
        title.grid(row=0, column=1, sticky="w")
        eyebrow(title, "Mission control").pack(anchor="w")
        self.h_name = text(title, "", T.H2)
        self.h_name.pack(anchor="w")

        self.h_objective = glossary_text(header, "", T.SMALL, T.TEXT_MUTED)
        self.h_objective.grid(row=0, column=2, sticky="ew", padx=T.PAD_XL)

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.grid(row=0, column=3, sticky="e", padx=(0, T.PAD_XL))
        self.h_commander = text(right, "", (12, "bold"), T.TEXT_MUTED)
        self.h_commander.pack(side="left", padx=(0, 12))
        self.h_badge = Badge(right, "")
        self.h_badge.pack(side="left", padx=(0, T.PAD))
        self.h_xp = Badge(right, "", "violet")
        self.h_xp.pack(side="left", padx=(0, 8))
        self.shop_btn = ghost_button(right, "🛒  Shop", self.open_shop, width=96, height=34)
        self.shop_btn.pack(side="left", padx=(0, 8))
        self.restart_btn = ghost_button(right, "New mission", self.restart,
                                        width=120, height=34)
        self.restart_btn.pack(side="left")

    def _refresh_header(self) -> None:
        m = self.mission
        self.h_name.configure(text=m.name)
        self.h_objective.set_text(f"Objective — {m.objective}")
        commander = m.players[0].name if m.players else "Commander"
        self.h_commander.configure(text=f"Cmdr. {commander}")
        self.h_badge.set(*assets.difficulty_tone(m.scenario))
        self.h_xp.set(f"⭐ {self.profile.balance:,} XP", "violet")

    def _build_footer(self, shell) -> None:
        footer = ctk.CTkFrame(shell, fg_color=T.SURFACE, corner_radius=0, height=68)
        footer.grid(row=3, column=0, sticky="ew")
        footer.grid_propagate(False)
        footer.grid_columnconfigure(0, weight=1)
        footer.grid_rowconfigure(0, weight=1)
        self.step_label = text(footer, "", T.SMALL, T.TEXT_MUTED)
        self.step_label.grid(row=0, column=0, sticky="w", padx=T.PAD_XL)
        self.back_btn = ghost_button(footer, "←  Back", self._back, width=120)
        self.back_btn.grid(row=0, column=1, padx=(0, T.PAD_SM))
        self.next_btn = primary_button(footer, "Next", self._next, width=220)
        self.next_btn.grid(row=0, column=2, padx=(0, T.PAD_XL))

    # ==================================================================
    # Navigation
    # ==================================================================
    def _gate_problem(self, target: str) -> str | None:
        """Why the player may not jump to `target` yet (None if allowed)."""
        if target == "results" and self.last_flight is None:
            return "Launch the mission first — results appear after the flight."
        if self.order.index(target) <= self.order.index(GATE_KEY):
            return None
        m = self.mission
        missing = [label for value, label in ((m.orbit, "an orbit"),
                                              (m.launch_vehicle, "a launch vehicle"),
                                              (m.destination, "a destination"))
                   if value is None]
        if missing:
            return "Before continuing, select " + ", ".join(missing) + " in Orbit & Launch."
        return None

    def show_screen(self, key: str) -> None:
        if self.current == key:
            return
        problem = self._gate_problem(key)
        if problem:
            self.toast(problem)
            if key == "results":            # nothing flown yet: stay put
                return
            if self.current != GATE_KEY:
                key = GATE_KEY
            else:
                return
        if self.current:
            old = self.screens[self.current]
            old.on_hide()
            old.grid_remove()
        self.current = key
        screen = self.screens[key]
        screen.grid(row=0, column=0, sticky="nsew")
        if screen.show_telemetry:
            self.telemetry.grid()
            self.telemetry.refresh()
        else:
            self.telemetry.grid_remove()
        screen.on_show()

        index = self.order.index(key)
        self.stepper.set_current(index)
        self.step_label.configure(
            text=f"Step {index + 1} of {len(self.order)}   ·   {screen.title}")
        self.back_btn.configure(state="normal" if index > 0 else "disabled")
        if index == len(self.order) - 1:
            self.next_btn.grid_remove()
        else:
            self.next_btn.grid()
            nxt = self.screens[self.order[index + 1]]
            self.next_btn.configure(text=f"Next: {nxt.title}  →")

    def _back(self) -> None:
        index = self.order.index(self.current)
        if index > 0:
            self.show_screen(self.order[index - 1])

    def _next(self) -> None:
        index = self.order.index(self.current)
        if index < len(self.order) - 1:
            self.show_screen(self.order[index + 1])

    def set_navigation_enabled(self, enabled: bool) -> None:
        """Lock navigation while a simulation is running."""
        state = "normal" if enabled else "disabled"
        for button in self.stepper._buttons:
            button.configure(state=state)
        self.next_btn.configure(state=state)
        self.restart_btn.configure(state=state)
        self.shop_btn.configure(state=state)
        index = self.order.index(self.current)
        self.back_btn.configure(state=state if index > 0 else "disabled")

    # ==================================================================
    # Shared services for screens
    # ==================================================================
    def open_shop(self, focus: str | None = None) -> None:
        """Open the XP shop; `focus` highlights one item."""
        from src.ui.shop import open_shop
        open_shop(self, focus)

    def on_profile_changed(self) -> None:
        """XP or unlocks changed: refresh the header and the current screen."""
        if self.shell is None:
            return
        self._refresh_header()
        self.telemetry.refresh_rank()
        if self.current:
            self.screens[self.current].refresh()

    def on_design_changed(self) -> None:
        """Every design mutation funnels through here."""
        if self.mission is None or self.current is None:
            return
        self.telemetry.refresh()
        self.screens[self.current].refresh()

    def toast(self, message: str, tone: str = "warning", icon: str | None = None,
              duration_ms: int = 2600) -> None:
        Toast.show(self, message, tone, icon, duration_ms)


def main() -> None:
    app = GameApp()
    app.mainloop()


if __name__ == "__main__":
    main()
