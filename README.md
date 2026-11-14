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
2. **Scenario** — pick a mission scenario (difficulty-scaled event
   frequency, or sandbox mode)
3. **Spacecraft bus** — add/remove structure, power (solar arrays, RTG),
   comms, ADCS, and avionics components
4. **Payload** — add/remove scientific instruments, each with mass,
   power, cost, and data-rate trade-offs
5. **Orbit & launch** — choose orbital regime, launch vehicle, and
   destination planet
6. **Dashboard** — live resource budgets (mass, power, cost, data, time)
   with feasibility warnings
7. **Flight path** — animated 2D trajectory visualization
2. **Scenario** — pick a mission scenario (difficulty-scaled budget and
   event frequency, or sandbox mode)
3. **Spacecraft bus** — add/remove components grouped by category
   (Power Generation, Communications, Attitude Control, Avionics &
   Storage, Structure, Propulsion); required groups are highlighted
4. **Payload** — add/remove instruments grouped by capability tag
   (imaging, spectroscopy, subsurface, space weather, sample return,
   comms); each adds science but consumes mass, power, cost, and data
5. **Orbit & launch** — choose orbital regime, launch vehicle (shown as
   a tiered button list: Light / Medium / Heavy), and destination planet.
   All dropdowns start blank; Next is blocked with a warning until
   orbit, vehicle, and destination are selected, and scenario-disallowed
   orbits snap back to blank
6. **Dashboard** — live resource budgets (mass, power, cost, data
   storage, time) with feasibility warnings
7. **Flight path** — animated 2D trajectory with planet artwork and a
   rotating rocket sprite
8. **Planet facts** — educational facts about the chosen destination
9. **Simulation** — blocked if the design has unresolved errors
   (sandbox mode excepted); shows score + report on success

### Spacecraft design

- **Bus components**: structures (compact/standard/heavy), solar arrays,
  RTG, comms systems, ADCS, avionics, and expanded storage — each with
  mass, power draw/generation, cost, downlink capacity, and (for
  avionics/storage) onboard data capacity in GB
- **Instruments**: cameras, spectrometers, magnetometers, etc. — each
  adds science value but consumes resources and generates data
- **Validation**: missing essentials (power, comms, ADCS, avionics) are
  flagged; hard violations include budget/mass/power overruns plus
  tight margins (<10% budget/mass, <15% power), exhausted mission time,
  and data backlog exceeding onboard storage

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
  spiral departure → return to Earth. Planets render as real artwork
  from `planetImages/` (Pillow-resized, cached), Earth included, and
  the rocket flies the route as a rotated `rocket.png` sprite (falls
  back to a triangle if the image is missing). Orbit routes are sized
  from the displayed planet diameter, so resizing never clips the path

### Simulation engine

`src/game/simulation.py` runs the mission lifecycle:

- **Launch** — success roll against launch vehicle reliability
- **Cruise** — body-dependent transit time (Moon 3mo, Mars 8mo, etc.)
- **Operations** — monthly loop accumulating science, generating data,
  and downlinking at a duty-cycled rate; onboard storage capacity
  (from bus components) caps how much data can be held
- **Random events** — micrometeorite strikes, solar flares, ground
  station outages, propellant leaks, bonus science windows, computer
  glitches, safe-mode events (frequency scaled by scenario difficulty)
- **Objectives** — scenario required objectives checked against
  capabilities (imaging, spectroscopy, sample return, etc.)
- **Penalties** — data backlog and negative power margin reduce science;
  total elapsed time (cruise + ops) is tracked against the mission limit

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

`src/data/scenarios.json` defines mission scenarios with durations,
required objectives/capabilities, orbit/instrument restrictions, and
difficulty levels:

- **Cadet** — half event frequency
- **Engineer** — baseline
- **Expert** — 1.5× event frequency
- **Sandbox** — unconstrained experimentation

**Budget is set by the destination**, not the scenario
(`budget_for()` in `src/game/planets.py`). It scales in a straight line
with distance from Earth, from **$200M** for the Moon (384,400 km) up to
**$7.1B** for Neptune (4.3 billion km) — e.g. Mars ≈ $561M, Saturn ≈ $2.1B.
Until a destination is chosen the $200M minimum applies. The scenarios'
`budget_usd` values are no longer used.

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
    app.py                 # Window shell: header, stepper, navigation, toasts
    theme.py               # Design tokens: colours, type ramp, spacing
    widgets.py             # Reusable cards, badges, meters, stepper, score ring
    telemetry.py           # Live resource sidebar + readiness checks
    assets.py              # Planet / rocket image loading (Pillow optional)
    screens/               # One module per wizard step (welcome, bus &
                           #   payload, orbit & launch, flight & facts,
                           #   review, launch & results)
    trajectory_view.py     # 2D animated trajectory canvas
    app.py                 # Main wizard UI (customtkinter): grouped
                           #   pickers, blank-dropdown validation,
                           #   scroll-wheel support, save/load, sim gate
    trajectory_view.py     # 2D animated trajectory canvas with planet
                           #   and rocket artwork (Pillow)
    spacecraft_view.py     # Spacecraft visualization stub
  data/
    instruments.json       # Instrument stats
    orbits.json            # Orbit definitions
    launch_vehicles.json   # Launch vehicle stats
    scenarios.json         # Mission scenarios
planetImages/              # Planet PNG artwork for the trajectory view
rocket.png                 # Rocket sprite for the transfer animation
gmat-win-R2026a/           # Bundled GMAT astrodynamics engine
```

## Getting Started

```bash
python -m src.main            # GUI (default)
python -m src.main --console  # Console mode
```

Requires Python 3.13+, `customtkinter` and `pillow` (GUI mode only —
`pip install -r requirements.txt`; without Pillow the planet artwork
falls back to coloured shapes). GMAT
integration works out of the box with the bundled `gmat-win-R2026a/`
folder; if it's missing, the game falls back to simplified orbital
data.
Requires Python 3.13+ and the packages in `requirements.txt`
(`customtkinter`, `pillow`). GMAT integration works out of the box with
the bundled `gmat-win-R2026a/` folder; if it's missing, the game falls
back to simplified orbital data.

## Key Design Trade-offs (the educational core)

- More capable instruments → more science, but more mass/power/cost/data
- Higher orbit → longer lifetime & better coverage, but harder launch & comms
- Bigger launch vehicle → more capability, but much higher cost
- More data → better science, but requires comms capacity to download
- Longer mission → more science accumulation, but more ops cost & risk
- Closer planets → cheaper/faster, but less capability needed
- Outer planets → flagship launchers only, long comms delays
