"""Multiplayer / networking layer (stretch goal).

Blueprint: team mode for up to 4 players. Options:
  - Local hot-seat: simplest — players share one screen, take turns.
  - LAN/WebSocket server: players on same network join a room.
  - Online (WebRTC/WebSocket relay): players anywhere.

State sync: mission design is shared; each player edits their
role's section; server (or host) validates and merges changes.
"""

# TODO: decide networking approach based on UI framework choice
# TODO: room codes / lobby system
# TODO: conflict resolution when two players edit simultaneously
# TODO: role-based permissions (Scientist can only pick instruments,
#       etc. — or keep all decisions collective per spec)
