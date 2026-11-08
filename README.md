# Space Mission Design Game

An interactive game where players design, manage, and simulate a complete
space mission — choosing objectives, spacecraft components, instruments,
orbits, and launch vehicles while balancing mass, power, budget, data,
communications, and mission lifetime.

## Status

**Blueprint stage** — project structure and file stubs are in place.
Each file contains TODO comments describing what needs to be implemented.

## Planned Architecture

```
src/
  main.py                  # Entry point / game loop
  game/
    mission.py             # Mission model & lifecycle phases
    spacecraft.py          # Bus components + payload
    instruments.py         # Instrument catalog & trade-offs
    orbit.py               # Orbital regimes & their characteristics
    launch_vehicle.py      # Rockets, payload capacity, reliability
    resources.py           # Mass/power/budget/data/comms/time budgets
    simulation.py          # Mission timeline simulator + random events
    scoring.py             # Score engine + post-mission report
    scenarios.py           # Mission scenarios & difficulty levels
    players.py             # Solo + team (up to 4) with roles
    multiplayer.py         # Networking (stretch goal)
    save_load.py           # Save/share/compare mission designs
  ui/
    app.py                 # Main UI screens & loop
    spacecraft_view.py     # Spacecraft visualization
  data/
    instruments.json       # Instrument stats
    orbits.json            # Orbit definitions
    launch_vehicles.json   # Launch vehicle stats
    scenarios.json         # Mission scenarios
```

## Key Design Trade-offs (the educational core)

- More capable instruments -> more science, but more mass/power/cost/data
- Higher orbit -> longer lifetime & better coverage, but harder launch & comms
- Bigger launch vehicle -> more capability, but much higher cost
- More data -> better science, but requires comms capacity to download
- Longer mission -> more science accumulation, but more ops cost & risk

## Getting Started (once implemented)

```bash
pip install -r requirements.txt
python -m src.main
```

## Suggested Tech Stack

- **Language**: Python (game logic, simulation, data)
- **UI**: pygame or customtkinter (desktop) — decide early; affects multiplayer design
- **Data**: JSON catalogs for easy balancing
- **Tests**: pytest
