"""Scoring and evaluation engine.

Blueprint: converts a MissionResult into a final score and a
human-readable mission report explaining WHY the mission succeeded
or failed — the key educational feedback loop.
"""

from __future__ import annotations

# TODO: from src.game.simulation import MissionResult


class ScoreEngine:
    """Computes mission score from simulation results."""

    # TODO: scoring weights (tunable):
    #   SCIENCE_WEIGHT = 0.40
    #   OBJECTIVE_WEIGHT = 0.25
    #   RESOURCE_EFFICIENCY_WEIGHT = 0.15
    #   RELIABILITY_WEIGHT = 0.10
    #   INNOVATION_WEIGHT = 0.10   (creative/unusual but valid designs)

    def score(self, result: "MissionResult") -> float:
        """Return a 0-100 mission score."""
        # TODO: science_return component
        # TODO: objectives_met fraction
        # TODO: resource efficiency (unused margin = bonus, overruns = penalty)
        # TODO: reliability (launch success, few anomalies)
        # TODO: combine with weights -> final score
        raise NotImplementedError

    def generate_report(self, result: "MissionResult") -> str:
        """Produce a post-mission analysis report.

        Should explain, in plain language:
          - which objectives were met and why
          - which constraints were tight or violated
          - what the best/worst decisions were
          - suggestions for improvement ("try a lighter instrument",
            "your data volume exceeded downlink by 3x — add a relay
            or reduce imaging cadence")
        """
        # TODO: template-based report generation
        # TODO: include per-decision feedback (educational value)
        raise NotImplementedError


# TODO: Leaderboard — save scores to local file / JSON,
#       support comparing mission designs and sharing results.
