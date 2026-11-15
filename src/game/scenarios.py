"""Mission scenarios and difficulty levels.

Predefined mission types with different objectives, budgets, and
constraints. Difficulty scales budget tightness and event frequency.
Includes a sandbox mode for unconstrained experimentation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

DIFFICULTY_MULTIPLIERS = {
    "cadet":   {"budget": 1.5, "events": 0.5},
    "engineer": {"budget": 1.0, "events": 1.0},
    "expert":  {"budget": 0.7, "events": 1.5},
}


@dataclass
class Scenario:
    """A mission scenario the player can attempt."""

    id: str
    name: str
    description: str
    objective: str
    budget_usd: float
    mission_months: int
    difficulty: str
    required_objectives: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    allowed_orbits: list[str] | None = None      # orbit ids, None = all
    allowed_instruments: list[str] | None = None  # instrument ids, None = all
    event_frequency_multiplier: float = 1.0
    sandbox_mode: bool = False
    # instrument id -> why it's a poor fit (a soft warning, never a block)
    unsuitable_instruments: dict[str, str] = field(default_factory=dict)

    def effective_budget(self) -> float:
        """Budget adjusted by difficulty (tighter budgets on higher difficulty)."""
        if self.sandbox_mode:
            return self.budget_usd
        mult = DIFFICULTY_MULTIPLIERS.get(self.difficulty, {}).get("budget", 1.0)
        return self.budget_usd * mult

    def instrument_warnings(self, instruments) -> list[str]:
        """Soft warnings for instruments that don't suit this scenario."""
        out = []
        for inst in instruments:
            reason = self.unsuitable_instruments.get(inst.id)
            if reason:
                out.append(f"{inst.name} doesn't suit {self.name}: {reason}")
        return out


def load_scenarios(path: Path | None = None) -> dict[str, Scenario]:
    path = path or DATA_DIR / "scenarios.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    scenarios = {}
    for entry in raw["scenarios"]:
        sc = Scenario(
            id=entry["id"],
            name=entry["name"],
            description=entry.get("description", ""),
            objective=entry["objective"],
            budget_usd=float(entry["budget_usd"]),
            mission_months=int(entry["mission_months"]),
            difficulty=entry.get("difficulty", "engineer"),
            required_objectives=entry.get("required_objectives", []),
            required_capabilities=entry.get("required_capabilities", []),
            allowed_orbits=entry.get("allowed_orbits"),
            allowed_instruments=entry.get("allowed_instruments"),
            event_frequency_multiplier=float(entry.get("event_frequency_multiplier", 1.0)),
            sandbox_mode=bool(entry.get("sandbox_mode", False)),
            unsuitable_instruments=dict(entry.get("unsuitable_instruments") or {}),
        )
        scenarios[sc.id] = sc
    return scenarios


def get_scenarios() -> dict[str, Scenario]:
    return load_scenarios()
