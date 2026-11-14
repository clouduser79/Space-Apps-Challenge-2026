"""Live mission telemetry.

`resource_readings` and `systems_check` turn the mission model into plain
display data (fractions, labels, tones). The `TelemetryPanel` sidebar and
the Mission Review screen both render from them, so the two views can
never disagree about the state of the design.
"""

from __future__ import annotations

from dataclasses import dataclass

import customtkinter as ctk

from src.game.mission import Mission
from src.ui import theme as T
from src.ui.widgets import Badge, Card, Meter, StatTile, StatusRow, eyebrow


@dataclass
class Reading:
    """One resource meter: how full it is, what to print, how healthy."""

    fraction: float
    value: str
    tone: str = "accent"
    hint: str = ""


def resource_readings(mission: Mission) -> dict[str, Reading]:
    """Budget, mass, power, data, comms and time as meter readings.

    Tone thresholds mirror the game's own rules (see ResourceBudget.
    violations): under 10% budget/mass margin or 15% power margin is a
    hard error, so the bar turns red exactly when the design becomes
    unflyable.
    """
    sc, r = mission.spacecraft, mission.resources
    out: dict[str, Reading] = {}

    # Budget — spacecraft + launch vehicle against the scenario budget
    frac = r.cost_spent_usd / r.budget_limit_usd if r.budget_limit_usd else 0.0
    if frac > 1:
        hint = "Over budget"
    elif mission.destination is None:
        hint = "Minimum budget — a farther destination raises it"
    else:
        hint = (f"{T.money(r.budget_remaining_usd)} remaining · "
                f"set by {mission.destination.name}")
    out["budget"] = Reading(
        frac, f"{T.money(r.cost_spent_usd)} / {T.money(r.budget_limit_usd)}",
        T.usage_tone(frac), hint)

    # Mass — only has a limit once both orbit and launch vehicle are chosen
    if r.mass_limit_kg:
        frac = r.mass_used_kg / r.mass_limit_kg
        out["mass"] = Reading(
            frac, f"{r.mass_used_kg:,.0f} / {r.mass_limit_kg:,.0f} kg",
            T.usage_tone(frac),
            "Too heavy for this launcher" if frac > 1
            else f"{r.mass_limit_kg - r.mass_used_kg:,.0f} kg of lift to spare")
    else:
        out["mass"] = Reading(0.0, f"{sc.total_mass_kg:,.0f} kg", "accent",
                              "Limit set by orbit + launch vehicle")

    # Power — consumption against generation
    used, gen = sc.power_consumed_w, sc.power_generated_w
    if gen:
        frac = used / gen
        out["power"] = Reading(
            frac, f"{used:,.0f} / {gen:,.0f} W", T.usage_tone(frac, 0.70, 0.85),
            "Power deficit" if frac > 1 else f"{gen - used:,.0f} W margin")
    else:
        out["power"] = Reading(1.0 if used else 0.0, f"{used:,.0f} / 0 W",
                               "danger" if used else "accent",
                               "No power generation installed")

    # Data — science data produced against downlink capacity
    data, link = sc.data_rate_mbps, sc.comms_mbps
    if link:
        frac = data / link
        tone = "danger" if frac > 2 else "warning" if frac > 1 else "accent"
        hint = ("Expect a growing data backlog" if frac > 1
                else "Downlink keeps up with instruments")
        out["data"] = Reading(frac, f"{data:g} / {link:g} Mbps", tone, hint)
    else:
        out["data"] = Reading(1.0 if data else 0.0, f"{data:g} / 0 Mbps",
                              "danger" if data else "accent", "No downlink installed")

    # Comms — raw downlink capacity
    out["comms"] = Reading(1.0 if link else 0.0, f"{link:g} Mbps downlink",
                           "accent" if link else "danger",
                           "" if link else "No communications subsystem")

    # Time — filled in by the simulation
    frac = (r.time_used_months / r.time_limit_months) if r.time_limit_months else 0.0
    out["time"] = Reading(frac, f"{r.time_used_months:.0f} / {r.time_limit_months} months",
                          "accent", "Advances when you run the simulation")
    return out


