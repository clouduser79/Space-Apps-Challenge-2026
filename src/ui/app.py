"""Main game application / UI loop.

Blueprint: orchestrates screens:
  MainMenu -> ScenarioSelect -> MissionDesign (objective, spacecraft,
  instruments, orbit, launch) -> ResourceDashboard -> Simulation ->
  ResultsReport -> Leaderboard

TODO: choose UI framework — options:
  - pygame: game-like feel, good for visualization
  - tkinter/customtkinter: simpler, native desktop
  - web (Flask/FastAPI + JS): easiest multiplayer later
"""


class GameApp:
    """Top-level application controller."""

    def __init__(self) -> None:
        # TODO: initialize UI framework window
        # TODO: load catalogs (instruments, orbits, launch vehicles, scenarios)
        # TODO: create game state
        raise NotImplementedError

    # TODO: screen methods:
    #   show_main_menu()
    #   show_scenario_select()
    #   show_objective_select()
    #   show_spacecraft_designer()   # drag/drop or list components
    #   show_instrument_select()     # with live mass/power/data impact
    #   show_orbit_select()          # with coverage/comm explanations
    #   show_launch_select()         # with compatibility warnings
    #   show_resource_dashboard()    # live bars: mass/power/budget/data/comms/time
    #   run_simulation()             # animated timeline playback
    #   show_results_report()        # score + explanation + suggestions
    #   show_leaderboard()

    # TODO: educational UI patterns:
    #   - tooltips explaining every term ("What is SSO?")
    #   - live "impact preview" when hovering a component:
    #     "Adds 12 kg, 25 W, $4M, 50 Mbps data"
    #   - constraint warnings in red before simulation
    #   - post-decision "why" explanations
