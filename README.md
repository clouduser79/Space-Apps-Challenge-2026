# Space Mission Design Game

An interactive game where players design, manage, and simulate a complete
space mission — choosing objectives, spacecraft components, instruments,
orbits, launch vehicles, and destinations while balancing mass, power,
budget, data, communications, and mission lifetime.

Every design decision has real consequences: more capable instruments mean
more science but more mass, power, cost, and data; higher orbits mean
longer lifetime but harder launches and weaker communications; bigger
rockets cost more but carry more.

## Features

### Mission design wizard (GUI)

The desktop app (`customtkinter`) walks players through a sequential
wizard — one screen at a time with Back/Next navigation:

1. **Welcome** — mission briefing and start
2. **Scenario** — pick a mission scenario (difficulty-scaled budget and
   event frequency, or sandbox mode)
3. **Spacecraft bus** — add/remove structure, power (solar arrays, RTG),
   comms, ADCS, and avionics components
4. **Payload** — add/remove scientific instruments, each with mass,
   power, cost, and data-rate trade-offs
5. **Orbit & launch** — choose orbital regime, launch vehicle, and
   destination planet
6. **Dashboard** — live resource budgets (mass, power, cost, data, time)
   with feasibility warnings
7. **Flight path** — animated 2D trajectory visualization
8. **Planet facts** — educational facts about the chosen destination
9. **Simulation** — run the mission and see the score + report

### Spacecraft design

- **Bus components**: structures (compact/standard/heavy), solar arrays,
  RTG, comms systems, ADCS, avionics — each with mass, power draw/generation,
  cost, and downlink capacity
- **Instruments**: cameras, spectrometers, magnetometers, etc. — each
  adds science value but consumes resources and generates data
- **Validation**: missing essentials (power, comms, ADCS, avionics) are
  flagged; hard constraint violations (budget/mass/power) block flight

### Orbits

Six orbital regimes in `src/data/orbits.json`, each with altitude,
inclination, period, coverage, eclipse fraction, drag, comms passes,
radiation level, revisit time, and station-keeping cost:

- **LEO** — low Earth orbit, easy comms, drag-limited lifetime
- **SSO** — sun-synchronous, consistent lighting for imaging
- **GEO** — geostationary, continuous coverage of one region
- **Earth–Sun L1** — halo orbit for solar observation
- **Low Lunar Orbit** — Moon missions
- **Mars LMO** — Mars orbit operations

Orbit methods compute science coverage score, comms capacity per day,
estimated lifetime (drag/radiation/station-keeping limited), and an
educational explanation.

### Real astrodynamics via GMAT

`src/game/gmat_bridge.py` integrates the bundled **GMAT** (General
Mission Analysis Tool, `gmat-win-R2026a/`) installation:

- Generates GMAT `.script` files with real Keplerian orbital elements
- Runs `GmatConsole.exe` headless (works on any Python version — the
  gmatpy bindings only support ≤3.14)
- Parses `ReportFile` output for real osculating orbital data
- Selecting an orbit shows live GMAT-computed **velocity, period, SMA,
  and eccentricity** in the orbit screen

### Destinations & trajectory animation

- **8 destinations**: Mercury, Moon, Mars, Venus, Jupiter, Saturn,
  Uranus, Neptune — each with real facts (diameter, day length, moons)
- **Reachability**: launch vehicle payload capacity classes
  (`escape` / `interplanetary` / `deep_space`) gate which planets are
  reachable — outer ice giants need flagship launchers
- **Orbit scoring**: each orbit is scored 0–100 for a destination with
  human-readable reasons (body match, altitude, inclination, period,
  distance)
- **Animated flight path** (`src/ui/trajectory_view.py`): outbound
  transfer arc → orbit intercept → 2 loops around the destination →
  spiral departure → return to Earth, with a rocket marker animating
  the full mission profile

### Simulation engine

`src/game/simulation.py` runs the mission lifecycle:

- **Launch** — success roll against launch vehicle reliability
- **Cruise** — body-dependent transit time (Moon 3mo, Mars 8mo, etc.)
- **Operations** — monthly loop accumulating science, generating data,
  and downlinking at a duty-cycled rate
