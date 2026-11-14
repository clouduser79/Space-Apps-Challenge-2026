"""Main game application — customtkinter GUI.

Screens:
  Welcome (solo/team + scenario select)
  Designer (tabs: Spacecraft bus, Payload, Orbit & Launch)
  Dashboard (live resource bars)
  Simulation -> Results report
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import customtkinter as ctk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.game.instruments import get_catalog as get_instruments
from src.game.launch_vehicle import get_catalog as get_launch_vehicles
from src.game.mission import Mission
from src.game.orbit import Orbit
from src.game.planets import PLANETS, reachable_planets, score_orbit_for
from src.game.players import Player
from src.game.save_load import load_leaderboard, load_mission, save_mission, save_result
from src.game.scenarios import get_scenarios
from src.game.scoring import ScoreEngine
from src.game.spacecraft import BUS_COMPONENTS
from src.ui.trajectory_view import TrajectoryCanvas

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


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
        super().__init__()
        self.title("Space Mission Design Game")
        self.geometry("1250x1050")
        self.mission: Mission | None = None
        self.orbits = load_orbits()
        self.instruments = get_instruments()
        self.launch_vehicles = get_launch_vehicles()
        self.scenarios = get_scenarios()
        self._build_welcome()

    # ---------------- Welcome screen ----------------
    def _build_welcome(self) -> None:
        self.welcome = ctk.CTkFrame(self)
        self.welcome.pack(fill="both", expand=True, padx=30, pady=30)

        ctk.CTkLabel(self.welcome, text="SPACE MISSION DESIGN GAME",
                     font=ctk.CTkFont(size=28, weight="bold")).pack(pady=(40, 5))
        ctk.CTkLabel(self.welcome,
                     text="Design. Build. Launch. Learn from trade-offs.",
                     font=ctk.CTkFont(size=14)).pack(pady=(0, 30))

        card = ctk.CTkFrame(self.welcome)
        card.pack(pady=10)

        ctk.CTkLabel(card, text="Pilot name:").grid(row=0, column=0, padx=15, pady=10, sticky="w")
        self.name_entry = ctk.CTkEntry(card, width=220, placeholder_text="Commander")
        self.name_entry.grid(row=0, column=1, padx=15, pady=10)

        ctk.CTkLabel(card, text="Scenario:").grid(row=1, column=0, padx=15, pady=10, sticky="w")
        self.scenario_menu = ctk.CTkOptionMenu(
            card, width=360,
            values=[f"{s.name} [{s.difficulty}]" for s in self.scenarios.values()],
            command=self._on_scenario_pick)
        self.scenario_menu.grid(row=1, column=1, padx=15, pady=10)
        self._scenario_labels = {f"{s.name} [{s.difficulty}]": s for s in self.scenarios.values()}
        first = next(iter(self.scenarios.values()))
        self.scenario_menu.set(f"{first.name} [{first.difficulty}]")
        self._selected_scenario = first

        self.objective_label = ctk.CTkLabel(card, text=f"Objective: {first.objective}",
                                            wraplength=420, justify="left")
        self.objective_label.grid(row=2, column=0, columnspan=2, padx=15, pady=(0, 15), sticky="w")

        ctk.CTkButton(card, text="Begin Mission Design", width=220, height=40,
                      command=self._start_mission).grid(row=3, column=0, columnspan=2, pady=15)

    def _on_scenario_pick(self, label: str) -> None:
        self._selected_scenario = self._scenario_labels[label]
        self.objective_label.configure(
            text=f"Objective: {self._selected_scenario.objective}")

    def _start_mission(self) -> None:
        name = self.name_entry.get().strip() or "Commander"
        scenario = self._selected_scenario
        self.mission = Mission(name=f"{scenario.name} Mission", scenario=scenario)
        self.mission.players = [Player(name, "Commander")]
        self.mission.set_objective(scenario.objective)
        self.welcome.destroy()
        self._build_main()

    # ---------------- Main designer ----------------
    def _build_main(self) -> None:
        m = self.mission
        self.main = ctk.CTkFrame(self)
        self.main.pack(fill="both", expand=True, padx=15, pady=15)

        header = ctk.CTkFrame(self.main, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(header, text=f"{m.name} — {m.scenario.name} ({m.scenario.difficulty})",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")
        ctk.CTkLabel(header, text=f"Objective: {m.objective}",
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=20)

        # Sequential screens (wizard style) — one visible at a time
        self.screen_box = ctk.CTkFrame(self.main, fg_color="transparent")
        self.screen_box.pack(fill="both", expand=True)

        screen_order = [
            ("bus", "Spacecraft Bus"),
            ("payload", "Payload"),
            ("orbit", "Orbit & Launch"),
            ("flight", "Flight Path"),
            ("facts", "Planet Facts"),
            ("dash", "Dashboard"),
            ("sim", "Simulate"),
        ]
        self.screens: dict[str, ctk.CTkFrame] = {}
        self.screen_titles: dict[str, str] = {}
        for key, title in screen_order:
            frame = ctk.CTkFrame(self.screen_box)
            self.screens[key] = frame
            self.screen_titles[key] = title
            setattr(self, f"tab_{key}", frame)
        self._screen_order = [k for k, _ in screen_order]
        self._screen_idx = 0

        self._build_bus_tab()
        self._build_payload_tab()
        self._build_orbit_tab()
        self._build_flight_tab()
        self._build_facts_tab()
        self._build_dashboard_tab()
        self._build_sim_tab()

        # Navigation bar
        nav = ctk.CTkFrame(self.main, fg_color="transparent")
        nav.pack(fill="x", pady=(8, 0))
        self.step_label = ctk.CTkLabel(nav, text="", font=ctk.CTkFont(size=12))
        self.step_label.pack(side="left", padx=10)
        self.back_btn = ctk.CTkButton(nav, text="Back", width=100,
                                      command=self._nav_back)
        self.back_btn.pack(side="right", padx=5)
        self.next_btn = ctk.CTkButton(nav, text="Next", width=100,
                                      command=self._nav_next)
        self.next_btn.pack(side="right", padx=5)

        self.refresh_all()
        self._show_screen("bus")

    # ----- Screen navigation -----
    def _show_screen(self, key: str) -> None:
        for k, frame in self.screens.items():
            frame.pack_forget()
        self.screens[key].pack(fill="both", expand=True)
        self._screen_idx = self._screen_order.index(key)
        total = len(self._screen_order)
        self.step_label.configure(
            text=f"Step {self._screen_idx + 1} of {total} — {self.screen_titles[key]}")
        self.back_btn.configure(state="normal" if self._screen_idx > 0 else "disabled")
        if self._screen_idx == total - 1:
            self.next_btn.pack_forget()
        else:
            self.next_btn.pack(side="right", padx=5)
            self.next_btn.configure(text="Next", state="normal")
        # Refresh dynamic content when its screen is shown
        if key == "dash":
            self._refresh_dashboard()
        if key == "flight" and self.mission.destination is not None:
            self.trajectory.plot(self.mission.destination)

    def _nav_back(self) -> None:
        if self._screen_idx > 0:
            self._show_screen(self._screen_order[self._screen_idx - 1])

    def _nav_next(self) -> None:
        if self._screen_idx < len(self._screen_order) - 1:
            self._show_screen(self._screen_order[self._screen_idx + 1])

    def _restart(self) -> None:
        """Tear down the designer and return to the welcome screen."""
        if hasattr(self, "trajectory"):
            self.trajectory.stop_animation()
        self.mission = None
        self.main.destroy()
        self._build_welcome()

    # ----- Bus tab -----
    def _build_bus_tab(self) -> None:
        tab = self.tab_bus
        ctk.CTkLabel(tab, text="Bus Components — each adds mass, cost, and power effects.",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(10, 5))
        self.bus_list = ctk.CTkScrollableFrame(tab)
        self.bus_list.pack(fill="both", expand=True, pady=5)

    def _refresh_bus(self) -> None:
        for w in self.bus_list.winfo_children():
            w.destroy()
        owned = {c.id for c in self.mission.spacecraft.bus}
        for cid, comp in BUS_COMPONENTS.items():
            row = ctk.CTkFrame(self.bus_list, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=comp.impact_summary(), anchor="w",
                         width=430).pack(side="left", padx=5)
            if cid in owned:
                btn = ctk.CTkButton(row, text="Remove", width=80, fg_color="#8B3A3A",
                                    command=lambda c=cid: self._remove_bus(c))
            else:
                btn = ctk.CTkButton(row, text="Add", width=80,
                                    command=lambda c=cid: self._add_bus(c))
            btn.pack(side="right", padx=5)

    def _add_bus(self, cid: str) -> None:
        self.mission.add_bus_component(BUS_COMPONENTS[cid])
        self.refresh_all()

    def _remove_bus(self, cid: str) -> None:
        self.mission.remove_bus_component(cid)
        self.refresh_all()

    # ----- Payload tab -----
    def _build_payload_tab(self) -> None:
        tab = self.tab_payload
        ctk.CTkLabel(tab,
                     text="Instruments — more science means more mass, power, cost, and data.",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(10, 5))
        self.payload_list = ctk.CTkScrollableFrame(tab)
        self.payload_list.pack(fill="both", expand=True, pady=5)

    def _refresh_payload(self) -> None:
        for w in self.payload_list.winfo_children():
            w.destroy()
        owned = {i.id for i in self.mission.spacecraft.payload}
        allowed = self.mission.scenario.allowed_instruments
        for iid, inst in self.instruments.items():
            if allowed and iid not in allowed:
                continue
            row = ctk.CTkFrame(self.payload_list, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=inst.impact_summary() + f"  [{', '.join(inst.tags)}]",
                         anchor="w", width=430).pack(side="left", padx=5)
            if iid in owned:
                btn = ctk.CTkButton(row, text="Remove", width=80, fg_color="#8B3A3A",
                                    command=lambda i=iid: self._remove_inst(i))
            else:
                btn = ctk.CTkButton(row, text="Add", width=80,
                                    command=lambda i=iid: self._add_inst(i))
            btn.pack(side="right", padx=5)

    def _add_inst(self, iid: str) -> None:
        try:
            self.mission.add_instrument(self.instruments[iid])
        except ValueError as e:
            self._toast(str(e))
        self.refresh_all()

    def _remove_inst(self, iid: str) -> None:
        self.mission.remove_instrument(iid)
        self.refresh_all()

    # ----- Orbit & Launch tab -----
    def _build_orbit_tab(self) -> None:
        tab = self.tab_orbit
        ctk.CTkLabel(tab, text="Orbit", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(10, 5))
        self.orbit_menu = ctk.CTkOptionMenu(
            tab, values=[o.name for o in self.orbits.values()],
            command=self._pick_orbit)
        self.orbit_menu.pack(anchor="w", padx=10)
        self.orbit_desc = ctk.CTkLabel(tab, text="", wraplength=700, justify="left")
        self.orbit_desc.pack(anchor="w", padx=10, pady=5)
        self._orbit_by_name = {o.name: o for o in self.orbits.values()}

        ctk.CTkLabel(tab, text="Launch Vehicle", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(20, 5))
        self.lv_menu = ctk.CTkOptionMenu(
            tab, values=[lv.name for lv in self.launch_vehicles.values()],
            command=self._pick_lv)
        self.lv_menu.pack(anchor="w", padx=10)
        self.lv_desc = ctk.CTkLabel(tab, text="", wraplength=700, justify="left")
        self.lv_desc.pack(anchor="w", padx=10, pady=5)
        self._lv_by_name = {lv.name: lv for lv in self.launch_vehicles.values()}

        ctk.CTkLabel(tab, text="Destination", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(20, 5))
        self.dest_menu = ctk.CTkOptionMenu(tab, values=["Select launch vehicle first"],
                                           command=self._pick_destination)
        self.dest_menu.pack(anchor="w", padx=10)
        self.dest_info = ctk.CTkLabel(tab, text="", wraplength=700, justify="left")
        self.dest_info.pack(anchor="w", padx=10, pady=5)
        self._refresh_destinations()

    def _pick_orbit(self, name: str) -> None:
        o = self._orbit_by_name[name]
        try:
            self.mission.set_orbit(o)
        except ValueError as e:
            self._toast(str(e))
            return
        self.orbit_desc.configure(text=f"{o.description} ({o.body}, {o.altitude_km:.0f} km)")
        if self.mission.destination:
            self._pick_destination(self.mission.destination.name)
        self.refresh_all()

    def _pick_lv(self, name: str) -> None:
        lv = self._lv_by_name[name]
        self.mission.set_launch_vehicle(lv)
        if self.mission.orbit:
            ok, reason = lv.can_launch(self.mission.spacecraft.total_mass_kg, self.mission.orbit)
            self.lv_desc.configure(text=f"{lv.description}\n{reason}")
        else:
            self.lv_desc.configure(text=f"{lv.description}\n(Select an orbit first)")
        self._refresh_destinations()
        self.refresh_all()

    # ----- Destination -----
    def _refresh_destinations(self) -> None:
        lv = self.mission.launch_vehicle
        reachable = reachable_planets(lv)
        if not reachable:
            self.dest_menu.configure(values=["No reachable destinations — pick a launch vehicle"])
            self.dest_menu.set("No reachable destinations — pick a launch vehicle")
            self.dest_info.configure(text="")
            return
        names = [p.name for p in reachable]
        self.dest_menu.configure(values=names)
        if self.mission.destination and self.mission.destination.name in names:
            self.dest_menu.set(self.mission.destination.name)
        else:
            self.dest_menu.set(names[0])
            self._pick_destination(names[0])

    def _pick_destination(self, name: str) -> None:
        planet = PLANETS.get(name.lower())
        if planet is None:
            return
        self.mission.set_destination(planet)

        # Planet facts
        facts = "\n".join(f"  - {f}" for f in planet.facts)
        self.dest_info.configure(
            text=f"{planet.name}: {planet.distance_label}\n"
                 f"Diameter {planet.diameter_km:,.0f} km | "
                 f"Day {planet.day_hours:.1f} h | Moons: {planet.moons}\n{facts}")

        # Orbit score for this destination
        score_text = ""
        if self.mission.orbit:
            score, reasons = score_orbit_for(self.mission.orbit, planet)
            score_text = f"\nOrbit suitability score: {score:.0f}/100\n" + \
                         "\n".join(f"  - {r}" for r in reasons)
        self.dest_info.configure(
            text=self.dest_info.cget("text") + score_text)

        # Update flight tab if built
        if hasattr(self, "trajectory"):
            self.trajectory.plot(planet)
            self.flight_status.configure(text=f"Trajectory plotted to {planet.name}.")
        self._update_facts_box()

    # ----- Flight Path tab (trajectory + simulation) -----
    def _build_flight_tab(self) -> None:
        tab = self.tab_flight
        ctk.CTkLabel(tab,
                     text="2D transfer trajectory — green marker is the halfway point "
                          "(potential landing site). The rocket flies out, orbits the "
                          "planet, and returns to Earth.",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(10, 5))
        self.trajectory = TrajectoryCanvas(tab)
        self.trajectory.pack(fill="both", expand=True, pady=5)
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x", pady=5)
        self.fly_btn = ctk.CTkButton(row, text="Animate Transfer", width=180, height=35,
                                     command=self._animate_transfer)
        self.fly_btn.pack(side="left", padx=5)
        self.flight_status = ctk.CTkLabel(row, text="Select a destination in 'Orbit & Launch'.",
                                          font=ctk.CTkFont(size=11))
        self.flight_status.pack(side="left", padx=15)

    def _animate_transfer(self) -> None:
        if self.mission.destination is None:
            # Try to auto-select the first reachable destination
            self._refresh_destinations()
        if self.mission.destination is None:
            self.flight_status.configure(
                text="No reachable destination — pick a launch vehicle in 'Orbit & Launch' first.")
            return
        self.fly_btn.configure(state="disabled")
        self.flight_status.configure(text="Rocket in transit... (outbound -> orbit -> return)")
        self.trajectory.animate(
            self.mission.destination,
            on_done=lambda: self.after(
                0, lambda: (self.fly_btn.configure(state="normal"),
                            self.flight_status.configure(
                                text=f"Completed trip to {self.mission.destination.name}!"))))

    # ----- Dashboard tab -----
    def _build_dashboard_tab(self) -> None:
        tab = self.tab_dash
        self.dash_frame = ctk.CTkFrame(tab, fg_color="transparent")
        self.dash_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.summary_label = ctk.CTkLabel(self.dash_frame, text="", justify="left",
                                          font=ctk.CTkFont(family="Consolas", size=13))
        self.summary_label.pack(anchor="w", pady=5)
        self.bars: dict[str, tuple[ctk.CTkLabel, ctk.CTkProgressBar]] = {}
        for key, label in [("budget", "Budget"), ("mass", "Mass"), ("power", "Power"),
                           ("comms", "Comms"), ("data", "Data"), ("time", "Time")]:
            row = ctk.CTkFrame(self.dash_frame, fg_color="transparent")
            row.pack(fill="x", pady=3)
            lbl = ctk.CTkLabel(row, text=label, width=80, anchor="w")
            lbl.pack(side="left")
            bar = ctk.CTkProgressBar(row, width=400)
            bar.pack(side="left", padx=10)
            val = ctk.CTkLabel(row, text="", width=280, anchor="w")
            val.pack(side="left")
            self.bars[key] = (val, bar)

        self.issues_label = ctk.CTkLabel(self.dash_frame, text="", justify="left",
                                         text_color="#E8A33D", wraplength=700)
        self.issues_label.pack(anchor="w", pady=10)

        btn_row = ctk.CTkFrame(self.dash_frame, fg_color="transparent")
        btn_row.pack(anchor="w", pady=10)
        ctk.CTkButton(btn_row, text="Save Design", width=140,
                      command=self._save_design).pack(side="left", padx=5)
        ctk.CTkButton(btn_row, text="Load Design", width=140,
                      command=self._load_design).pack(side="left", padx=5)
        self.save_status = ctk.CTkLabel(btn_row, text="", font=ctk.CTkFont(size=11))
        self.save_status.pack(side="left", padx=15)

        # Leaderboard
        ctk.CTkLabel(self.dash_frame, text="Leaderboard (top scores)",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(15, 5))
        self.leaderboard_box = ctk.CTkTextbox(self.dash_frame, height=140,
                                              font=ctk.CTkFont(family="Consolas", size=12))
        self.leaderboard_box.pack(fill="x", pady=5)
        self._refresh_leaderboard()

    def _refresh_dashboard(self) -> None:
        m = self.mission
        sc = m.spacecraft
        r = m.resources
        self.summary_label.configure(text=sc.summary())

        def set_bar(key, used, limit, fmt):
            val, bar = self.bars[key]
            frac = min(1.0, used / limit) if limit else 0.0
            bar.set(frac)
            val.configure(text=fmt(used, limit))

        set_bar("budget", r.cost_spent_usd, r.budget_limit_usd,
                lambda u, l: f"${u/1e6:.1f}M / ${l/1e6:.1f}M")
        set_bar("mass", r.mass_used_kg, r.mass_limit_kg or sc.total_mass_kg or 1,
                lambda u, l: f"{u:.0f} kg / {l:.0f} kg")
        set_bar("power", sc.power_consumed_w, sc.power_generated_w or 1,
                lambda u, l: f"{u:.0f} W used / {l:.0f} W gen")
        set_bar("comms", sc.comms_mbps, sc.comms_mbps or 1,
                lambda u, l: f"{u:.0f} Mbps downlink")
        set_bar("data", sc.data_rate_mbps, max(sc.comms_mbps, 1),
                lambda u, l: f"{u:.0f} Mbps gen vs {l:.0f} Mbps downlink")
        set_bar("time", r.time_used_months, r.time_limit_months,
                lambda u, l: f"{u:.0f} / {l} months")

        errors, warnings = m.validate_design()
        issues = []
        if errors:
            issues.append("ERRORS: " + "; ".join(errors))
        if warnings:
            issues.append("WARNINGS: " + "; ".join(warnings))
        missing = sc.missing_essentials()
        if missing:
            issues.append("MISSING SYSTEMS: " + ", ".join(missing))
        self.issues_label.configure(text="\n".join(issues) if issues else "Design looks feasible.")

    # ----- Save / Load -----
    def _save_design(self) -> None:
        try:
            safe = "".join(c if c.isalnum() or c in "-_ " else "_"
                           for c in self.mission.name).strip() or "mission"
            path = save_mission(self.mission, f"{safe}.json")
            self.save_status.configure(text=f"Saved to {path.name}")
        except Exception as e:
            self.save_status.configure(text=f"Save failed: {e}")

    def _load_design(self) -> None:
        from src.game.save_load import SAVE_DIR
        files = sorted(SAVE_DIR.glob("*.json")) if SAVE_DIR.exists() else []
        if not files:
            self.save_status.configure(text="No saved designs found.")
            return
        top = ctk.CTkToplevel(self)
        top.title("Load Mission Design")
        top.geometry("360x300")
        top.transient(self)
        top.grab_set()
        ctk.CTkLabel(top, text="Saved designs:", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=10)
        listbox = ctk.CTkScrollableFrame(top, height=180)
        listbox.pack(fill="both", expand=True, padx=15)
        choice = {"file": None}
        for f in files:
            ctk.CTkButton(listbox, text=f.name, anchor="w",
                          command=lambda p=f: (choice.update(file=p.name), top.destroy())
                          ).pack(fill="x", pady=2)
        ctk.CTkButton(top, text="Cancel", command=top.destroy).pack(pady=10)
        self.wait_window(top)
        if not choice["file"]:
            return
        try:
            self.mission = load_mission(choice["file"])
            self._sync_menus_after_load()
            self.refresh_all()
            self.save_status.configure(text=f"Loaded {choice['file']}")
        except Exception as e:
            self.save_status.configure(text=f"Load failed: {e}")

    def _sync_menus_after_load(self) -> None:
        """Update orbit/LV/destination menus to match a loaded mission."""
        m = self.mission
        if m.orbit:
            self.orbit_menu.set(m.orbit.name)
            self.orbit_desc.configure(
                text=f"{m.orbit.description} ({m.orbit.body}, {m.orbit.altitude_km:.0f} km)")
        if m.launch_vehicle:
            self.lv_menu.set(m.launch_vehicle.name)
            self.lv_desc.configure(text=m.launch_vehicle.description)
        self._refresh_destinations()
        if m.destination:
            self._pick_destination(m.destination.name)

    def _refresh_leaderboard(self) -> None:
        entries = load_leaderboard()[:10]
        self.leaderboard_box.delete("1.0", "end")
        if not entries:
            self.leaderboard_box.insert("end", "No missions recorded yet.")
            return
        for i, e in enumerate(entries, 1):
            self.leaderboard_box.insert(
                "end", f"{i}. {e.get('mission_name', '?')} — "
                       f"{e.get('score', 0):.1f}/100 "
                       f"({'SUCCESS' if e.get('success') else 'partial'})\n")

    # ----- Sim tab -----
    def _build_sim_tab(self) -> None:
        tab = self.tab_sim
        ctk.CTkLabel(tab, text="Run the mission simulation to see how your design performs.",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", pady=10)
        self.sim_btn = ctk.CTkButton(tab, text="LAUNCH SIMULATION", width=220, height=40,
                                     command=self._run_simulation)
        self.sim_btn.pack(pady=10)
        self.report_box = ctk.CTkTextbox(tab, font=ctk.CTkFont(family="Consolas", size=12))
        self.report_box.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkButton(tab, text="Try Again — Start Over", width=220, height=36,
                      fg_color="#555555", hover_color="#444444",
                      command=self._restart).pack(pady=10)
        self.success_label = ctk.CTkLabel(tab, text="", font=ctk.CTkFont(size=20, weight="bold"))
        self.success_label.pack(pady=5)

    # ----- Planet Facts tab -----
    def _build_facts_tab(self) -> None:
        tab = self.tab_facts
        ctk.CTkLabel(tab, text="Facts about your chosen destination",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(10, 5))
        self.facts_box = ctk.CTkTextbox(tab, font=ctk.CTkFont(size=13))
        self.facts_box.pack(fill="both", expand=True, padx=5, pady=5)
        self._update_facts_box()

    def _update_facts_box(self) -> None:
        p = self.mission.destination
        self.facts_box.delete("1.0", "end")
        if p is None:
            self.facts_box.insert("end", "No destination selected yet.\n\n"
                                  "Pick a launch vehicle in 'Orbit & Launch', then choose "
                                  "a destination.")
            return
        self.facts_box.insert("end",
            f"{p.name}\n{'=' * 40}\n\n"
            f"Distance from Earth: {p.distance_label}\n"
            f"Diameter: {p.diameter_km:,.0f} km\n"
            f"Length of day: {p.day_hours:.1f} hours\n"
            f"Moons: {p.moons}\n\n"
            "Fun facts:\n")
        for f in p.facts:
            self.facts_box.insert("end", f"  - {f}\n")

    def _run_simulation(self) -> None:
        self.sim_btn.configure(state="disabled", text="Simulating...")
        self.report_box.delete("1.0", "end")

        def worker():
            m = self.mission
            try:
                errors, _ = m.validate_design()
                header = ""
                if errors and not m.scenario.sandbox_mode:
                    header = ("DESIGN HAS ERRORS — simulation may fail.\n\n"
                              + "\n".join(f"  X {e}" for e in errors)
                              + "\n\nRunning anyway to show consequences...\n\n")
                result = m.simulate()
                score = ScoreEngine().score(result)
                report = ScoreEngine().generate_report(result)
                text = header + report + f"\n\n{'=' * 60}\nFINAL SCORE: {score} / 100\n"
                try:
                    save_result(result, score)
                except Exception:
                    pass
            except Exception as e:
                score = 0
                text = f"SIMULATION CRASHED: {e}"
            # Tkinter is not thread-safe — update UI on the main thread
            self.after(0, lambda: self._show_report(text, score))

        threading.Thread(target=worker, daemon=True).start()

    def _show_report(self, text: str, score: float = 0) -> None:
        self.report_box.delete("1.0", "end")
        self.report_box.insert("end", text)
        self.sim_btn.configure(state="normal", text="LAUNCH SIMULATION")
        self._refresh_leaderboard()
        if score >= 90:
            self.success_label.configure(text="SUCCESS!", text_color="#7BE382")
        else:
            self.success_label.configure(text="")

    # ----- shared -----
    def refresh_all(self) -> None:
        if not hasattr(self, "bus_list"):
            return
        self._refresh_bus()
        self._refresh_payload()
        self._refresh_dashboard()

    def _toast(self, msg: str) -> None:
        top = ctk.CTkToplevel(self)
        top.title("Notice")
        top.geometry("380x120")
        top.transient(self)
        ctk.CTkLabel(top, text=msg, wraplength=340).pack(padx=15, pady=15)
        ctk.CTkButton(top, text="OK", width=80, command=top.destroy).pack(pady=5)


def main() -> None:
    app = GameApp()
    app.mainloop()


if __name__ == "__main__":
    main()
