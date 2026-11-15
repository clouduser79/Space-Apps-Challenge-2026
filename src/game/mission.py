"""Core mission model.

Represents a complete mission from concept to operation.
Holds mission objective, scenario requirements, spacecraft, orbit,
launch vehicle, resources, and mission phase.
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from .instruments import Instrument, get_catalog as get_instrument_catalog
from .launch_vehicle import LaunchVehicle, get_catalog as get_lv_catalog
from .orbit import Orbit
from .resources import ResourceBudget
from .scenarios import Scenario
from .spacecraft import Spacecraft

if TYPE_CHECKING:
    from .simulation import MissionResult


class MissionPhase(enum.Enum):
    OBJECTIVE = "Define objective"
    SPACECRAFT = "Design spacecraft"
    PAYLOAD = "Select instruments"
    ORBIT = "Choose orbit"
    LAUNCH = "Select launch vehicle"
    REVIEW = "Review & simulate"
    DONE = "Complete"


class Mission:
    """A complete space mission design."""

    def __init__(self, name: str, scenario: Scenario) -> None:
        self.name = name
        self.scenario = scenario
        self.objective = scenario.objective
        self.phase = MissionPhase.OBJECTIVE

        self.spacecraft = Spacecraft()
        self.orbit: Orbit | None = None
        self.launch_vehicle: LaunchVehicle | None = None
        # Planet from planets.py. Scenario missions derive it from the
        # orbit (see set_orbit); only sandbox players pick it themselves.
        self.destination = None

        self.resources = ResourceBudget(
            budget_usd=self._budget_for(None),
            mission_months=scenario.mission_months,
        )
        self.players: list = []  # populated by game loop

        # Design state tracking for consequence feedback
        self.design_log: list[str] = []

    # --- objective / requirements ---
    def set_objective(self, objective: str) -> None:
        """Confirm mission objective and derive requirements."""
        self.objective = objective
        self._derive_requirements()
        self.phase = MissionPhase.SPACECRAFT

    def _derive_requirements(self) -> None:
        """Translate scenario requirements into capability checks."""
        reqs = []
        for cap in self.scenario.required_capabilities:
            reqs.append(f"Payload must provide '{cap}' capability")
        for obj in self.scenario.required_objectives:
            reqs.append(f"Mission objective: {obj.replace('_', ' ')}")
        if self.scenario.sandbox_mode:
            reqs.append("Sandbox mode — no hard requirements")
        self.requirements = reqs

    # --- design mutation with consequence logging ---
    def add_bus_component(self, component) -> None:
        self.spacecraft.add_bus(component)
        self._sync_resources()
        self.design_log.append(
            f"Added {component.name}: {component.impact_summary()}")

    def remove_bus_component(self, component_id: str) -> bool:
        ok = self.spacecraft.remove_bus(component_id)
        if ok:
            self._sync_resources()
        return ok

    def add_instrument(self, instrument: Instrument) -> None:
        if self.scenario.allowed_instruments and instrument.id not in self.scenario.allowed_instruments:
            raise ValueError(f"{instrument.name} not allowed in this scenario")
        self.spacecraft.add_instrument(instrument)
        self._sync_resources()
        self.design_log.append(
            f"Added instrument {instrument.name}: {instrument.impact_summary()}")

    def remove_instrument(self, instrument_id: str) -> bool:
        ok = self.spacecraft.remove_instrument(instrument_id)
        if ok:
            self._sync_resources()
        return ok

    @property
    def picks_destination(self) -> bool:
        """Only sandbox players choose a destination; scenario missions
        go wherever their orbit is."""
        return self.scenario.sandbox_mode

    def _budget_for(self, planet) -> float:
        """Scenario missions get the scenario's difficulty-scaled budget;
        in sandbox the budget grows with the destination's distance."""
        if self.scenario.sandbox_mode:
            from .planets import budget_for
            return budget_for(planet)
        return self.scenario.effective_budget()

    def set_orbit(self, orbit: Orbit) -> None:
        if (self.scenario.allowed_orbits
                and orbit.id not in self.scenario.allowed_orbits):
            raise ValueError(f"{orbit.name} not allowed in this scenario")
        self.orbit = orbit
        self._update_mass_limit()
        self._sync_destination()

    def _sync_destination(self) -> None:
        """Scenario missions: the destination follows the orbit's body."""
        if not self.picks_destination:
            from .planets import destination_for_orbit
            self.set_destination(destination_for_orbit(self.orbit))

    def set_destination(self, planet) -> None:
        """Set (or clear, with None) the destination planet. In sandbox the
        budget follows it (farther worlds get bigger budgets)."""
        self.destination = planet
        self.resources.budget_limit_usd = self._budget_for(planet)

    def set_launch_vehicle(self, lv: LaunchVehicle) -> None:
        self.launch_vehicle = lv
        self._update_mass_limit()
        self._sync_resources()

    def _update_mass_limit(self) -> None:
        """Mass limit comes from the LV's capacity to the selected orbit.
        Recomputed whenever either one changes so order of selection
        doesn't matter."""
        if self.orbit and self.launch_vehicle:
            cap = self.launch_vehicle.capacity_for(self.orbit)
            if cap:
                self.resources.set_mass_limit(cap)

    def _sync_resources(self) -> None:
        """Push spacecraft totals into the resource budget."""
        sc = self.spacecraft
        self.resources.mass_used_kg = sc.total_mass_kg
        self.resources.power_used_w = sc.power_consumed_w
        self.resources.power_limit_w = sc.power_generated_w
        self.resources.comms_limit_mbps = sc.comms_mbps
        self.resources.data_limit_gb = sc.data_capacity_gb
        self.resources.cost_spent_usd = (
            sc.total_cost_usd
            + (self.launch_vehicle.cost_usd if self.launch_vehicle else 0.0)
        )

    # --- validation ---
    def validate_design(self) -> tuple[list[str], list[str]]:
        """Check the whole design.

        Returns (errors, warnings). Errors = hard violations.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Essential systems
        for missing in self.spacecraft.missing_essentials():
            errors.append(f"Missing essential system: {missing}")

        # Resource violations
        errors.extend(self.resources.violations())
        warnings.extend(self.resources.warnings())

        # Orbit / launch vehicle compatibility
        if self.orbit and self.launch_vehicle:
            ok, reason = self.launch_vehicle.can_launch(
                self.spacecraft.total_mass_kg, self.orbit)
            if not ok:
                errors.append(f"Launch incompatibility: {reason}")
        elif not self.orbit:
            errors.append("No orbit selected")
        elif not self.launch_vehicle:
            errors.append("No launch vehicle selected")

        # Power balance
        if self.spacecraft.power_margin_w < 0:
            errors.append(
                f"Power deficit: consuming {self.spacecraft.power_consumed_w:.0f} W "
                f"but only generating {self.spacecraft.power_generated_w:.0f} W")

        # Objective capability coverage
        caps = self.spacecraft.capabilities
        for cap in self.scenario.required_capabilities:
            if cap not in caps:
                errors.append(
                    f"Objective unmet: no instrument provides '{cap}' capability")

        # Data vs comms feasibility (rough check)
        if (self.spacecraft.comms_mbps > 0
                and self.spacecraft.data_rate_mbps > self.spacecraft.comms_mbps * 2):
            warnings.append(
                f"Data generation ({self.spacecraft.data_rate_mbps:.0f} Mbps) "
                f"far exceeds downlink ({self.spacecraft.comms_mbps:.0f} Mbps) — "
                "expect data backlog")

        # Instruments that don't suit the scenario: a caution, never a block
        warnings.extend(self.scenario.instrument_warnings(self.spacecraft.payload))

        # Sandbox mode: violations become warnings
        if self.scenario.sandbox_mode:
            warnings.extend(errors)
            errors = []

        return errors, warnings

    # Resource fields that hold the *last flight's results*, not the design
    _RUN_FIELDS = ("time_used_months", "data_generated_gb", "data_downlinked_gb")

    def reset_run_results(self) -> None:
        """Forget the previous flight (call before launching again)."""
        for name in self._RUN_FIELDS:
            setattr(self.resources, name, 0.0)

    def preflight_check(self) -> tuple[list[str], list[str]]:
        """validate_design() for the design alone, ignoring the last
        flight's results. After a run that used the whole mission time,
        validate_design() reports "Mission time limit reached" — true of
        that flight, but not a reason to block the next launch."""
        saved = {name: getattr(self.resources, name) for name in self._RUN_FIELDS}
        self.reset_run_results()
        try:
            return self.validate_design()
        finally:
            for name, value in saved.items():
                setattr(self.resources, name, value)

    def can_simulate(self) -> bool:
        errors, _ = self.validate_design()
        return len(errors) == 0

    # --- simulation ---
    def simulate(self, seed: int | None = None,
                 modifiers: dict | None = None) -> "MissionResult":
        """Run the mission simulation and return results. `modifiers` are
        the player's in-flight event choices (see MissionSimulator)."""
        from .simulation import MissionSimulator
        sim = MissionSimulator(self, seed=seed, modifiers=modifiers)
        result = sim.run()
        # Reflect the run in the resource budget (time used, data volumes)
        self.resources.time_used_months = result.months_elapsed
        self.resources.data_generated_gb = result.data_generated_gb
        self.resources.data_downlinked_gb = result.data_downlinked_gb
        return result

    # --- serialization ---
    def to_dict(self) -> dict:
        """Serialize the mission design to a JSON-friendly dict."""
        return {
            "name": self.name,
            "scenario_id": self.scenario.id,
            "objective": self.objective,
            "phase": self.phase.value,
            "bus_ids": [c.id for c in self.spacecraft.bus],
            "instrument_ids": [i.id for i in self.spacecraft.payload],
            "orbit_id": self.orbit.id if self.orbit else None,
            "launch_vehicle_id": (self.launch_vehicle.id
                                  if self.launch_vehicle else None),
            "destination_id": self.destination.id if self.destination else None,
            "design_log": list(self.design_log),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Mission":
        """Rebuild a mission from a dict produced by to_dict()."""
        import json as _json
        from pathlib import Path as _Path

        from .planets import DESTINATIONS
        from .scenarios import get_scenarios
        from .spacecraft import BUS_COMPONENTS

        scenario = get_scenarios()[data["scenario_id"]]
        mission = cls(name=data["name"], scenario=scenario)
        mission.objective = data.get("objective", scenario.objective)
        mission.phase = MissionPhase(data.get("phase", MissionPhase.OBJECTIVE.value))
        mission.design_log = list(data.get("design_log", []))

        # Rebuild spacecraft from catalog IDs
        for cid in data.get("bus_ids", []):
            if cid in BUS_COMPONENTS:
                mission.spacecraft.add_bus(BUS_COMPONENTS[cid])
        inst_cat = get_instrument_catalog()
        for iid in data.get("instrument_ids", []):
            if iid in inst_cat:
                mission.spacecraft.add_instrument(inst_cat[iid])

        # Rebuild orbit from orbits.json
        orbit_id = data.get("orbit_id")
        if orbit_id:
            orbit_path = (_Path(__file__).resolve().parent.parent
                          / "data" / "orbits.json")
            raw = _json.loads(orbit_path.read_text(encoding="utf-8"))
            for e in raw["orbits"]:
                if e["id"] == orbit_id:
                    mission.orbit = Orbit(
                        id=e["id"], name=e["name"], body=e["body"],
                        altitude_km=float(e["altitude_km"]),
                        inclination_deg=float(e["inclination_deg"]),
                        period_hours=float(e["period_hours"]),
                        description=e.get("description", ""),
                        coverage=e.get("coverage", "global"),
                        eclipse_fraction=float(e.get("eclipse_fraction", 0.0)),
                        drag_factor=float(e.get("drag_factor", 0.0)),
                        comms_passes_per_day=int(e.get("comms_passes_per_day", 0)),
                        radiation_level=int(e.get("radiation_level", 0)),
                        revisit_days=float(e.get("revisit_days", 7.0)),
                        comms_pass_minutes=float(e.get("comms_pass_minutes", 10.0)),
                        station_keeping_dv_m_s_per_year=float(
                            e.get("station_keeping_dv_m_s_per_year", 0.0)))
                    break

        # Rebuild launch vehicle
        lv_id = data.get("launch_vehicle_id")
        if lv_id:
            lv_cat = get_lv_catalog()
            if lv_id in lv_cat:
                mission.set_launch_vehicle(lv_cat[lv_id])

        # Rebuild destination: picked in sandbox, implied by the orbit
        # otherwise (an older save's hand-picked planet is ignored)
        if mission.picks_destination:
            dest_id = data.get("destination_id")
            if dest_id and dest_id in DESTINATIONS:
                mission.set_destination(DESTINATIONS[dest_id])
        else:
            mission._sync_destination()

        mission._sync_resources()
        return mission

    # --- display ---
    def dashboard(self) -> str:
        lines = [
            f"MISSION: {self.name}",
            f"Scenario: {self.scenario.name} ({self.scenario.difficulty})",
            f"Objective: {self.objective}",
            f"Phase: {self.phase.value}",
            "",
            self.spacecraft.summary(),
            "",
            self.resources.dashboard(),
        ]
        if self.orbit:
            lines.append(f"Orbit: {self.orbit.name} ({self.orbit.body}, "
                         f"{self.orbit.altitude_km:.0f} km)")
        if self.launch_vehicle:
            lines.append(f"Launch: {self.launch_vehicle.name} "
                         f"(${self.launch_vehicle.cost_usd / 1e6:.0f}M, "
                         f"reliability {self.launch_vehicle.reliability:.0%})")
        return "\n".join(lines)
