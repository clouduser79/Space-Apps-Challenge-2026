"""Save/load system.

Blueprint: persist mission designs, simulation results, and
leaderboard entries. Enables "save, share, and compare" designs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .mission import Mission
    from .simulation import MissionResult

SAVE_DIR = Path(__file__).parent / "saves"
HISTORY_FILE = SAVE_DIR / "history.jsonl"   # default location; see _history_file()


def _history_file() -> Path:
    """The leaderboard file inside the *current* SAVE_DIR, so redirecting
    SAVE_DIR (e.g. in tests) redirects the history too."""
    return SAVE_DIR / "history.jsonl"


def _ensure_dir() -> None:
    SAVE_DIR.mkdir(parents=True, exist_ok=True)

def save_mission(mission: "Mission", filename: str) -> Path:
    """Serialize a mission design to JSON."""
    _ensure_dir()
    path = SAVE_DIR / filename
    if path.suffix != ".json":
        path = path.with_suffix(".json")
    with path.open("w", encoding="utf-8") as f:
        json.dump(mission.to_dict(), f, indent=2)
    return path


def load_mission(filename: str) -> "Mission":
    """Load a saved mission design."""
    from .mission import Mission

    path = SAVE_DIR / filename
    if path.suffix != ".json":
        path = path.with_suffix(".json")
    with path.open(encoding="utf-8") as f:
        return Mission.from_dict(json.load(f))


def save_result(result: "MissionResult", score: float) -> None:
    """Append a mission result to the leaderboard/history."""
    _ensure_dir()
    entry = {**result.to_dict(), "score": score}
    with _history_file().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def load_leaderboard() -> list[dict]:
    """Return all recorded mission results, sorted by score."""
    history = _history_file()
    if not history.exists():
        return []
    with history.open(encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]
    return sorted(entries, key=lambda e: e["score"], reverse=True)
