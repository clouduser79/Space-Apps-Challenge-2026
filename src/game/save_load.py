"""Save/load system.

Blueprint: persist mission designs, simulation results, and
leaderboard entries. Enables "save, share, and compare" designs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .mission import Mission, MissionResult

SAVE_DIR = Path(__file__).parent / "saves"
HISTORY_FILE = SAVE_DIR / "history.json1"
#TODO: SAVE_DIR.mkdir(exist_ok=True)

def save_mission(mission: "Mission", filename: str) -> Path:
    """Serialize a mission design to JSON."""
    # TODO: mission.to_dict() -> json.dump to SAVE_DIR / filename
    path = SAVE_DIR / filename
    if path.suffix != ".json":
        path = path.with_suffix(".json")
    with path.open("W", encoding = "utf-8") as f:
        json.dump(mission.to_dict(), f, indent = 2)
    return path
    #raise NotImplementedError


def load_mission(filename: str) -> "Mission":
    """Load a saved mission design."""
    # TODO: read JSON -> Mission.from_dict()
    from .mission import Mission

    path = SAVE_DIR / filename
    if path.suffix != ".json":
        path = path.with_suffix(".json")
    with path.open(encoding = "utf-8") as f:
        return Mission.from_dict(json.load(f))
    #raise NotImplementedError


def save_result(result: "MissionResult", score: float) -> None:
    """Append a mission result to the leaderboard/history."""
    # TODO: append to saves/history.jsonl (JSON Lines for easy append)
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    entry = {**result.to_dict(), "score": score}
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    #raise NotImplementedError


def load_leaderboard() -> list[dict]:
    """Return all recorded mission results, sorted by score."""
    # TODO: read history.jsonl -> list of dicts -> sort desc by score
    if not HISTORY_FILE.exists():
        return []
    with HISTORY_FILE.open(encoidng = "utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]
    return sorted(entries, key=lambda e: e["score"], reverse = True)
    #raise NotImplementedError