- **Random events** — micrometeorite strikes, solar flares, ground
  station outages, propellant leaks, bonus science windows, computer
  glitches, safe-mode events (frequency scaled by scenario difficulty)
- **Objectives** — scenario required objectives checked against
  capabilities (imaging, spectroscopy, sample return, etc.)
- **Penalties** — data backlog and negative power margin reduce science

### Scoring & reporting

`src/game/scoring.py` produces a 0–100 score from five weighted
components:

- Science return (40%)
- Objectives met (25%)
- Efficiency — data backlog vs. downlink (15%)
- Reliability — fewer anomalies (10%)
- Innovation (10%)

The post-mission report explains **why** the mission succeeded or
failed with plain-language engineering feedback (e.g., "your
instruments generate far more data than your comms can downlink").
Scores ≥ 90 show a **SUCCESS!** banner.

### Save / load / leaderboard

`src/game/save_load.py` persists everything to `src/game/saves/`:

- **Save design** — serialize a mission (spacecraft, orbit, launch
  vehicle, destination, scenario) to JSON
- **Load design** — restore a saved mission and continue editing
- **Leaderboard** — every simulation result is appended to
  `history.jsonl` and displayed sorted by score on the dashboard

### Scenarios & difficulty

`src/data/scenarios.json` defines mission scenarios with budgets,
durations, required objectives/capabilities, orbit/instrument
restrictions, and difficulty levels:

- **Cadet** — 1.5× budget, half event frequency
- **Engineer** — baseline
- **Expert** — 0.7× budget, 1.5× event frequency
- **Sandbox** — unconstrained experimentation

### Console mode

A full text-based version is available for terminals:

```bash
python -m src.main --console
```

Includes team setup with roles (Mission Planner, Spacecraft Engineer,
Scientist, Communications, Resource Manager) for up to 4 players.

## Architecture

```
src/
  main.py                  # Entry point (GUI default, --console for CLI)
  game/
    mission.py             # Mission model, lifecycle phases, validation,
                           #   to_dict/from_dict serialization
    spacecraft.py          # Bus components + payload assembly
    instruments.py         # Instrument catalog
    orbit.py               # Orbit model: coverage, lifetime, comms, drag
    planets.py             # Destination catalog, reachability, orbit scoring
    launch_vehicle.py      # Rockets, payload capacity, reliability
    resources.py           # Mass/power/budget/data/comms/time budgets
    simulation.py          # Mission timeline simulator + random events
    scoring.py             # Score engine + post-mission report
    scenarios.py           # Mission scenarios & difficulty levels
    players.py             # Solo + team roles (console mode)
    multiplayer.py         # Networking stub (stretch goal)
    save_load.py           # Save/load missions + leaderboard
    gmat_bridge.py         # GMAT script generation & report parsing
  ui/
    app.py                 # Main wizard UI (customtkinter)
    trajectory_view.py     # 2D animated trajectory canvas
    spacecraft_view.py     # Spacecraft visualization stub
  data/
    instruments.json       # Instrument stats
    orbits.json            # Orbit definitions
    launch_vehicles.json   # Launch vehicle stats
    scenarios.json         # Mission scenarios
gmat-win-R2026a/           # Bundled GMAT astrodynamics engine
```

## Getting Started

```bash
python -m src.main            # GUI (default)
python -m src.main --console  # Console mode
```

Requires Python 3.13+ and `customtkinter` (GUI mode only). GMAT
integration works out of the box with the bundled `gmat-win-R2026a/`
folder; if it's missing, the game falls back to simplified orbital
data.

## Key Design Trade-offs (the educational core)

- More capable instruments → more science, but more mass/power/cost/data
- Higher orbit → longer lifetime & better coverage, but harder launch & comms
- Bigger launch vehicle → more capability, but much higher cost
- More data → better science, but requires comms capacity to download
- Longer mission → more science accumulation, but more ops cost & risk
- Closer planets → cheaper/faster, but less capability needed
- Outer planets → flagship launchers only, long comms delays