def systems_check(mission: Mission) -> list[tuple[str, str, str]]:
    """Checklist rows as (label, tone, detail)."""
    sc = mission.spacecraft
    bus = sc.bus

    def row(label: str, ok: bool, detail_ok: str = "", detail_missing: str = "missing"):
        return (label, "success", detail_ok) if ok else (label, "danger", detail_missing)

    rows = [
        row("Power generation", any(c.power_gen_w > 0 for c in bus),
            f"{sc.power_generated_w:g} W"),
        row("Communications", any(c.comms_mbps > 0 for c in bus),
            f"{sc.comms_mbps:g} Mbps"),
        row("Attitude control", any(c.id.startswith("adcs") for c in bus)),
        row("Onboard computer", any(c.id.startswith("avionics") for c in bus)),
        row("Science payload", bool(sc.payload),
            f"{len(sc.payload)} instrument{'s' if len(sc.payload) != 1 else ''}",
            "none"),
    ]
    for capability in mission.scenario.required_capabilities:
        rows.append(row(f"Capability: {capability.replace('_', ' ')}",
                        capability in sc.capabilities))
    rows += [
        row("Orbit", mission.orbit is not None,
            mission.orbit.body if mission.orbit else "", "not selected"),
        row("Launch vehicle", mission.launch_vehicle is not None,
            mission.launch_vehicle.name if mission.launch_vehicle else "", "not selected"),
        row("Destination", mission.destination is not None,
            mission.destination.name if mission.destination else "", "not selected"),
    ]
    return rows


def readiness(mission: Mission) -> tuple[str, str]:
    """Overall status as (badge text, tone)."""
    errors, warnings = mission.preflight_check()
    if errors:
        return f"{len(errors)} issue{'s' if len(errors) != 1 else ''}", "danger"
    if warnings:
        return f"{len(warnings)} caution{'s' if len(warnings) != 1 else ''}", "warning"
    return "Flight ready", "success"


class TelemetryPanel(Card):
    """Sidebar that stays visible while designing, so every Add/Remove
    click shows its consequence immediately."""

    WIDTH = 300
    _METERS = [("budget", "Budget"), ("mass", "Launch mass"),
               ("power", "Power load"), ("data", "Data vs downlink")]

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=T.SURFACE, width=self.WIDTH)
        self.app = app
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)

        head = self._row(pady=(T.PAD, 0))
        head.grid_columnconfigure(0, weight=1)
        eyebrow(head, "Live telemetry").grid(row=0, column=0, sticky="w")
        self.status = Badge(head, "—")
        self.status.grid(row=0, column=1, sticky="e")

        self.meters: dict[str, Meter] = {}
        for key, caption in self._METERS:
            meter = Meter(self, caption)
            meter.grid(sticky="ew", padx=T.PAD, pady=(14, 0))
            self.meters[key] = meter

        tiles = self._row(pady=(T.PAD, 0))
        tiles.grid_columnconfigure((0, 1), weight=1, uniform="tile")
        self.science = StatTile(tiles, "Science value")
        self.science.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.parts = StatTile(tiles, "Components")
        self.parts.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        eyebrow(self, "Systems check", T.TEXT_DIM).grid(
            sticky="w", padx=T.PAD, pady=(T.PAD_LG - 4, 6))
        self.checklist = self._row(pady=(0, T.PAD))
        self.checklist.grid_columnconfigure(0, weight=1)
        self._rows: list[StatusRow] = []

    def _row(self, pady) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(sticky="ew", padx=T.PAD, pady=pady)
        return frame

    def refresh(self) -> None:
        mission = self.app.mission
        if mission is None:
            return
        self.status.set(*readiness(mission))

        readings = resource_readings(mission)
        for key, meter in self.meters.items():
            reading = readings[key]
            meter.set(reading.fraction, reading.value, reading.tone, reading.hint)

        sc = mission.spacecraft
        self.science.set(f"{sc.science_value:.0f}", "violet" if sc.payload else "neutral")
        self.parts.set(str(len(sc.bus) + len(sc.payload)))

        rows = systems_check(mission)
        while len(self._rows) < len(rows):          # grow once, then reuse
            status_row = StatusRow(self.checklist, "")
            status_row.grid(sticky="ew", pady=2)
            self._rows.append(status_row)
        for status_row, (label, tone, detail) in zip(self._rows, rows):
            status_row.set(tone, detail, label=label)
