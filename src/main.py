"""Space Mission Design Game — console entry point.

Game flow:
  Main menu -> scenario select -> objective -> spacecraft bus ->
  instruments -> orbit -> launch vehicle -> review/simulate -> report
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.game.instruments import get_catalog as get_instruments
from src.game.launch_vehicle import get_catalog as get_launch_vehicles
from src.game.mission import Mission, MissionPhase
from src.game.orbit import Orbit
from src.game.players import Player, PlayerRole, Team
from src.game.scenarios import get_scenarios
from src.game.scoring import ScoreEngine
from src.game.spacecraft import BUS_COMPONENTS

DATA_DIR = Path(__file__).resolve().parent / "data"


def load_orbits() -> dict[str, Orbit]:
    """Build Orbit objects from JSON (orbit.py is a read-only data holder)."""
    raw = json.loads((DATA_DIR / "orbits.json").read_text(encoding="utf-8"))
    orbits = {}
    for e in raw["orbits"]:
        o = Orbit(
            name=e["name"],
            body=e["body"],
            altitude_km=float(e["altitude_km"]),
            inclination_deg=float(e["inclination_deg"]),
            period_hours=float(e["period_hours"]),
            description=e.get("description", ""),
        )
        o.id = e["id"]  # attach id for scenario filtering
        orbits[o.id] = o
    return orbits


def hr() -> None:
    print("\n" + "-" * 60)


def pause() -> None:
    input("\nPress Enter to continue...")


def choose(prompt: str, options: list[tuple[str, str]], allow_back: bool = True) -> str | None:
    """Generic menu. options = [(key, label)]. Returns key or None for back."""
    print(f"\n{prompt}")
    for i, (_, label) in enumerate(options, 1):
        print(f"  {i}. {label}")
    if allow_back:
        print("  0. Back")
    while True:
        raw = input("> ").strip()
        if allow_back and raw == "0":
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][0]
        print("Invalid choice.")


def setup_team() -> Team:
    team = Team()
    mode = choose("Game mode:", [
        ("solo", "Solo mission"),
        ("team", "Team mission (up to 4 players)"),
    ])
    if mode == "team":
        n = input("How many players (2-4)? ").strip()
        n = max(2, min(4, int(n) if n.isdigit() else 2))
        roles = list(PlayerRole.ALL)
        for i in range(n):
            name = input(f"Player {i + 1} name: ").strip() or f"Player{i + 1}"
            role = choose(f"{name}, pick a role:",
                          [(r, PlayerRole.LABELS[r]) for r in roles], allow_back=False)
            team.add_player(Player(name, role or PlayerRole.MISSION_PLANNER))
            if role in roles:
                roles.remove(role)
        print("\nTeam roster:")
        print(team.contributions_report())
    else:
        name = input("Pilot name (Enter for 'Commander'): ").strip() or "Commander"
        team.add_player(Player(name, PlayerRole.MISSION_PLANNER))
    return team


def pick_scenario():
    scenarios = get_scenarios()
    options = [(s.id, f"{s.name} [{s.difficulty}] — {s.description}")
               for s in scenarios.values()]
    key = choose("Select mission scenario:", options, allow_back=False)
    return scenarios[key]


def design_spacecraft(mission: Mission, instruments, orbits) -> None:
    """Interactive bus + payload designer with live consequence preview."""
    sc = mission.spacecraft
    print("\n=== SPACECRAFT DESIGN ===")
    print("Every component adds mass, power draw, cost, and data load.")
    print("You need: power generation, comms, ADCS, avionics to fly.\n")

    while True:
        print(mission.spacecraft.summary())
        missing = sc.missing_essentials()
        if missing:
            print("MISSING:", ", ".join(missing))
        print("\nCurrent bus:")
        for c in sc.bus:
            print(f"  - {c.name} ({c.id})")
        print("\nPayload:")
        for i in sc.payload:
            print(f"  - {i.name}")

        action = choose("Spacecraft designer:", [
            ("bus", "Add/remove bus component"),
            ("payload", "Add/remove instrument"),
            ("orbit", "Choose orbit"),
            ("launch", "Choose launch vehicle"),
            ("done", "Finish design & review"),
        ])
        if action is None:
            continue
        if action == "done":
            mission.phase = MissionPhase.REVIEW
            return
        if action == "bus":
            _design_bus(mission)
        elif action == "payload":
            _design_payload(mission, instruments)
        elif action == "orbit":
            _design_orbit(mission, orbits)
        elif action == "launch":
            _design_launch(mission)


def _design_bus(mission: Mission) -> None:
    sc = mission.spacecraft
    # Show components not yet added, plus option to remove
    options = []
    for cid, comp in BUS_COMPONENTS.items():
        if not any(c.id == cid for c in sc.bus):
            options.append((f"add:{cid}", f"ADD {comp.impact_summary()}"))
    for c in sc.bus:
        options.append((f"rm:{c.id}", f"REMOVE {c.name}"))
    options.append(("cancel", "Cancel"))
    key = choose("Bus components:", options)
    if not key or key == "cancel":
        return
    if key.startswith("add:"):
        mission.add_bus_component(BUS_COMPONENTS[key[4:]])
    elif key.startswith("rm:"):
        mission.remove_bus_component(key[3:])


def _design_payload(mission: Mission, instruments) -> None:
    sc = mission.spacecraft
    options = []
    for iid, inst in instruments.items():
        if not any(i.id == iid for i in sc.payload):
            options.append((f"add:{iid}", f"ADD {inst.impact_summary()}"))
    for i in sc.payload:
        options.append((f"rm:{i.id}", f"REMOVE {i.name}"))
    options.append(("cancel", "Cancel"))
    key = choose("Scientific instruments (each adds mass/power/cost/data):", options)
    if not key or key == "cancel":
        return
    try:
        if key.startswith("add:"):
            mission.add_instrument(instruments[key[4:]])
        elif key.startswith("rm:"):
            mission.remove_instrument(key[3:])
    except ValueError as e:
        print(f"\n!! {e}")


def _design_orbit(mission: Mission, orbits) -> None:
    options = []
    for oid, o in orbits.items():
        if (mission.scenario.allowed_orbits
                and oid not in mission.scenario.allowed_orbits):
            continue
        options.append((oid, f"{o.name} — {o.body}, {o.altitude_km:.0f} km, "
                               f"{o.description[:60]}"))
    key = choose("Select orbit:", options)
    if key:
        mission.set_orbit(orbits[key])
        print(f"\nOrbit set: {orbits[key].name}")


def _design_launch(mission: Mission) -> None:
    lvs = get_launch_vehicles()
    options = []
    for lid, lv in lvs.items():
        if mission.orbit:
            ok, reason = lv.can_launch(mission.spacecraft.total_mass_kg, mission.orbit)
            label = f"{lv.name} — ${lv.cost_usd / 1e6:.0f}M, " \
                    f"reliability {lv.reliability:.0%} | {reason}"
        else:
            label = f"{lv.name} — ${lv.cost_usd / 1e6:.0f}M, " \
                    f"reliability {lv.reliability:.0%} (select orbit first)"
        options.append((lid, label))
    key = choose("Select launch vehicle:", options)
    if key:
        mission.set_launch_vehicle(lvs[key])
        print(f"\nLaunch vehicle set: {lvs[key].name}")


def review_and_simulate(mission: Mission) -> None:
    print("\n=== DESIGN REVIEW ===")
    errors, warnings = mission.validate_design()
    print(mission.dashboard())
    hr()
    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  ! {w}")
    if errors:
        print("\nERRORS — design is not flyable:")
        for e in errors:
            print(f"  X {e}")
        print("\nGo back and fix these, or continue anyway to see what happens.")
    else:
        print("\nDesign is feasible! No constraint violations.")

    action = choose("Next step:", [
        ("edit", "Go back to editing"),
        ("sim", "Run mission simulation"),
    ], allow_back=False)
    if action == "edit":
        mission.phase = MissionPhase.SPACECRAFT
        design_spacecraft(mission, get_instruments(), load_orbits())
        review_and_simulate(mission)
        return

    # Simulation
    print("\n=== MISSION SIMULATION ===")
    print("Launching... cruise... operations...\n")
    result = mission.simulate(seed=None)
    score = ScoreEngine().score(result)
    report = ScoreEngine().generate_report(result)
    print(report)
    print(f"\nFINAL SCORE: {score} / 100")
    mission.phase = MissionPhase.DONE


def console_main() -> None:
    print("=" * 60)
    print("  SPACE MISSION DESIGN GAME")
    print("  Design. Build. Launch. Learn from trade-offs.")
    print("=" * 60)

    team = setup_team()
    scenario = pick_scenario()

    mission = Mission(name=f"{scenario.name} Mission", scenario=scenario)
    mission.players = team.players
    mission.set_objective(scenario.objective)

    print(f"\nObjective confirmed: {mission.objective}")
    if mission.requirements:
        print("Derived requirements:")
        for r in mission.requirements:
            print(f"  - {r}")
    pause()

    design_spacecraft(mission, get_instruments(), load_orbits())
    review_and_simulate(mission)

    print("\nThanks for flying, Commander.")


def main() -> None:
    if "--console" in sys.argv:
        console_main()
        return
    from src.ui.app import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
