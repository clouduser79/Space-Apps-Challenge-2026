"""In-flight event cards: tactical choices made during the launch simulation.

Each card pauses the flight and offers two options. Every option carries
`effects` — modifiers the MissionSimulator understands (science_mult,
data_mult, event_freq_mult, ops_months_mult, forced_events) — plus short
`chips` that spell the trade-off out for the player. The final simulation
is run with all chosen effects applied, so choices really change the score.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class Choice:
    label: str
    effects: dict
    chips: list[tuple[str, str]]          # (text, tone) — tone: success/danger/warning


@dataclass
class EventCard:
    id: str
    phase: str                            # "cruise" or "ops"
    icon: str
    title: str
    story: str
    choices: list[Choice] = field(default_factory=list)


DECK: list[EventCard] = [
    EventCard("micrometeorites", "cruise", "☄️", "Micrometeorite swarm ahead!",
              "Radar spots a cloud of tiny, super-fast space rocks crossing your path.",
              [Choice("Burn fuel to dodge", {"ops_months_mult": 0.9},
                      [("−10% mission time", "warning"), ("No damage", "success")]),
               Choice("Shield up — accept power dips", {"forced_events": ["Shield maneuver power dip"]},
                      [("Power margin dips", "danger"), ("Keeps all your fuel", "success")])]),
    EventCard("solar_flare", "cruise", "☀️", "Solar flare warning!",
              "The Sun just erupted. A wave of radiation will hit in a few hours.",
              [Choice("Power down (safe mode)", {"science_mult": 0.95},
                      [("−5% science", "warning"), ("Electronics protected", "success")]),
               Choice("Keep instruments running", {"forced_events": ["Solar flare"], "science_mult": 1.04},
                      [("+1 anomaly", "danger"), ("+4% science", "success")])]),
    EventCard("comet", "ops", "✨", "Surprise comet flyby!",
              "A comet is zooming past — a once-in-a-lifetime chance to study it.",
              [Choice("Retarget the instruments", {"science_mult": 1.12, "data_mult": 1.3},
                      [("+12% science", "success"), ("+30% data to send home", "warning")]),
               Choice("Stick to the plan", {"event_freq_mult": 0.85},
                      [("Fewer surprises", "success"), ("Miss the comet", "warning")])]),
    EventCard("battery", "ops", "🔋", "Battery is getting old!",
              "Your batteries can't hold as much charge as they used to.",
              [Choice("Switch off one instrument", {"science_mult": 0.9},
                      [("−10% science", "warning"), ("Power stays safe", "success")]),
               Choice("Push through", {"forced_events": ["Safe mode event"]},
                      [("Risk of safe mode", "danger"), ("All instruments on", "success")])]),
]


def pick_events(rng: random.Random | None = None) -> list[EventCard]:
    """One cruise card and one operations card for this flight."""
    rng = rng or random.Random()
    cruise = [c for c in DECK if c.phase == "cruise"]
    ops = [c for c in DECK if c.phase == "ops"]
    return [rng.choice(cruise), rng.choice(ops)]


def merge_effects(chosen: list[dict]) -> dict:
    """Combine several choices: multipliers multiply, forced events add up."""
    out: dict = {}
    for effects in chosen:
        for key, value in effects.items():
            if key == "forced_events":
                out.setdefault(key, []).extend(value)
            else:
                out[key] = out.get(key, 1.0) * value
    return out
