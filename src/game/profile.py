"""Player profile: XP, ranks, medals, shop unlocks and a log of every
flight, saved to saves/profile.json.

Two XP numbers: `xp` is lifetime XP earned (it drives rank and never goes
down), and `xp_spent` is what has gone into the shop. The spendable
balance is the difference, so buying things never costs you a rank.

XP for a flight:  25 for flying
                + the mission score (0-100)
                + 20 per objective met
                + medal bonus (gold 100, silver 50, bronze 25)
A launch failure still earns 10 XP — trying counts.

Medals reward meeting the scenario's objectives:
  gold    every objective met and a score of 85+
  silver  every objective met
  bronze  at least one objective met
Sandbox missions have no objectives, so they medal on score alone
(85+ gold, 70+ silver, 50+ bronze).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime

from . import save_load

RANKS: list[tuple[int, str]] = [
    (0, "Cadet"), (250, "Pilot"), (600, "Navigator"), (1200, "Commander"),
    (2500, "Admiral"), (5000, "Legend"),
]
MEDAL_XP = {"gold": 100, "silver": 50, "bronze": 25}


@dataclass
class Profile:
    name: str = "Commander"
    xp: int = 0
    flights: int = 0
    successes: int = 0
    best_score: float = 0.0
    medals: dict = field(default_factory=lambda: {"gold": 0, "silver": 0, "bronze": 0})
    xp_spent: int = 0
    unlocks: list = field(default_factory=list)      # shop item ids
    history: list = field(default_factory=list)      # one dict per flight

    @property
    def balance(self) -> int:
        """XP available to spend in the shop."""
        return max(0, self.xp - self.xp_spent)


def _path():
    return save_load.SAVE_DIR / "profile.json"


def load_profile() -> Profile:
    """The saved profile, or a fresh one if missing or unreadable."""
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        profile = Profile(**{k: v for k, v in data.items() if k in Profile.__dataclass_fields__})
        profile.medals = {**Profile().medals, **(profile.medals or {})}
        return profile
    except (OSError, ValueError, TypeError):
        return Profile()


def save_profile(profile: Profile) -> None:
    try:
        save_load.SAVE_DIR.mkdir(parents=True, exist_ok=True)
        _path().write_text(json.dumps(asdict(profile), indent=2), encoding="utf-8")
    except OSError:
        pass   # a read-only folder must never break the game


def rank_for(xp: int) -> dict:
    """Current rank plus progress toward the next one."""
    index = max(i for i, (floor, _) in enumerate(RANKS) if xp >= floor)
    floor, name = RANKS[index]
    if index + 1 < len(RANKS):
        next_floor, next_name = RANKS[index + 1]
        progress = (xp - floor) / (next_floor - floor)
    else:
        next_floor, next_name, progress = None, None, 1.0
    return {"name": name, "level": index + 1, "floor": floor, "next_name": next_name,
            "next_floor": next_floor, "progress": progress}


def medal_for(result, score: float, scenario) -> str | None:
    """'gold' / 'silver' / 'bronze' / None for a finished flight."""
    if not result.launch_success:
        return None
    met, failed = len(result.objectives_met), len(result.objectives_failed)
    if met + failed == 0:                     # sandbox: score only
        return ("gold" if score >= 85 else "silver" if score >= 70
                else "bronze" if score >= 50 else None)
    if failed == 0:
        return "gold" if score >= 85 else "silver"
    return "bronze" if met > 0 else None


def buy(profile: Profile, item_id: str) -> bool:
    """Spend XP to unlock a shop item. False if unaffordable or owned."""
    from .shop import ITEMS_BY_ID
    item = ITEMS_BY_ID.get(item_id)
    if item is None or item_id in profile.unlocks or profile.balance < item.price:
        return False
    profile.xp_spent += item.price
    profile.unlocks.append(item_id)
    save_profile(profile)
    return True


def award_flight(profile: Profile, result, score: float, medal: str | None,
                 mission=None) -> dict:
    """Add one flight to the profile (and save it): XP, medal, and an
    entry in the flight log. Returns what changed, for the results screen
    and milestone toasts."""
    before = rank_for(profile.xp)
    if result.launch_success:
        gained = (25 + round(score) + 20 * len(result.objectives_met)
                  + MEDAL_XP.get(medal or "", 0))
    else:
        gained = 10
    profile.xp += gained
    profile.flights += 1
    if result.success:
        profile.successes += 1
    profile.best_score = max(profile.best_score, float(score))
    if medal:
        profile.medals[medal] = profile.medals.get(medal, 0) + 1
    after = rank_for(profile.xp)
    profile.history.append({
        "flight": profile.flights,
        "mission": getattr(mission, "name", result.mission_name),
        "destination": getattr(getattr(mission, "destination", None), "name", "—"),
        "score": round(float(score), 1),
        "xp": gained,
        "medal": medal,
        "rank": after["name"],
        "level": after["level"],
        "success": bool(result.success),
        "launch_ok": bool(result.launch_success),
        "objectives": f"{len(result.objectives_met)}/"
                      f"{len(result.objectives_met) + len(result.objectives_failed)}",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    save_profile(profile)
    return {"xp_gained": gained, "rank_before": before, "rank_after": after,
            "ranked_up": after["level"] > before["level"], "medal": medal}
