"""Resource budget tracking.

The six key mission resources. Every design decision consumes or
produces these. The dashboard displays them live.
"""

from __future__ import annotations


def _usd(amount: float) -> str:
    """$51.0M / $4.0B / $1.2T — budgets now span millions to trillions."""
    for scale, unit in ((1e12, "T"), (1e9, "B")):
        if abs(amount) >= scale:
            return f"${amount / scale:.1f}{unit}"
    return f"${amount / 1e6:.1f}M"


class ResourceBudget:
    """Tracks mission resource limits and consumption."""

    def __init__(self, budget_usd: float, mission_months: int) -> None:
        self.budget_limit_usd = budget_usd
        self.cost_spent_usd = 0.0

        self.mass_limit_kg = 0.0        # set once launch vehicle is chosen
        self.mass_used_kg = 0.0

        self.power_limit_w = 0.0        # set by power system
        self.power_used_w = 0.0

        self.data_limit_gb = 0.0        # onboard storage (simplified)
        self.data_generated_gb = 0.0
        self.data_downlinked_gb = 0.0

        self.comms_limit_mbps = 0.0     # downlink capacity
        self.time_limit_months = mission_months
        self.time_used_months = 0.0

    # --- setters used during design ---
    def set_mass_limit(self, kg: float) -> None:
        self.mass_limit_kg = kg

    def set_power_limit(self, w: float) -> None:
        self.power_limit_w = w

    def set_comms_limit(self, mbps: float) -> None:
        self.comms_limit_mbps = mbps

    def set_data_limit(self, gb: float) -> None:
        self.data_limit_gb = gb

    # --- margins (positive = healthy) ---
    @property
    def budget_remaining_usd(self) -> float:
        return self.budget_limit_usd - self.cost_spent_usd

    @property
    def mass_margin_kg(self) -> float:
        return self.mass_limit_kg - self.mass_used_kg if self.mass_limit_kg else 0.0

    @property
    def power_margin_w(self) -> float:
        return self.power_limit_w - self.power_used_w if self.power_limit_w else 0.0

    @property
    def data_backlog_gb(self) -> float:
        return self.data_generated_gb - self.data_downlinked_gb

    @property
    def time_remaining_months(self) -> float:
        return self.time_limit_months - self.time_used_months

    def violations(self) -> list[str]:
        """Hard constraint violations (empty list = feasible design).

        Includes threshold crossings: margins under ~10-15% or any
        resource at/over its limit force the player to change components.
        """
        v = []
        if self.cost_spent_usd > self.budget_limit_usd:
            v.append(f"Budget exceeded by {_usd(self.cost_spent_usd - self.budget_limit_usd)}")
        elif (self.budget_limit_usd
              and self.budget_remaining_usd < self.budget_limit_usd * 0.10):
            v.append("Budget margin under 10% — choose cheaper components")
        if self.mass_limit_kg and self.mass_used_kg > self.mass_limit_kg:
            v.append(f"Mass exceeded by {self.mass_used_kg - self.mass_limit_kg:.0f} kg")
        elif (self.mass_limit_kg
              and 0 < self.mass_margin_kg < self.mass_limit_kg * 0.10):
            v.append("Mass margin under 10% — remove or shrink components")
        if self.power_limit_w and self.power_used_w > self.power_limit_w:
            v.append(f"Power exceeded by {self.power_used_w - self.power_limit_w:.0f} W")
        elif (self.power_limit_w
              and 0 < self.power_margin_w < self.power_limit_w * 0.15):
            v.append("Power margin under 15% — add generation or cut loads")
        if self.time_limit_months and self.time_used_months >= self.time_limit_months:
            v.append("Mission time limit reached — shorten the mission")
        if self.data_limit_gb and self.data_backlog_gb > self.data_limit_gb:
            v.append(f"Data backlog {self.data_backlog_gb:.0f} GB exceeds storage "
                     f"{self.data_limit_gb:.0f} GB — add downlink or storage")
        return v

    def warnings(self) -> list[str]:
        """Soft warnings — feasible but risky/tight."""
        w = []
        if self.comms_limit_mbps and self.data_rate_check_needed():
            w.append("Data generation may exceed downlink capacity")
        return w

    def data_rate_check_needed(self) -> bool:
        return False  # refined during simulation

    def dashboard(self) -> str:
        """Real-time resource display for the CLI dashboard."""
        lines = [
            "=== RESOURCE DASHBOARD ===",
            f"Budget:   {_usd(self.cost_spent_usd):>8} spent / "
            f"{_usd(self.budget_limit_usd)}  "
            f"(remaining {_usd(self.budget_remaining_usd)})",
            f"Mass:     {self.mass_used_kg:7.0f} kg / "
            f"{self.mass_limit_kg if self.mass_limit_kg else '?':>7} kg",
            f"Power:    {self.power_used_w:7.0f} W / "
            f"{self.power_limit_w if self.power_limit_w else '?':>7} W",
            f"Comms:    {self.comms_limit_mbps:7.0f} Mbps downlink",
            f"Data:     {self.data_generated_gb:7.1f} GB generated / "
            f"{self.data_downlinked_gb:.1f} GB downlinked",
            f"Time:     {self.time_used_months:7.1f} / "
            f"{self.time_limit_months} months",
        ]
        return "\n".join(lines)
