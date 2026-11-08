"""Spacecraft model.

Blueprint: spacecraft = bus (structure, power, comms, avionics, ADCS)
           + payload (scientific instruments).
Every component has mass, power draw, cost, and optional data rate.
"""

from __future__ import annotations

# TODO: from dataclasses import dataclass, field


@dataclass_placeholder = None  # placeholder so file parses without dataclasses yet


class Component:
    """Base class for any spacecraft component."""

    def __init__(self, name: str, mass_kg: float, power_w: float,
                 cost_usd: float) -> None:
        self.name = name
        self.mass_kg = mass_kg
        self.power_w = power_w
        self.cost_usd = cost_usd
        # TODO: add description / educational tooltip text

    # TODO: to_dict() / from_dict() for save/load


class Spacecraft:
    """The player's spacecraft: bus components + payload instruments."""

    def __init__(self) -> None:
        # TODO: bus components:
        #   - structure (mass varies by size class)
        #   - solar arrays / RTG (power generation)
        #   - batteries (energy storage for eclipse periods)
        #   - communications subsystem (data rate, affects downlink)
        #   - onboard computer (data handling, processing)
        #   - attitude determination & control (pointing accuracy)
        # TODO: payload: list[Instrument]
        # TODO: computed totals: total_mass, total_power_draw,
        #       total_cost, total_data_rate

    # TODO: add_component(component) / remove_component(component)
    # TODO: properties: total_mass, total_power, total_cost, total_data_rate
    # TODO: validate() -> list of constraint warnings
    # TODO: to_dict() / from_dict() for save/load
