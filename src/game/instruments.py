"""Scientific instruments catalog.

Blueprint: each instrument trades scientific value against mass,
power, cost, and data generation. This is the core trade-off system.
"""

from __future__ import annotations

# TODO: from dataclasses import dataclass


class Instrument:
    """A scientific instrument the player can select."""

    def __init__(self, name: str, mass_kg: float, power_w: float,
                 cost_usd: float, data_rate_mbps: float,
                 science_value: float, description: str) -> None:
        self.name = name
        self.mass_kg = mass_kg
        self.power_w = power_w
        self.cost_usd = cost_usd
        self.data_rate_mbps = data_rate_mbps
        self.science_value = science_value  # 0-100 scale
        self.description = description
        # TODO: add fields: required_pointing_accuracy, min_orbit_altitude,
        #       wavelength_band, sample_return_capable, etc.

    # TODO: to_dict() / from_dict()


# TODO: INSTRUMENT_CATALOG — dict of predefined instruments, e.g.:
#   - "Wide-Angle Camera": cheap, light, low science value, low data
#   - "High-Res Imager": moderate cost/mass, high science value, high data
#   - "Spectrometer": detects composition, medium everything
#   - "Radar Sounder": subsurface, heavy, high power, high data
#   - "Sample Return Capsule": very heavy/costly, huge science value
#   - "Magnetometer": light, low power, niche science value
#   - "Radiation Detector": light, useful for crewed/habitat missions
#   - "Communications Relay": boosts data downlink, not science
#
# TODO: load catalog from src/data/instruments.json instead of hardcoding
