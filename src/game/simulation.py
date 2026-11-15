"""Mission simulation engine.

Steps through the mission timeline (launch -> cruise -> operations),
applying simplified models, random events, and resource consumption.
Produces a MissionResult for the scoring engine.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .mission import Mission


@dataclass
class RandomEvent:
    """An unexpected mission event (good or bad)."""

    name: str
    probability: float
    description: str
    science_multiplier: float = 1.0
    power_multiplier: float = 1.0     # applied during event months
    duration_months: int = 1
    mass_penalty_kg: float = 0.0      # e.g. debris avoidance fuel


# Event deck — frequency scaled by scenario.event_frequency_multiplier
EVENT_DECK: list[RandomEvent] = [
    RandomEvent("Micrometeorite strike", 0.10,
                "A micrometeorite damages an instrument — science output reduced.",
                science_multiplier=0.85, duration_months=3),
    RandomEvent("Solar flare", 0.12,
                "A solar flare boosts radiation — power systems degraded temporarily.",
                power_multiplier=0.7, duration_months=1),
    RandomEvent("Ground station outage", 0.10,
                "Primary ground station offline — data downlink delayed.",
                science_multiplier=0.95, duration_months=2),
    RandomEvent("Propellant leak", 0.06,
                "A small leak forces extra maneuvers — mission lifetime shortened.",
                science_multiplier=0.9, duration_months=6),
    RandomEvent("Bonus science window", 0.08,
                "Unexpected optimal viewing geometry — bonus science data.",
                science_multiplier=1.15, duration_months=2),
    RandomEvent("Computer glitch", 0.08,
                "Onboard computer reboots repeatedly — some data lost.",
                science_multiplier=0.9, duration_months=1),
    RandomEvent("Safe mode event", 0.05,
                "Spacecraft enters safe mode — instruments offline for weeks.",
                science_multiplier=0.5, power_multiplier=0.5, duration_months=1),
]


# Events that only happen because of a player's in-flight choice (never
# rolled randomly, so adding them doesn't change the odds of the deck above).
CHOICE_EVENTS: list[RandomEvent] = [
    RandomEvent("Shield maneuver power dip", 0.0,
                "Turned the spacecraft to shield its instruments — power margins "
                "dipped and observing slowed for a while.",
                science_multiplier=0.92, power_multiplier=0.75, duration_months=2),
]


@dataclass
class MissionResult:
    """Output of a simulation run."""

    mission_name: str
    launch_success: bool
    science_return: float            # 0-100+ scale
    objectives_met: list[str]
    objectives_failed: list[str]
    months_operated: float
    months_elapsed: float = 0.0     # cruise + ops — total mission duration
    data_generated_gb: float = 0.0
    data_downlinked_gb: float = 0.0
    data_backlog_gb: float = 0.0
    events_triggered: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    score_breakdown: dict = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.launch_success and not self.failure_reason and len(self.objectives_failed) == 0

    def to_dict(self) -> dict:
        """Serialize the result for the leaderboard/history file."""
        from dataclasses import asdict
        return asdict(self)


class MissionSimulator:
    """Runs a mission design through its lifecycle."""

    # Simplified model constants
    CRUISE_MONTHS = {"Earth": 0, "Moon": 3, "Mars": 8, "Deep Space": 12}
    GB_PER_MBPS_MONTH = 0.324  # 1 Mbps continuous for ~30 days ≈ 324 GB; we use duty cycle
    DOWNLINK_DUTY_CYCLE = 0.15  # fraction of time actually downlinking

    def __init__(self, mission: "Mission", seed: int | None = None,
                 modifiers: dict | None = None) -> None:
        """`modifiers` carries the player's in-flight decisions (all optional):
        science_mult, data_mult, event_freq_mult, ops_months_delta and
        forced_events (names from EVENT_DECK that happen at the start of
        operations), ops_months_mult. With none given the simulation behaves
        as before."""
        self.mission = mission
        self.rng = random.Random(seed)
        self.events_triggered: list[str] = []
        self.mods = modifiers or {}

    def run(self) -> MissionResult:
        m = self.mission
        sc = m.spacecraft
        months_total = m.scenario.mission_months

        # --- Phase 1: Launch ---
        launch_success = self.rng.random() < (m.launch_vehicle.reliability if m.launch_vehicle else 0.5)
        if not launch_success:
            return MissionResult(
                mission_name=m.name,
                launch_success=False,
                science_return=0.0,
                objectives_met=[],
                objectives_failed=m.scenario.required_objectives or ["launch"],
                months_operated=0.0,
                months_elapsed=0.0,
                data_generated_gb=0.0,
                data_downlinked_gb=0.0,
                data_backlog_gb=0.0,
                events_triggered=["Launch failure"],
                failure_reason="Launch vehicle failed — spacecraft lost.",
            )

        # --- Phase 2: Cruise ---
        body = m.orbit.body if m.orbit else "Earth"
        cruise_months = self.CRUISE_MONTHS.get(body, 6)
        ops_months = max(0.0, months_total - cruise_months)
        ops_months = round(ops_months * self.mods.get("ops_months_mult", 1.0))

        # --- Phase 3: Operations (monthly loop) ---
        science_accum = 0.0
        data_gen_gb = 0.0
        data_down_gb = 0.0
        # Active events are *copies* of the deck entries: their duration
        # counts down per run without wearing out the shared deck (which used
        # to make later runs in the same session shorter-lived).
        active_events: list[RandomEvent] = []
        event_freq = (m.scenario.event_frequency_multiplier
                      * self.mods.get("event_freq_mult", 1.0))
        by_name = {ev.name: ev for ev in EVENT_DECK + CHOICE_EVENTS}
        for name in self.mods.get("forced_events", []):
            if name in by_name:
                active_events.append(replace(by_name[name]))
                self.events_triggered.append(name)

        month = 0.0
        while month < ops_months:
            # Roll for new events
            # Every deck entry draws its roll each month, active or not, so a
            # player's choice changes only what it says it changes — not the
            # luck of every later event.
            for ev in EVENT_DECK:
                roll = self.rng.random()
                if (all(a.name != ev.name for a in active_events)
                        and roll < ev.probability * event_freq):
                    active_events.append(replace(ev))
                    self.events_triggered.append(ev.name)

            # Science accumulation
            month_science = sc.science_value * 0.5  # per month baseline
            for ev in active_events:
                month_science *= ev.science_multiplier
            science_accum += month_science

            # Data generation vs downlink
            gen_gb = sc.data_rate_mbps * self.GB_PER_MBPS_MONTH * self.mods.get("data_mult", 1.0)
            down_cap_gb = sc.comms_mbps * self.GB_PER_MBPS_MONTH * self.DOWNLINK_DUTY_CYCLE
            data_gen_gb += gen_gb
            data_down_gb += min(gen_gb, down_cap_gb)

            month += 1.0
            # Expire events
            for ev in list(active_events):
                ev.duration_months -= 1
                if ev.duration_months <= 0:
                    active_events.remove(ev)

        # --- Phase 4: Evaluate objectives ---
        objectives_met, objectives_failed = self._check_objectives(science_accum, data_backlog := data_gen_gb - data_down_gb)

        # Penalties
        science_return = science_accum * self.mods.get("science_mult", 1.0)
        if data_backlog > 1000:
            science_return *= 0.8  # overwhelmed storage/ops
        if m.spacecraft.power_margin_w < 0:
            science_return *= 0.7  # brownouts

        failure_reason = None
        if science_return <= 0:
            failure_reason = "No scientific return achieved."

        return MissionResult(
            mission_name=m.name,
            launch_success=True,
            science_return=science_return,
            objectives_met=objectives_met,
            objectives_failed=objectives_failed,
            months_operated=ops_months,
            months_elapsed=cruise_months + ops_months,
            data_generated_gb=data_gen_gb,
            data_downlinked_gb=data_down_gb,
            data_backlog_gb=data_backlog,
            events_triggered=self.events_triggered,
            failure_reason=failure_reason,
        )

    def _check_objectives(self, science_accum: float, data_backlog_gb: float) -> tuple[list[str], list[str]]:
        """Evaluate scenario required_objectives against sim results."""
        m = self.mission
        met, failed = [], []
        caps = m.spacecraft.capabilities

        for obj in m.scenario.required_objectives:
            ok = True
            if "revisit" in obj or "coverage" in obj:
                ok = science_accum > 50
            elif "composition" in obj or "spectro" in obj:
                ok = "spectroscopy" in caps
            elif "imaging" in obj or "map" in obj:
                ok = "imaging" in caps
            elif "weather" in obj or "solar" in obj:
                ok = "space_weather" in caps or m.orbit.body == "Deep Space"
            elif "sample" in obj:
                ok = "sample_return" in caps
            elif "radiation" in obj:
                ok = m.spacecraft.power_margin_w >= 0
            if ok:
                met.append(obj)
            else:
                failed.append(obj)
        return met, failed
