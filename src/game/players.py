"""Player and team management.

Supports 1-4 players. In team mode each player has a role; decisions
are collective but roles get tailored dashboard views and the
end-of-mission report credits contributions.
"""

from __future__ import annotations


class PlayerRole:
    MISSION_PLANNER = "mission_planner"
    SPACECRAFT_ENGINEER = "spacecraft_engineer"
    SCIENTIST = "scientist"
    COMMUNICATIONS = "communications"
    RESOURCE_MANAGER = "resource_manager"

    ALL = [MISSION_PLANNER, SPACECRAFT_ENGINEER, SCIENTIST,
           COMMUNICATIONS, RESOURCE_MANAGER]

    LABELS = {
        MISSION_PLANNER: "Mission Planner",
        SPACECRAFT_ENGINEER: "Spacecraft Engineer",
        SCIENTIST: "Scientist",
        COMMUNICATIONS: "Communications",
        RESOURCE_MANAGER: "Resource Manager",
    }


class Player:
    """A participant in the mission team."""

    def __init__(self, name: str, role: str) -> None:
        self.name = name
        self.role = role
        self.decisions_made: list[str] = []

    def record_decision(self, decision: str) -> None:
        self.decisions_made.append(decision)

    def contribution_summary(self) -> str:
        return f"{self.name} ({PlayerRole.LABELS.get(self.role, self.role)}): " \
               f"{len(self.decisions_made)} decisions"


class Team:
    """A team of up to 4 players working one mission."""

    MAX_PLAYERS = 4

    def __init__(self) -> None:
        self.players: list[Player] = []

    def add_player(self, player: Player) -> bool:
        if len(self.players) >= self.MAX_PLAYERS:
            return False
        self.players.append(player)
        return True

    @property
    def is_multiplayer(self) -> bool:
        return len(self.players) > 1

    def contributions_report(self) -> str:
        if not self.players:
            return "No players."
        return "\n".join(p.contribution_summary() for p in self.players)
