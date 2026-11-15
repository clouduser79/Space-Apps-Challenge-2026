# Space Mission Game

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
6. **Scenario** — pick a mission scenario (difficulty-scaled budget and
   event frequency, or sandbox mode)
7. **Spacecraft bus** — add/remove components grouped by category
   (Power Generation, Communications, Attitude Control, Avionics &
   Storage, Structure, Propulsion); required groups are highlighted
8. **Payload** — add/remove instruments grouped by capability tag
   (imaging, spectroscopy, subsurface, space weather, sample return,
   comms); each adds science but consumes mass, power, cost, and data
9. **Orbit & launch** — choose orbital regime, launch vehicle (shown as
   a tiered button list: Light / Medium / Heavy), and destination planet.
   All dropdowns start blank; Next is blocked with a warning until
   orbit, vehicle, and destination are selected, and scenario-disallowed
   orbits snap back to blank
10. **Planet facts** — educational facts about the chosen destination
11. **Review** — live resource budgets (mass, power, cost, data storage,
    time) with feasibility warnings, save/load and the leaderboard
12. **Launch** — run the simulation and watch it fly in 3D, with a 2D
    transfer minimap ("Preview route" replays the full round trip); launch
    is blocked when the design has unresolved errors (sandbox excepted)
13. **Results** — opens automatically when the flight ends: score,
    breakdown, objectives, anomalies and engineering feedback

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
Mission Analysis Tool, R2026a) installation:

- Generates GMAT `.script` files with real Keplerian orbital elements
- Runs `GmatConsole` headless (works on any Python version — the
  gmatpy bindings only support ≤3.14)
- Parses `ReportFile` output for real osculating orbital data
- Selecting an orbit shows live GMAT-computed **velocity, period, SMA,
  and eccentricity** in the orbit screen
- **Windows**: `gmat-win-R2026a/` ships in the repo
- **macOS**: `gmat-mac-x64-R2026a-signed.dmg` is downloaded and bundled
  into the `.app` at release time; on first run it's copied to
  `~/Library/Application Support/SpaceMissionGame/gmat` (app bundles
  can't write inside Resources)

### Destinations & trajectory animation

- **8 destinations**: Mercury, Moon, Mars, Venus, Jupiter, Saturn,
  Uranus, Neptune — each with real facts (diameter, day length, moons)
- **Reachability**: launch vehicle payload capacity classes
  (`escape` / `interplanetary` / `deep_space`) gate which planets are
  reachable — outer ice giants need flagship launchers
- **Orbit scoring**: each orbit is scored 0–100 for a destination with
  human-readable reasons (body match, altitude, inclination, period,
  distance)
- **Transfer map** (`src/ui/trajectory_view.py`): the 2D geometry —
  outbound arc → parking orbit → return to Earth — now drawn as the
  Launch screen's minimap. (`TrajectoryCanvas`, the old full-screen
  Flight Path view, is kept in the file but no longer used.)
- **3D mission view** (Launch screen): a pure-Python canvas 3D engine
  (`src/ui/spacecraft_view.py`) flies Tharun's Rocket — strap-on boosters
  that separate, unfolding solar arrays, an opening comms dish — to a
  procedurally textured destination sized by its real diameter
  (`src/ui/planet_render.py`) — launching from a 3D Earth, slipping into
  orbit, flying three laps, then arcing home and landing back on Earth.
  Paths are smooth cubic curves, and the 3D view and 2D map share one
  flight timeline so they stay in step. It follows the simulation phases live,
  shows the approach vector, range and real orbital speed (√(GM/r)), and
  pins a 2D transfer minimap in the corner. Drag to orbit the camera.
  Preview the rocket alone with `python -m src.ui.spacecraft_view`.

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

### Gamification

- **Design grade (A–F)** in the telemetry sidebar, updated on every click,
  with a "Next:" tip naming the most important fix (`design_grade()` in
  `src/ui/telemetry.py`)
- **XP & ranks** — Cadet → Pilot → Navigator → Commander → Admiral →
  Legend, stored in `src/game/saves/profile.json` (`src/game/profile.py`).
  XP per flight = 25 + score + 20 per objective + medal bonus; a launch
  failure still earns 10
- **Event cards** — twice per flight the simulation pauses for a tactical
  choice (e.g. burn fuel to dodge micrometeorites vs. accept power dips).
  Choices feed real modifiers into the simulation, which re-runs with the
  same seed so only your decision changes the outcome
  (`src/game/flight_events.py`)
- **Medals** — gold (all objectives + score ≥ 85), silver (all
  objectives), bronze (some objectives); sandbox medals on score alone
- **Milestone toasts** slide in for lift-off, separation, orbit insertion,
  medals, XP and rank-ups
- **Pilot leaderboard** on the Results screen: every flight you've flown
  (score, objectives, XP gained, medal, rank at the time), ranked by score,
  with lifetime totals — total XP earned, XP to spend, rank, flights,
  medals and best score. Each new flight is added on top of the log.
- **XP shop** (header button, locked items, or Results): premium parts —
  RTG, large solar array, Ka-band comms, precision pointing, high-res
  imager, radar sounder, sample return, GEO and lunar orbits, the heavy
  launcher — are locked until bought with XP (`src/game/shop.py`). The
  starter kit still completes every scenario. Spending XP never lowers
  your rank: rank follows lifetime XP, the shop spends a separate balance.

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
    screens/               # One module per wizard step: welcome, bus &
                           #   payload, orbit & launch, planet facts,
                           #   review, launch (+ launch_viewport.py, the
                           #   3D mission view) and results
    trajectory_view.py     # 2D animated trajectory canvas
    spacecraft_view.py     # Canvas 3D engine + Tharun's Rocket model
    planet_render.py       # Procedural planet textures, sizes, rings
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

```bashthyackageson c`mn            # G
(`cusdfmuk)nr`,`ddetemr`,.`piilnw` # Cons ```
  on Windowson
macOS the release `.app` bundles GMAT automatcally. IGMAT 
 Requires Python 3.13+, `customtkinter` and `pillow` (GUI mode only —

## Tpch stack

- **Langpagn**:tall -r requir(stemeardnlibrarytonly for gtme logi`)
- **GUI**: [CustomT;intir](httpt://github.com/TomSchimansky/CustomTkinter)
h 6.0 on Tkouter,twith  daPkditect` fow th th awareeess
- **Imaging**: Pillow (op ional — planet artwork fallp back ao
  coloured shapes wiehout it) artwork
- **Astrodynamics**: GMAT R2026a faGmatConsole`, headless slript mode)
- **Rendering**: plre-stdlib ` k.Canvas` — nb gaae engine or GPU deps
- **Packag ng**: PyItsoall co(uSraceMissesnGame.specap → `eexe` on
sMWATdows, `.app` + `.dm` on mcOS
- **CI/CD**: GitHub Acs(`.github/flows/release.yml`) — build
 bth plaformsn `v*`ags and publisstGHub Releases

## Releasts

Prshiag a `v*w tao sruggers the releeseoworkxlow, which pr iucts:

- **Wbndowd**:l`SpaceMd `gomGame.exn`-(sinRle-fil26PyInst/l`er buid)
- **molOS**: `SpaceMisifonGame.d g` (api bundte w'th GMAT  ncludmi;
 sad-hsc signed — iggh,-ctick → Open onhfirsg launch)e falls back to simplified orbital
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
