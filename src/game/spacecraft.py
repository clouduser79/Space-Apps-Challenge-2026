"""Spacecraft model.

Spacecraft = bus (structure, power, comms, avionics, ADCS)
           + payload (scientific instruments).
Every component has mass, power draw, cost, and optional data rate.
Adding any component has real consequences on all resource budgets.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .instruments import Instrument


@dataclass
class Component:
    """A bus component (non-instrument part of the spacecraft)."""

    id: str
    name: str
    mass_kg: float
    power_w: float          # positive = consumes power
    cost_usd: float
    power_gen_w: float = 0.0   # positive = generates power (solar arrays, RTG)
    comms_mbps: float = 0.0    # downlink capacity contributed
    description: str = ""

    def impact_summary(self) -> str:
        gen = f", +{self.power_gen_w:g} W gen" if self.power_gen_w else ""
        comms = f", {self.comms_mbps:g} Mbps downlink" if self.comms_mbps else ""
        return (f"{self.name}: +{self.mass_kg:g} kg, "
                f"{'-' if self.power_w else '+'}{abs(self.power_w):g} W{gen}, "
                f"+${self.cost_usd / 1e6:.1f}M{comms}")


# Bus component catalog — the "realistic or simplified spacecraft model".
# Power draw is negative-generation convention handled via power_w sign;
# power_gen_w is separate for clarity.
BUS_COMPONENTS: dict[str, Component] = {
    "structure_small": Component(
        "structure_small", "Compact Structure", 80, 0, 5_000_000,
        description="Minimal bus for CubeSat-class missions."),
    "structure_standard": Component(
        "structure_standard", "Standard Structure", 250, 0, 20_000_000,
        description="Typical science spacecraft bus."),
    "structure_heavy": Component(
        "structure_heavy", "Heavy Structure", 800, 0, 80_000_000,
        description="Flagship-class bus for large payloads."),
    "solar_small": Component(
        "solar_small", "Small Solar Array", 15, 0, 2_000_000,
        power_gen_w=100, description="Enough for low-power payloads in LEO."),
    "solar_standard": Component(
        "solar_standard", "Standard Solar Array", 60, 0, 8_000_000,
        power_gen_w=500, description="Supports most instrument suites."),
    "solar_large": Component(
        "solar_large", "Large Solar Array", 200, 0, 25_000_000,
        power_gen_w=2000, description="For power-hungry instruments."),
    "rtg": Component(
        "rtg", "Radioisotope Generator", 45, 0, 60_000_000,
        power_gen_w=300, description="Nuclear power for deep space / eclipse-heavy orbits."),
    "avionics": Component(
        "avionics", "Onboard Computer", 12, 25, 4_000_000,
        description="Command & data handling."),
    "adcs_basic": Component(
        "adcs_basic", "Basic Attitude Control", 8, 15, 3_000_000,
        description="Nadir pointing only."),
    "adcs_precise": Component(
        "adcs_precise", "Precision Attitude Control", 20, 40, 12_000_000,
        description="Arcsecond pointing for high-res imaging."),
    "comms_basic": Component(
        "comms_basic", "Basic Comms (X-band)", 10, 20, 3_000_000,
        comms_mbps=10, description="Low-rate downlink."),
    "comms_high": Component(
        "comms_high", "High-Rate Comms (Ka-band)", 25, 50, 15_000_000,
        comms_mbps=100, description="Fast downlink for data-heavy missions."),
    "propulsion_basic": Component(
        "propulsion_basic", "Basic Propulsion", 30, 5, 8_000_000,
        description="Orbit maintenance & simple maneuvers."),
    "propulsion_advanced": Component(
        "propulsion_advanced", "Advanced Propulsion", 120, 10, 40_000_000,
        description="Required for large orbit changes / deep space."),
}


class Spacecraft:
    """The player's spacecraft: bus components + payload instruments."""

    def __init__(self) -> None:
        self.bus: list[Component] = []
        self.payload: list[Instrument] = []

    # --- mutation ---
    def add_bus(self, component: Component) -> None:
        self.bus.append(component)

    def remove_bus(self, component_id: str) -> bool:
        for i, c in enumerate(self.bus):
            if c.id == component_id:
                del self.bus[i]
                return True
        return False

    def add_instrument(self, instrument: Instrument) -> None:
        self.payload.append(instrument)

    def remove_instrument(self, instrument_id: str) -> bool:
        for i, inst in enumerate(self.payload):
            if inst.id == instrument_id:
                del self.payload[i]
                return True
        return False

    # --- computed totals (the consequence engine) ---
    @property
    def total_mass_kg(self) -> float:
        return sum(c.mass_kg for c in self.bus) + sum(i.mass_kg for i in self.payload)

    @property
    def power_generated_w(self) -> float:
        return sum(c.power_gen_w for c in self.bus)

    @property
    def power_consumed_w(self) -> float:
        return (sum(c.power_w for c in self.bus)
                + sum(i.power_w for i in self.payload))

    @property
    def power_margin_w(self) -> float:
        return self.power_generated_w - self.power_consumed_w

    @property
    def total_cost_usd(self) -> float:
        return (sum(c.cost_usd for c in self.bus)
                + sum(i.cost_usd for i in self.payload))

    @property
    def comms_mbps(self) -> float:
        return sum(c.comms_mbps for c in self.bus)

    @property
    def data_rate_mbps(self) -> float:
        """Science data generation rate across all instruments."""
        return sum(i.data_rate_mbps for i in self.payload)

    @property
    def science_value(self) -> float:
        return sum(i.science_value for i in self.payload)

    @property
    def capabilities(self) -> set[str]:
        """Set of capability tags provided by the payload."""
        tags: set[str] = set()
        for inst in self.payload:
            tags.update(inst.tags)
        return tags

    def summary(self) -> str:
        return (f"Mass: {self.total_mass_kg:.0f} kg | "
                f"Power: {self.power_consumed_w:.0f}W used / "
                f"{self.power_generated_w:.0f}W gen | "
                f"Cost: ${self.total_cost_usd / 1e6:.1f}M | "
                f"Downlink: {self.comms_mbps:g} Mbps | "
                f"Data gen: {self.data_rate_mbps:g} Mbps | "
                f"Science: {self.science_value:.0f}")

    def missing_essentials(self) -> list[str]:
        """Bus systems every spacecraft needs to function."""
        missing = []
        if not any(c.power_gen_w > 0 for c in self.bus):
            missing.append("power generation (solar array or RTG)")
        if not any(c.comms_mbps > 0 for c in self.bus):
            missing.append("communications subsystem")
        if not any(c.id.startswith("adcs") for c in self.bus):
            missing.append("attitude control")
        if not any(c.id.startswith("avionics") for c in self.bus):
            missing.append("onboard computer")
        return missing
