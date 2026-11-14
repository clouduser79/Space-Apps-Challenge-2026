"""Orbit selection.

Blueprint: orbits differ in altitude, inclination, coverage,
communications passes, and mission lifetime (drag / radiation).
Orbit choice affects science return and operational constraints.
"""

from __future__ import annotations

from typing import Any


class Orbit:
    """An orbital regime the mission can target."""

    def __init__(self, id: str, name: str, body: str, altitude_km: float,
                 inclination_deg: float, period_hours: float,
                 description: str, coverage: str, eclipse_fraction: float,
                 drag_factor: float, comms_passes_per_day: int,
                 radiation_level: int, revisit_days: float = 7.0,
                 comms_pass_minutes: float = 10.0,
                 station_keeping_dv_m_s_per_year: float = 0.0) -> None:
        self.id = id
        self.name = name
        self.body = body                # e.g. "Earth", "Mars", "Moon"
        self.altitude_km = altitude_km
        self.inclination_deg = inclination_deg
        self.period_hours = period_hours
        self.description = description
        self.coverage = coverage
        self.eclipse_fraction = eclipse_fraction
        self.drag_factor = drag_factor
        self.comms_passes_per_day = comms_passes_per_day
        self.radiation_level = radiation_level
        self.revisit_days = revisit_days
        self.comms_pass_minutes = comms_pass_minutes
        self.station_keeping_dv_m_s_per_year = station_keeping_dv_m_s_per_year

    def science_coverage_score(self) -> float:
        """0-1 score for how much of the target body this orbit can see.

        Placeholder model: latitude reach from inclination, combined
        with how often a given spot is revisited.
        """
        if self.coverage == "fixed_disc":
            return 0.4              # sees a whole hemisphere, never changes
        incl = self.inclination_deg
        lat_reach = (incl if incl <= 90 else 180 - incl) / 90
        lat_reach = min(max(lat_reach, 0.0), 1.0)
        revisit = 1 / (1 + self.revisit_days / 7)
        base = 0.5 * lat_reach + 0.5 * revisit
        return round(base * (0.6 if self.coverage == "regional" else 1.0), 3)

    def comms_capacity_per_day(self, downlink_mbps: float) -> float:
        """Data that can be downlinked per day, in gigabits.

        passes/day * minutes/pass * 60 s * Mbps / 1000.
        """
        seconds = self.comms_passes_per_day * self.comms_pass_minutes * 60
        return seconds * downlink_mbps / 1000

    def estimated_lifetime_years(self, spacecraft: Any) -> float:
        """Lifetime limited by drag, radiation, or station-keeping fuel.

        `spacecraft` is duck-typed. Optional attributes read with defaults:
          design_life_years (15), radiation_hardened (False),
          propellant_dv_m_s (0).
        """
        limits = [getattr(spacecraft, "design_life_years", 15.0)]

        if self.drag_factor > 0:
            limits.append(5.0 / self.drag_factor)   # unboosted decay

        hardened = getattr(spacecraft, "radiation_hardened", False)
        rad_tolerance = 45.0 if hardened else 15.0
        limits.append(rad_tolerance / max(self.radiation_level, 0.1))

        if self.station_keeping_dv_m_s_per_year > 0:
            dv = getattr(spacecraft, "propellant_dv_m_s", 0.0)
            limits.append(dv / self.station_keeping_dv_m_s_per_year)

        return round(max(min(limits), 0.0), 2)

    def educational_explanation(self) -> str:
        """Tooltip text for the UI."""
        
        parts = [f"{self.name} orbits {self.body} at about "
                 f"{self.altitude_km:,.0f} km, completing a lap every "
                 f"{self.period_hours:.1f} hours."]
        if self.drag_factor > 0.5:
            parts.append("Atmospheric drag is strong here, so the "
                         "spacecraft needs reboosts or has a short life.")
        if self.radiation_level > 3:
            parts.append("Radiation is harsh, which shortens electronics "
                         "and instrument life unless hardened.")
        if self.eclipse_fraction > 0.3:
            parts.append("Long eclipses mean more battery mass for power.")
    
        return " ".join(parts)

# TODO: ORBIT_CATALOG — predefined orbits, e.g.:
#   Earth: LEO (400 km, high drag, frequent passes), SSO (sun-synchronous,
#          ideal imaging), MEO/GPS-like, GEO (comms, poor coverage of poles)
#   Moon: Low Lunar Orbit, Frozen orbit, NRHO (Gateway-like)
#   Mars: Areostationary, Low Mars Orbit, Areosynchronous
#   Deep space: Earth-Sun L1/L2 (station-keeping fuel needed), Hohmann transfer
#
# TODO: load from src/data/orbits.json