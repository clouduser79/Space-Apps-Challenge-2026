"""Mission simulation engine.

Blueprint: steps through the mission timeline (launch -> cruise ->
operations -> end of life), applying physics-lite models, random
events, and resource consumption. Produces a MissionResult.
"""

from __future__ import annotations

# TODO: import random, math
# TODO: from src.game.mission import Mission


class RandomEvent:
    """An unexpected mission event (good or bad)."""

    def __init__(self, name: str, probability: float,
                 effect_description: str) -> None:
        self.name = name
        self.probability = probability
        # TODO: effect: callable or dict describing impact on resources/science
        # Examples:
        #   - "Micrometeorite strike": -5% instrument health
        #   - "Solar flare": -20% power for 3 days, radiation damage risk
        #   - "Ground station outage": data backlog grows
        #   - "Propellant leak": mission lifetime shortened
        #   - "Bonus science window": +10% science return


class MissionSimulator:
    """Runs a mission design through its lifecycle."""

    def __init__(self, mission: "Mission", seed: int | None = None) -> None:
        self.mission = mission
        # TODO: self.rng = random.Random(seed)  # seedable for reproducibility
        # TODO: self.timeline = build timeline from orbit transfer + ops duration
        # TODO: self.events = load random events table

    def run(self) -> "MissionResult":
        """Execute the full simulation."""
        # TODO: Phase 1 — Launch:
        #   - roll launch vehicle reliability -> success/failure
        #   - on failure: mission ends, partial credit for design quality
        # TODO: Phase 2 — Cruise / orbit insertion:
        #   - check propellant / delta-v budget (TODO: add propulsion model)
        #   - apply cruise duration based on orbit type
        # TODO: Phase 3 — Operations:
        #   - monthly loop: science accumulation, data generation,
        #     downlink passes, power balance (eclipse vs sunlight),
        #     random events
        #   - instrument degradation over time
        # TODO: Phase 4 — End of life:
        #   - propellant depletion / orbit decay / mission duration cap
        # TODO: return MissionResult(science_return, resources_used,
        #                            events_triggered, success_flags)
        raise NotImplementedError


class MissionResult:
    """Output of a simulation run."""

    def __init__(self) -> None:
        # TODO: fields:
        #   science_return: float (0-100+)
        #   mission_success: bool
        #   objectives_met: list[str] / list[str] (failed objectives)
        #   resources: final ResourceBudget state
        #   events: list of triggered RandomEvents
        #   score_breakdown: dict (for scoring engine)
        pass
