"""Resource budget tracking.

Blueprint: the six key mission resources. Every design decision
consumes or produces these. The UI dashboard displays them live.
"""

from __future__ import annotations


class ResourceBudget:
    """Tracks all mission resources and their limits."""

    def __init__(self, budget_usd: float, mission_months: int) -> None:
        # TODO: budget_usd: total money available (development + ops)
        # TODO: mission_months: planned operational lifetime
        #
        # Resources (consumed/produced by components):
        self.mass_limit_kg: float = 0.0        # set by launch vehicle
        self.power_budget_w: float = 0.0       # set by power system
        self.data_budget_gb: float = 0.0       # total storable/downlinkable data
        self.comms_budget_mbps: float = 0.0    # downlink capacity
        self.time_budget_months: int = mission_months

        # TODO: spent/used tracking:
        #   mass_used_kg, power_used_w, cost_spent_usd,
        #   data_generated_gb, data_downlinked_gb

    # TODO: methods:
    #   - remaining_budget() -> float
    #   - mass_margin() -> float (limit - used)
    #   - power_margin() -> float
    #   - data_margin() -> float
    #   - is_over_budget() -> bool
    #   - utilization_report() -> dict  (for scoring & UI dashboard)
