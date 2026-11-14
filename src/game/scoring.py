"""Scoring and evaluation engine.

Converts a MissionResult into a final score and a human-readable
mission report explaining WHY the mission succeeded or failed —
the key educational feedback loop.
"""

from __future__ import annotations

from .simulation import MissionResult


class ScoreEngine:
    """Computes mission score from simulation results."""

    SCIENCE_WEIGHT = 0.40
    OBJECTIVE_WEIGHT = 0.25
    EFFICIENCY_WEIGHT = 0.15
    RELIABILITY_WEIGHT = 0.10
    INNOVATION_WEIGHT = 0.10

    def score(self, result: MissionResult) -> float:
        """Return a 0-100 mission score."""
        if not result.launch_success:
            return 5.0  # participation credit only

        # Science component (cap at 100)
        science_score = min(100.0, result.science_return)

        # Objective component
        total_objs = len(result.objectives_met) + len(result.objectives_failed)
        objective_score = (len(result.objectives_met) / total_objs * 100) if total_objs else 70.0

        # Efficiency: reward unused budget/mass margins, penalize backlog
        efficiency = 100.0
        if result.data_backlog_gb > 500:
            efficiency -= min(40.0, result.data_backlog_gb / 100)
        if result.data_backlog_gb < 50:
            efficiency += 10.0  # bonus for right-sizing data
        efficiency = max(0.0, min(100.0, efficiency))

        # Reliability: fewer anomalies = better
        reliability = max(0.0, 100.0 - len(result.events_triggered) * 8.0)

        # Innovation: unique instrument combos get a small bonus
        innovation = 60.0  # baseline; UI can override

        breakdown = {
            "science": science_score,
            "objectives": objective_score,
            "efficiency": efficiency,
            "reliability": reliability,
            "innovation": innovation,
        }
        result.score_breakdown = breakdown

        final = (
            science_score * self.SCIENCE_WEIGHT
            + objective_score * self.OBJECTIVE_WEIGHT
            + efficiency * self.EFFICIENCY_WEIGHT
            + reliability * self.RELIABILITY_WEIGHT
            + innovation * self.INNOVATION_WEIGHT
        )
        return round(final, 1)

    def generate_report(self, result: MissionResult) -> str:
        """Produce a post-mission analysis report in plain language."""
        lines = [
            "=" * 60,
            f"MISSION REPORT: {result.mission_name}",
            "=" * 60,
            "",
        ]

        if not result.launch_success:
            lines += [
                "OUTCOME: LAUNCH FAILURE",
                "",
                result.failure_reason or "The launch vehicle failed.",
                "",
                "TIP: Review launch vehicle reliability vs. cost trade-off.",
                "A cheaper rocket may save budget but risks losing everything.",
            ]
            return "\n".join(lines)

        status = "SUCCESS" if result.success else "PARTIAL SUCCESS"
        lines += [
            f"OUTCOME: {status}",
            f"Science return: {result.science_return:.0f}",
            f"Months operated: {result.months_operated:.0f}",
            f"Data: {result.data_generated_gb:.0f} GB generated, "
            f"{result.data_downlinked_gb:.0f} GB downlinked "
            f"({result.data_backlog_gb:.0f} GB backlog)",
            "",
            "OBJECTIVES:",
        ]
        for obj in result.objectives_met:
            lines.append(f"  [PASS] {obj.replace('_', ' ')}")
        for obj in result.objectives_failed:
            lines.append(f"  [FAIL] {obj.replace('_', ' ')}")

        lines += ["", "ANOMALIES:"]
        if result.events_triggered:
            for ev in result.events_triggered:
                lines.append(f"  - {ev}")
        else:
            lines.append("  None — clean mission.")

        lines += ["", "SCORE BREAKDOWN:"]
        for k, v in result.score_breakdown.items():
            lines.append(f"  {k.capitalize():12s} {v:5.1f}")

        # --- Educational feedback ---
        lines += ["", "ENGINEERING FEEDBACK:"]
        lines.extend(self._feedback(result))

        return "\n".join(lines)

    def _feedback(self, result: MissionResult) -> list[str]:
        tips = []
        if result.data_backlog_gb > 1000:
            tips.append("Your instruments generate far more data than your "
                        "comms can downlink. Either add a high-rate comms "
                        "system, reduce instrument count, or accept science loss.")
        elif result.data_backlog_gb < 50 and result.science_return > 80:
            tips.append("Good data management — your downlink capacity "
                        "well matches your data generation.")
        if result.objectives_failed:
            tips.append("Failed objectives usually mean missing instrument "
                        "capabilities. Check the required capabilities list "
                        "before finalizing your payload.")
        if len(result.events_triggered) > 3:
            tips.append("Many anomalies occurred. Consider redundancy in "
                        "critical systems or a more reliable bus.")
        if result.science_return > 150:
            tips.append("Exceptional science return! Your instrument suite "
                        "was well-matched to the mission objective.")
        if not tips:
            tips.append("Solid mission. Try adjusting instrument mix or "
                        "orbit to explore different trade-offs.")
        return tips
