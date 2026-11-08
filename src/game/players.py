"""Player and team management.

Blueprint: supports 1-4 players. In team mode, each player has a
role (mission planning, spacecraft, science, comms/resources) but
decisions are collective — the game should surface trade-off
discussions between roles.
"""

from __future__ import annotations


class PlayerRole:
    """Team role constants."""
    # TODO: MISSION_PLANNER, SPACECRAFT_ENGINEER, SCIENTIST,
    #       COMMUNICATIONS, RESOURCE_MANAGER
    pass


class Player:
    """A participant in the mission team."""

    def __init__(self, name: str, role: str, is_ai: bool = False) -> None:
        self.name = name
        self.role = role
        # TODO: is_ai: for solo play, AI teammates can fill roles
        #       and suggest decisions (good for learning)
        # TODO: contribution_score: track decisions made per role
        # TODO: preferences: role-based weighting for scoring
        #       (e.g., Scientist values science_return more)

    # TODO: suggest_decision(mission_state) -> recommendation
    #       (used by AI teammates and for role-based UI hints)


class Team:
    """A team of up to 4 players working one mission."""

    MAX_PLAYERS = 4

    def __init__(self) -> None:
        self.players: list[Player] = []

    def add_player(self, player: Player) -> bool:
        """Add a player if under the 4-player cap."""
        # TODO: enforce MAX_PLAYERS
        # TODO: enforce unique roles (optional)
        raise NotImplementedError

    # TODO: collaboration mechanics:
    #   - decision proposals: a player proposes a change, team votes/confirms
    #   - role dashboards: each role sees metrics relevant to them
    #   - conflict surfacing: when two roles' priorities conflict,
    #     show the trade-off explicitly (educational goal)
    #   - contribution tracking for end-of-mission report
