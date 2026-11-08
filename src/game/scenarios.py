"""Mission scenarios and difficulty levels.

Blueprint: predefined mission types with different objectives,
budgets, and constraints. Difficulty scales budget tightness,
allowed component tiers, and random event frequency.
"""

from __future__ import annotations


class Scenario:
    """A mission scenario the player can attempt."""

    def __init__(self, name: str, description: str,
                 objective: str, budget_usd: float,
                 mission_months: int, difficulty: str) -> None:
        self.name = name
        self.description = description
        self.objective = objective
        self.budget_usd = budget_usd
        self.mission_months = mission_months
        # difficulty: "cadet" | "engineer" | "expert"
        self.difficulty = difficulty
        # TODO: required_objectives: list[str]  (checklist for scoring)
        # TODO: allowed_orbits: list[str] or None (all)
        # TODO: allowed_instruments: list[str] or None (all)
        # TODO: event_frequency_multiplier: float
        # TODO: sandbox_mode: bool (no constraints, pure experimentation)


# TODO: SCENARIOS — e.g.:
#   1. "Earth Observation" — image a region weekly for 2 years,
#      low budget, LEO/SSO only.
#   2. "Mars Reconnaissance" — high-res imaging + spectroscopy of Mars,
#      tight mass budget, interplanetary launch.
#   3. "Lunar Resource Survey" — radar + neutron spectrometer,
#      crewed-rated comms delay handling.
#   4. "Deep Space Weather Monitor" — L1 orbit, long lifetime,
#      radiation-hardened components required.
#   5. "Sample Return" — flagship mission, huge budget, complex ops.
#   6. "Sandbox" — no constraints, experiment freely.
#
# TODO: load from src/data/scenarios.json
