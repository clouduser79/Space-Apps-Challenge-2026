"""Launch vehicles catalog.

Blueprint: launch vehicles have payload capacity (to specific orbits),
cost, and reliability. Compatibility check: spacecraft mass + orbit
determine whether a vehicle can fly the mission.
"""

from __future__ import annotations


class LaunchVehicle:
    """A rocket that can deliver the spacecraft to an orbit."""

    def __init__(self, name: str, cost_usd: float,
                 payload_capacity_kg: dict[str, float],
                 reliability: float, description: str) -> None:
        self.name = name
        self.cost_usd = cost_usd
        # payload_capacity_kg: {orbit_type: max_kg}, e.g.
        #   {"LEO": 22000, "GTO": 8000, "escape": 4000}
        self.payload_capacity_kg = payload_capacity_kg
        self.reliability = reliability  # 0.0-1.0, affects launch success chance
        self.description = description
        # TODO: add fields: fairing_size, launch_sites, availability_years

    def can_launch(self, spacecraft_mass_kg: float, orbit: "Orbit") -> bool:
        """Check whether this vehicle can lift the spacecraft to the orbit."""
        # TODO: map orbit -> capacity class (LEO/GTO/escape/interplanetary)
        # TODO: return spacecraft_mass_kg <= capacity for that class
        raise NotImplementedError


# TODO: LAUNCH_VEHICLE_CATALOG — e.g.:
#   - Small launcher (e.g., Electron-class): cheap, ~300 kg to LEO
#   - Medium launcher (e.g., Falcon 9-class): ~$60M, ~22 t to LEO
#   - Heavy launcher (e.g., SLS/Starship-class): expensive, interplanetary
#   - Manned-rated vehicle (crew missions only)
#
# TODO: load from src/data/launch_vehicles.json
