"""Core mission model.

Blueprint: represents a complete mission from concept to operation.
Holds mission objective, spacecraft, orbit, launch vehicle, resources,
and mission phase (design -> simulation -> evaluation).
"""

from __future__ import annotations

# TODO: import dataclasses / typing
# TODO: import spacecraft, orbit, launch vehicle, instrument modules


class MissionPhase:
    """Enum-like constants for mission lifecycle stages."""
    # TODO: define phases: OBJECTIVE, SPACECRAFT, INSTRUMENTS,
    #       ORBIT, LAUNCH, SIMULATION, EVALUATION
    pass


class Mission:
    """A complete space mission design."""

    def __init__(self, name: str, objective: str) -> None:
        self.name = name
        self.objective = objective
        # TODO: mission requirements derived from objective
        #       (e.g., "image Mars surface" -> needs imaging instrument,
        #        Mars orbit, comms delay tolerance, etc.)
        self.phase = MissionPhase.OBJECTIVE

        # TODO: spacecraft = Spacecraft()
        # TODO: orbit = Orbit()
        # TODO: launch_vehicle = LaunchVehicle()
        # TODO: resources = ResourceBudget()  (mass, power, budget, data, comms, time)
        # TODO: players: list[Player] (1-4)

    # --- Design phase methods ---
    def set_objective(self, objective: str) -> None:
        """Define the mission objective and derive requirements."""
        # TODO: store objective
        # TODO: generate mission requirements checklist
        # TODO: advance phase
        raise NotImplementedError

    def validate_design(self) -> list[str]:
        """Check the whole design for constraint violations.

        Returns a list of human-readable warnings/errors, e.g.:
          - "Spacecraft mass (450 kg) exceeds launch vehicle capacity (300 kg)"
          - "Power demand (800 W) exceeds available power (600 W)"
          - "Data volume exceeds downlink capacity over mission lifetime"
        """
        # TODO: check mass vs launch vehicle payload capacity
        # TODO: check power budget (generation vs consumption)
        # TODO: check data volume vs comms capacity
        # TODO: check budget totals
        # TODO: check orbit/launch vehicle compatibility
        raise NotImplementedError

    def simulate(self) -> "MissionResult":
        """Run the mission simulation and return results."""
        # TODO: step through mission timeline (launch, cruise, ops)
        # TODO: apply random events / anomalies
        # TODO: compute science return, resource usage, success metrics
        raise NotImplementedError
