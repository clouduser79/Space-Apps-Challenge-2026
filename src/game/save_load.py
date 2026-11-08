"""Save/load system.

Blueprint: persist mission designs, simulation results, and
leaderboard entries. Enables "save, share, and compare" designs.
"""

from __future__ import annotations

import json
from pathlib import Path

SAVE_DIR = Path("saves")
# TODO: SAVE_DIR.mkdir(exist_ok=True)


def save_mission(mission: "Mission", filename: str) -> Path:
    """Serialize a mission design to JSON."""
    # TODO: mission.to_dict() -> json.dump to SAVE_DIR / filename
    raise NotImplementedError


def load_mission(filename: str) -> "Mission":
    """Load a saved mission design."""
    # TODO: read JSON -> Mission.from_dict()
    raise NotImplementedError


def save_result(result: "MissionResult", score: float) -> None:
    """Append a mission result to the leaderboard/history."""
    # TODO: append to saves/history.jsonl (JSON Lines for easy append)
    raise NotImplementedError


def load_leaderboard() -> list[dict]:
    """Return all recorded mission results, sorted by score."""
    # TODO: read history.jsonl -> list of dicts -> sort desc by score
    raise NotImplementedError
