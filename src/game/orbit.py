"""Orbit selection.

Blueprint: orbits differ in altitude, inclination, coverage,
communications passes, and mission lifetime (drag / radiation).
Orbit choice affects science return and operational constraints.
"""

from __future__ import annotations


class Orbit:
    """An orbital regime the mission can target."""

    def __init__(self, name: str, body: str, altitude_km: float,
                 inclination_deg: float, period_hours: float,
                 description: str) -> None:
        self.name = name
        self.body = body                # e.g. "Earth", "Mars", "Moon"
        self.altitude_km = altitude_km
        self.inclination_deg = inclination_deg
        self.period_hours = period_hours
        self.description = description
        # TODO: add fields:
        #   - coverage: global vs regional revisit time
        #   - eclipse_fraction (affects power)
        #   - drag_factor (LEO decays faster -> shorter lifetime)
        #   - comms_passes_per_day (depends on ground station network)
        #   - radiation_level (affects instrument lifetime / electronics)

    # TODO: methods:
    #   - science_coverage_score() -> float
    #   - comms_capacity_per_day() -> float (Mbps-days)
    #   - estimated_lifetime_years(spacecraft) -> float
    #   - educational_explanation() -> str (tooltip text for UI)


# TODO: ORBIT_CATALOG — predefined orbits, e.g.:
#   Earth: LEO (400 km, high drag, frequent passes), SSO (sun-synchronous,
#          ideal imaging), MEO/GPS-like, GEO (comms, poor coverage of poles)
#   Moon: Low Lunar Orbit, Frozen orbit, NRHO (Gateway-like)
#   Mars: Areostationary, Low Mars Orbit, Areosynchronous
#   Deep space: Earth-Sun L1/L2 (station-keeping fuel needed), Hohmann transfer
#
# TODO: load from src/data/orbits.json
