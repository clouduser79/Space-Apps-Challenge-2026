"""Launch vehicles catalog.

Launch vehicles have payload capacity (to specific orbit classes),
cost, and reliability. Compatibility check: spacecraft mass + orbit
determine whether a vehicle can fly the mission.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .orbit import Orbit  # read-only use of the Orbit data holder

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Map an Orbit to the payload-capacity class used in the JSON catalog.
_ORBIT_CLASS_RULES = [
    # (predicate, capacity_key) — first match wins
    (lambda o: o.body != "Earth", "interplanetary"),
    (lambda o: o.body == "Moon", "escape"),
    (lambda o: o.name.lower().startswith("geostationary"), "GTO"),
    (lambda o: o.altitude_km < 2000, "LEO"),
    (lambda o: True, "LEO"),
]


def orbit_capacity_class(orbit: Orbit) -> str:
    for pred, key in _ORBIT_CLASS_RULES:
        if pred(orbit):
            return key
    return "LEO"


@dataclass
class LaunchVehicle:
    """A rocket that can deliver the spacecraft to an orbit."""

    id: str
    name: str
    cost_usd: float
    payload_capacity_kg: dict[str, float]
    reliability: float          # 0.0-1.0 launch success probability
    description: str

    def capacity_for(self, orbit: Orbit) -> float | None:
        """Payload capacity (kg) to the orbit's class, or None if unsupported."""
        key = orbit_capacity_class(orbit)
        # Try exact class, then fall back through sensible alternates.
        for candidate in (key, "LEO", "escape", "interplanetary"):
            if candidate in self.payload_capacity_kg:
                return self.payload_capacity_kg[candidate]
        return None

    def can_launch(self, spacecraft_mass_kg: float, orbit: Orbit) -> tuple[bool, str]:
        """Check mass/orbit compatibility. Returns (ok, reason)."""
        cap = self.capacity_for(orbit)
        if cap is None:
            return False, f"{self.name} cannot reach {orbit.name}"
        if spacecraft_mass_kg > cap:
            return False, (f"{self.name} can lift {cap:.0f} kg to "
                           f"{orbit_capacity_class(orbit)} but spacecraft "
                           f"is {spacecraft_mass_kg:.0f} kg")
        return True, f"{self.name} can lift {spacecraft_mass_kg:.0f} kg to {orbit.name}"


def load_catalog(path: Path | None = None) -> dict[str, LaunchVehicle]:
    path = path or DATA_DIR / "launch_vehicles.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    catalog = {}
    for entry in raw["launch_vehicles"]:
        lv = LaunchVehicle(
            id=entry["id"],
            name=entry["name"],
            cost_usd=float(entry["cost_usd"]),
            payload_capacity_kg={k: float(v) for k, v in entry["payload_capacity_kg"].items()},
            reliability=float(entry["reliability"]),
            description=entry.get("description", ""),
        )
        catalog[lv.id] = lv
    return catalog


_catalog: dict[str, LaunchVehicle] | None = None


def get_catalog() -> dict[str, LaunchVehicle]:
    global _catalog
    if _catalog is None:
        _catalog = load_catalog()
    return _catalog
