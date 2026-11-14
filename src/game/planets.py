"""Destination planet catalog and orbit scoring.

Planets have real-ish facts for the post-selection display, and each
orbit gets scored for suitability to reach/observe a destination.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Planet:
    id: str
    name: str
    distance_au: float          # distance from Sun in AU (for trajectory scaling)
    distance_label: str         # human-friendly distance from Earth
    diameter_km: float
    day_hours: float
    moons: int
    color: str                  # hex color for canvas
    radius_px: int
    facts: list[str] = field(default_factory=list)
    reach_key: str = "interplanetary"  # launch vehicle capacity class needed
    distance_from_earth_km: float = 0.0  # same figure as distance_label; drives budget


# Destination catalog. Earth is the origin (not a destination).
PLANETS: dict[str, Planet] = {
    "mercury": Planet(
        id="mercury", distance_from_earth_km=82000000.0, name="Mercury", distance_au=0.39,
        distance_label="~82 million km from Earth (at closest)",
        diameter_km=4879, day_hours=4222.6, moons=0,
        color="#A8A29E", radius_px=9, reach_key="interplanetary",
        facts=[
            "Mercury is the smallest planet in the solar system.",
            "A single day on Mercury lasts ~59 Earth days.",
            "Despite being closest to the Sun, Venus is hotter.",
        ]),
    "moon": Planet(
        id="moon", distance_from_earth_km=384400, name="Moon", distance_au=0.0026,
        distance_label="~384,400 km from Earth",
        diameter_km=3474, day_hours=708, moons=0,
        color="#C0C0C0", radius_px=14, reach_key="escape",
        facts=[
            "The Moon is Earth's only natural satellite.",
            "A day on the Moon lasts ~29.5 Earth days.",
            "Apollo astronauts left the last footprints there in 1972.",
        ]),
    "mars": Planet(
        id="mars", distance_from_earth_km=225000000.0, name="Mars", distance_au=1.52,
        distance_label="~225 million km from Earth (at closest)",
        diameter_km=6779, day_hours=24.6, moons=2,
        color="#D1603D", radius_px=12, reach_key="interplanetary",
        facts=[
            "Mars has the tallest volcano in the solar system: Olympus Mons.",
            "A day on Mars is only ~37 minutes longer than an Earth day.",
            "Mars has two small moons: Phobos and Deimos.",
        ]),
    "venus": Planet(
        id="venus", distance_from_earth_km=41000000.0, name="Venus", distance_au=0.72,
        distance_label="~41 million km from Earth (at closest)",
        diameter_km=12104, day_hours=5832, moons=0,
        color="#E8C47A", radius_px=16, reach_key="interplanetary",
        facts=[
            "Venus spins backwards compared to most planets.",
            "Its surface is hot enough to melt lead (~465°C).",
            "A day on Venus is longer than its year.",
        ]),
    "jupiter": Planet(
        id="jupiter", distance_from_earth_km=588000000.0, name="Jupiter", distance_au=5.2,
        distance_label="~588 million km from Earth (at closest)",
        diameter_km=139820, day_hours=9.9, moons=95,
        color="#D8A56C", radius_px=22, reach_key="interplanetary",
        facts=[
            "Jupiter is more massive than all other planets combined.",
            "The Great Red Spot is a storm larger than Earth.",
            "Jupiter has at least 95 confirmed moons.",
        ]),
    "saturn": Planet(
        id="saturn", distance_from_earth_km=1200000000.0, name="Saturn", distance_au=9.58,
        distance_label="~1.2 billion km from Earth (at closest)",
        diameter_km=116460, day_hours=10.7, moons=274,
        color="#E3C98F", radius_px=24, reach_key="interplanetary",
        facts=[
            "Saturn's rings are made of billions of ice and rock particles.",
            "Saturn is less dense than water — it would float in a big enough ocean.",
            "Saturn has more confirmed moons than any other planet.",
        ]),
    "uranus": Planet(
        id="uranus", distance_from_earth_km=2600000000.0, name="Uranus", distance_au=19.2,
        distance_label="~2.6 billion km from Earth (at closest)",
        diameter_km=50724, day_hours=17.2, moons=28,
        color="#9ADBE8", radius_px=17, reach_key="deep_space",
        facts=[
            "Uranus spins on its side — its axis is tilted ~98 degrees.",
            "It is an ice giant with a blue-green methane atmosphere.",
            "A year on Uranus lasts ~84 Earth years.",
        ]),
    "neptune": Planet(
        id="neptune", distance_from_earth_km=4300000000.0, name="Neptune", distance_au=30.1,
        distance_label="~4.3 billion km from Earth (at closest)",
        diameter_km=49244, day_hours=16.1, moons=16,
        color="#4A6FD8", radius_px=17, reach_key="deep_space",
        facts=[
            "Neptune has the fastest winds in the solar system (~2,100 km/h).",
            "It was discovered through mathematical prediction before telescopes saw it.",
            "Neptune's largest moon, Triton, orbits backwards.",
        ]),
}

# Earth — the departure point
EARTH = Planet(
    id="earth", name="Earth", distance_au=1.0,
    distance_label="Home", diameter_km=12742, day_hours=24, moons=1,
    color="#4A90D9", radius_px=14,
    facts=["Earth is the only known planet with life."])


# --------------------------------------------------------------------------
# Mission budget scales with distance from Earth
# --------------------------------------------------------------------------
MIN_BUDGET_USD = 200e6    # the nearest destination (the Moon)
MAX_BUDGET_USD = 7.1e9    # the farthest destination (Neptune)


def budget_for(planet: Planet | None) -> float:
    """Mission budget for a destination: $200M for the nearest world rising
    in a straight line with distance from Earth to $7.1B for the farthest. With
    no destination chosen yet, the minimum applies."""
    if planet is None:
        return MIN_BUDGET_USD
    distances = [p.distance_from_earth_km for p in PLANETS.values()]
    near, far = min(distances), max(distances)
    t = (planet.distance_from_earth_km - near) / (far - near) if far > near else 0.0
    t = max(0.0, min(1.0, t))
    return MIN_BUDGET_USD + t * (MAX_BUDGET_USD - MIN_BUDGET_USD)


def reachable_planets(launch_vehicle) -> list[Planet]:
    """Planets this launch vehicle can reach, given its capacity classes."""
    if launch_vehicle is None:
        return []
    caps = launch_vehicle.payload_capacity_kg
    out = []
    for p in PLANETS.values():
        if p.reach_key in caps:
            out.append(p)
        elif p.reach_key == "interplanetary" and "escape" in caps:
            # Escape-velocity vehicles can reach interplanetary destinations
            out.append(p)
        elif p.reach_key == "deep_space" and "interplanetary" in caps:
            # Only flagship launchers reach the outer ice giants
            out.append(p)
    return out


def score_orbit_for(orbit, dest: Planet) -> tuple[float, list[str]]:
    """Score an orbit 0-100 for a destination mission. Returns (score, reasons)."""
    score = 100.0
    reasons: list[str] = []

    # Orbit body should match the destination (or be a transfer orbit)
    if orbit.body.lower() != dest.name.lower() and dest.id != "moon":
        if orbit.body == "Deep Space":
            score -= 10
            reasons.append("Deep-space orbit: long cruise, limited coverage of target")
        else:
            score -= 35
            reasons.append(f"Orbit is around {orbit.body}, not {dest.name} — "
                           "you'd need a transfer burn to get there")
    elif orbit.body.lower() == dest.name.lower():
        score += 0  # matched
        reasons.append(f"Orbit matches destination ({dest.name})")

    # Altitude effects
    if orbit.altitude_km < 500:
        score -= 10
        reasons.append("Low altitude: atmospheric drag shortens mission lifetime")
    elif orbit.altitude_km > 30000:
        score -= 15
        reasons.append("Very high orbit: weak coverage and long communication delays")

    # Inclination / coverage
    if orbit.inclination_deg > 90:
        score += 5
        reasons.append("Polar orbit: excellent global coverage")

    # Period affects comms windows
    if orbit.period_hours > 12:
        score -= 10
        reasons.append("Long orbital period: fewer communication passes per day")

    # Distance penalty for comms delay (applies to any orbit used for the mission)
    if dest.distance_au > 2:
        score -= 15
        reasons.append(f"{dest.name} is far away — communication delay and "
                       "light-time affect operations")

    return max(0.0, min(100.0, score)), reasons
