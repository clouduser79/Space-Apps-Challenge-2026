"""3D mission viewport for the Launch screen.

The flight matches the mission type (`FlightPlan.kind`, from the
destination — see planets.mission_kind):

  interplanetary  Moon, Mars and sandbox worlds. Two worlds: a textured
                  Earth on the left — where Tharun's Rocket launches from
                  and lands back on — and the destination (sized by its
                  real diameter, with rings for Saturn) with its parking
                  orbit.
  earth           Earth-orbit missions (LEO, SSO, GEO): lift off, climb
                  into the mission orbit around Earth, three laps, then a
                  deorbit burn and a landing on Earth.
  l1              Sun–Earth L1: Earth on the right, the L1 point marked on
                  the Sun–Earth line to its left (sunward); cruise out, hold
                  station on a small halo loop, return.

Every kind uses the same four phases (only their labels and lengths
differ), so the rocket flies the whole mission in step with the
simulation:

  Standby     rocket stands on Earth; the planned paths are dashed
  Launch      engines + boosters fire, rocket lifts off and pitches over,
              boosters separate (or, on a launch failure, it explodes)
  Cruise      flies the outbound arc; solar arrays unfold, comms dish opens,
              then it slides into orbit along the orbit's own direction
  Operations  three full laps of the planet in the mission's orbit
  Return      leaves orbit along its direction of travel, arcs home beneath
              the outbound path and lands on Earth — then disappears

Paths are cubic Bezier curves whose end directions match the orbit and the
Earth's surface, so every hand-off is smooth (no corners). One method,
`FlightPlan.info(progress)`, turns overall flight progress into phase and
path parameters; the 3D view, the 2D map and the Launch screen all use the
same plan, so they can never disagree about where the rocket is. The
plan's length scales gently with the scenario's mission_months (clamped
to MIN_FLIGHT_S..MAX_FLIGHT_S).

The camera frames Earth, the planet, the orbit and both paths with a
margin, for whatever size the pane is. Drag to orbit the camera;
double-click resets.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from functools import lru_cache
import time
import tkinter as tk
import tkinter.font as tkfont

import customtkinter as ctk

from src.game.planets import EARTH, mission_kind
from src.ui import assets
from src.ui import planet_render as P
from src.ui import theme as T
from src.ui.spacecraft_view import (Camera, Instance, Renderer, RocketState, add,
                                    align_y, apply, build_rocket, length, lerp,
                                    matmul, mul, normalize, rot_x, rot_y, rot_z, sub)
from src.ui.trajectory_view import map_fraction
from src.ui.widgets import draw_stars

HEIGHT = 440
FPS_MS = 33                     # target frame interval
FOV = 50.0
MIN_3D_WIDTH = 380              # panes can't be dragged narrower than this,
MIN_MAP_WIDTH = 240             #   so their contents always fit
DEFAULT_PITCH = 0.24

# --------------------------------------------------------------------------
# Shared flight timeline (3D view, 2D map and Launch screen all use these)
# --------------------------------------------------------------------------
LAUNCH_SHARE = 0.15             # share of the outbound arc flown during Launch
_PHASE_KEYS = ("launch", "cruise", "ops", "return")

# Per mission kind: (phase label, seconds at the reference mission length)
# and laps of the orbit before heading home.
BASE_PHASES = {
    "interplanetary": (("Launch", 1.4), ("Cruise", 2.4), ("Operations", 4.5),
                       ("Return", 2.6)),
    "l1": (("Launch", 1.4), ("Cruise", 2.0), ("Station-keeping", 4.5), ("Return", 2.2)),
    "earth": (("Launch", 1.4), ("Ascent", 1.0), ("Operations", 4.5), ("Deorbit", 1.8)),
}
LOOPS_FOR = {"interplanetary": 3, "l1": 2, "earth": 3}
REFERENCE_MONTHS = 24           # mission length the base timings are for
MIN_FLIGHT_S, MAX_FLIGHT_S = 8.0, 16.0


def ops_scale(months: float) -> float:
    """Operations-phase stretch for a mission length: gentle (a fifth root
    -ish curve) and clamped, so 12 months is a bit shorter than 24 and
    120 months is under twice as long."""
    k = (max(1.0, months) / REFERENCE_MONTHS) ** 0.35
    return max(0.75, min(1.8, k))


@dataclass(frozen=True)
class FlightPlan:
    """One flight's timeline: phases (label, seconds) and laps in orbit."""

    kind: str
    phases: tuple
    loops: int

    @property
    def names(self) -> list[str]:
        return [name for name, _ in self.phases]

    @property
    def total(self) -> float:
        return sum(seconds for _, seconds in self.phases)

    def span(self, index: int) -> tuple[float, float]:
        """(start, width) of a phase as fractions of the whole flight."""
        start = sum(sec for _, sec in self.phases[:index]) / self.total
        return start, self.phases[index][1] / self.total

    def at(self, index: int, share: float) -> float:
        """Overall progress `share` of the way through phase `index`."""
        start, width = self.span(index)
        return start + share * width

    def phase_at(self, progress: float) -> tuple[int, float]:
        """(phase index, progress within that phase) for overall progress 0..1."""
        progress = max(0.0, min(1.0, progress))
        last = len(self.phases) - 1
        for i in range(len(self.phases)):
            start, width = self.span(i)
            if progress < start + width or i == last:
                return i, max(0.0, min(1.0, (progress - start) / width))
        return last, 1.0

    def info(self, progress: float) -> dict:
        """Everything both views need to place the rocket at `progress`:
        phase, u (progress within the phase), curve (outbound arc 0..1),
        orbit_angle (radians travelled in orbit), ret (return arc 0..1)."""
        index, u = self.phase_at(progress)
        loops = self.loops
        info = {"phase": _PHASE_KEYS[index], "index": index, "u": u,
                "curve": 1.0, "orbit_angle": 0.0, "ret": 0.0, "kind": self.kind}
        if index == 0:
            info["curve"] = LAUNCH_SHARE * u * u
        elif index == 1:
            info["curve"] = LAUNCH_SHARE + (1 - LAUNCH_SHARE) * _smooth(u)
        elif index == 2:
            info["orbit_angle"] = u * loops * 2 * math.pi
            info["lap"] = min(loops, int(u * loops) + 1)
        else:
            info["orbit_angle"] = loops * 2 * math.pi
            info["ret"] = u
        return info


def flight_plan(kind: str = "interplanetary", months: float = REFERENCE_MONTHS) -> FlightPlan:
    """Timeline for a mission kind, with operations stretched by
    `ops_scale(months)` and the whole flight clamped to
    MIN_FLIGHT_S..MAX_FLIGHT_S."""
    base = BASE_PHASES.get(kind, BASE_PHASES["interplanetary"])
    k = ops_scale(months)
    phases = [(name, sec * k if i == 2 else sec) for i, (name, sec) in enumerate(base)]
    total = sum(sec for _, sec in phases)
    fit = max(MIN_FLIGHT_S, min(MAX_FLIGHT_S, total)) / total
    return FlightPlan(kind, tuple((name, round(sec * fit, 3)) for name, sec in phases),
                      LOOPS_FOR.get(kind, 3))


def plan_for(mission) -> FlightPlan:
    """The flight plan for a mission: kind from its destination, length
    from its scenario."""
    if mission is None:
        return flight_plan("earth")
    return flight_plan(mission_kind(mission.destination), mission.scenario.mission_months)


# Defaults (an interplanetary flight of the reference length), kept for
# callers that don't have a mission at hand.
DEFAULT_PLAN = flight_plan()
FLIGHT_PHASES = DEFAULT_PLAN.phases
FLIGHT_S = DEFAULT_PLAN.total
LOOPS = DEFAULT_PLAN.loops


def phase_span(index: int) -> tuple[float, float]:
    return DEFAULT_PLAN.span(index)


def phase_at(progress: float) -> tuple[int, float]:
    return DEFAULT_PLAN.phase_at(progress)


def flight_info(progress: float) -> dict:
    return DEFAULT_PLAN.info(progress)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _rgb(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


ACCENT, ORBIT, OUTBOUND = _rgb(T.ACCENT), _rgb(T.ORBIT_RING), _rgb(T.OUTBOUND)
RETURN_RGB = _rgb(T.RETURN)
L1_RGB = _rgb(T.SUN)
SUNLINE_RGB = tuple(int(v * 0.55) for v in _rgb(T.SUN))


def _smooth(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _clamp01(t: float) -> float:
    return max(0.0, min(1.0, t))


def cubic(p0, p1, p2, p3, t: float):
    """Point on a cubic Bezier (works for 2D and 3D tuples)."""
    mt = 1 - t
    a, b, c, d = mt * mt * mt, 3 * mt * mt * t, 3 * mt * t * t, t * t * t
    return tuple(a * p0[i] + b * p1[i] + c * p2[i] + d * p3[i] for i in range(len(p0)))


def cubic_tangent(p0, p1, p2, p3, t: float):
    """Direction of travel along a cubic Bezier (unnormalised)."""
    mt = 1 - t
    a, b, c = 3 * mt * mt, 6 * mt * t, 3 * t * t
    return tuple(a * (p1[i] - p0[i]) + b * (p2[i] - p1[i]) + c * (p3[i] - p2[i])
                 for i in range(len(p0)))


def smooth_arc(start, start_dir, end, end_dir, pull: float = 0.45,
               start_cap: float | None = None, end_cap: float | None = None):
    """Cubic control points leaving `start` along `start_dir` and arriving
    at `end` travelling along `end_dir` — matched directions, no kinks.
    The caps limit how far each end runs straight before turning (keeps a
    long arc from overshooting a small orbit)."""
    span = math.dist(start, end)
    n0 = math.hypot(*start_dir) or 1.0
    n1 = math.hypot(*end_dir) or 1.0
    k0 = min(span * pull, start_cap) if start_cap else span * pull
    k1 = min(span * pull, end_cap) if end_cap else span * pull
    c1 = tuple(start[i] + start_dir[i] / n0 * k0 for i in range(len(start)))
    c2 = tuple(end[i] - end_dir[i] / n1 * k1 for i in range(len(end)))
    return start, c1, c2, end


@lru_cache(maxsize=64)
def _arc_table(arc) -> tuple[float, ...]:
    """Cumulative length (0..1) at 96 evenly spaced curve parameters."""
    pts = [cubic(*arc, i / 96) for i in range(97)]
    lengths = [0.0]
    for a, b in zip(pts, pts[1:]):
        lengths.append(lengths[-1] + math.dist(a, b))
    total = lengths[-1] or 1.0
    return tuple(v / total for v in lengths)


def even_t(arc, fraction: float) -> float:
    """Curve parameter at `fraction` of the arc's length. Bezier curves
    speed up and slow down along their parameter; using this the rocket
    moves at an even pace, so "50% of the way home" means halfway along
    the path in both the 3D view and the 2D map."""
    fraction = max(0.0, min(1.0, fraction))
    table = _arc_table(arc)
    lo, hi = 0, len(table) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if table[mid] < fraction:
            lo = mid
        else:
            hi = mid
    span = table[hi] - table[lo] or 1.0
    return (lo + (fraction - table[lo]) / span) / (len(table) - 1)


def along(arc, fraction: float):
    """(point, direction) at `fraction` of the arc's length."""
    t = even_t(arc, fraction)
    return cubic(*arc, t), cubic_tangent(*arc, max(t, 1e-4))


def _km(value: float) -> str:
    for scale, unit in ((1e9, "B km"), (1e6, "M km")):
        if value >= scale:
            return f"{value / scale:.2f}{unit}"
    return f"{value:,.0f} km"


class MissionViewport(ctk.CTkFrame):
    """Card holding the 3D view and the 2D transfer map side by side.

    They start at 50/50; the divider between them can be dragged, and each
    pane rescales its own contents to fit. Call `set_mission`, then
    `start()` while visible; `play()` / `finish()` / `abort()` follow the
    simulation."""

    def __init__(self, master) -> None:
        super().__init__(master, fg_color=T.BG, corner_radius=T.RADIUS,
                         border_width=1, border_color=T.BORDER)
        self.paned = tk.PanedWindow(self, orient="horizontal", height=HEIGHT, bd=0,
                                    bg=T.BORDER_STRONG, sashwidth=8, sashrelief="flat",
                                    sashpad=0, showhandle=False, opaqueresize=True,
                                    sashcursor="sb_h_double_arrow")
        self.paned.pack(fill="both", expand=True, padx=2, pady=2)
        self.canvas = tk.Canvas(self.paned, width=MIN_3D_WIDTH, height=HEIGHT, bg=T.BG,
                                highlightthickness=0, cursor="fleur")
        self.map = TransferMap(self.paned)
        self.paned.add(self.canvas, minsize=MIN_3D_WIDTH, stretch="always")
        self.paned.add(self.map, minsize=MIN_MAP_WIDTH, stretch="always")
        self._ratio = 0.5                 # 3D share of the width
        self._pane_width = 0
        self.paned.bind("<Configure>", self._keep_ratio, add="+")
        self.paned.bind("<ButtonRelease-1>", self._remember_ratio, add="+")
        self.renderer = Renderer(self.canvas)
        self.camera = Camera(fov_deg=FOV)
        self.yaw, self.pitch = 0.0, DEFAULT_PITCH
        self._drag: tuple[int, int] | None = None

        self.mission = None
        self.dest = EARTH
        self.plan = plan_for(None)
        self.mode = "idle"            # idle | flight | home | lost
        self.launch_ok = True
        self.flight_start = 0.0
        self.flight_len = self.plan.total
        self.particles: list[list] = []
        self._exploded = False
        self._after = None
        self._running = False
        self._t0 = time.monotonic()
        self._paused_at: float | None = None   # flight clock frozen while an
        self._pause_total = 0.0                #   event card is on screen
        self._size = (0, 0)
        self._hud_text: dict[str, str] = {}      # live readouts, shown on the map pane
        self._status_colour = T.TEXT_MUTED
        self._halos: list[tuple[int, str, float]] = []
        self._labels: list[tuple[int, tuple, float]] = []   # (item, 3D point, dy px)
        self._scene_key = (EARTH.id, None, self.plan)
        self.target = (0.0, 0.0, 0.0)
        self.dist = 20.0
        self._configure_scene()

        c = self.canvas
        c.bind("<Configure>", self._on_resize)
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._drag_view)
        c.bind("<ButtonRelease-1>", lambda _e: setattr(self, "_drag", None))
        c.bind("<Double-Button-1>", self._reset_view)
        self.bind("<Destroy>", lambda e: self.stop() if e.widget is self else None)

    # ==================================================================
    # Public API
    # ==================================================================
    def set_mission(self, mission) -> None:
        dest = (mission.destination if mission and mission.destination else EARTH)
        plan = plan_for(mission)
        orbit = mission.orbit if mission else None
        key = (dest.id, orbit.id if orbit else None, plan)
        self.mission = mission
        if key != self._scene_key:          # new destination, orbit or timeline
            self._scene_key = key
            self.dest = dest
            self.plan = plan
            self.flight_len = plan.total
            self._configure_scene()
            self._draw_static()
            self.map.set_scene(dest, plan, orbit)

    @property
    def kind(self) -> str:
        return self.plan.kind

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._tick()

    def stop(self) -> None:
        self._running = False
        if self._after is not None:
            try:
                self.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def play(self, duration_s: float, launch_success: bool) -> None:
        """Fly the mission over `duration_s` (matching the phase tracker)."""
        self.map.cancel_preview()
        self.mode = "flight"
        self.launch_ok = launch_success
        self.flight_start = self._now()
        self.flight_len = duration_s
        self.particles.clear()
        self._exploded = False

    def finish(self, success: bool) -> None:
        """Simulation done: landed (rocket gone) or lost after a failure."""
        self.mode = "home" if success else "lost"

    def _now(self) -> float:
        """Flight clock: wall time minus time spent paused."""
        t = self._paused_at if self._paused_at is not None else time.monotonic()
        return t - self._pause_total

    def pause(self) -> None:
        """Freeze the flight (rocket holds position)."""
        if self._paused_at is None:
            self._paused_at = time.monotonic()

    def resume(self) -> None:
        if self._paused_at is not None:
            self._pause_total += time.monotonic() - self._paused_at
            self._paused_at = None

    def abort(self) -> None:
        self.resume()
        self.mode = "idle"
        self.particles.clear()

    def preview_route(self, duration_s: float = 5.0) -> None:
        """Replay the full round trip on the transfer map (only on standby)."""
        if self.mode == "idle":
            self.map.preview(duration_s)

    def _keep_ratio(self, event) -> None:
        """Start at 50/50 and keep the player's chosen split when the
        window (and so the card) changes width."""
        if event.width == self._pane_width or event.width < MIN_3D_WIDTH + MIN_MAP_WIDTH:
            return
        self._pane_width = event.width
        x = int(event.width * self._ratio)
        x = max(MIN_3D_WIDTH, min(event.width - MIN_MAP_WIDTH, x))
        self.after_idle(lambda: self.paned.sash_place(0, x, 0))

    def _remember_ratio(self, _event) -> None:
        """The divider was dragged: remember the new split."""
        width = self.paned.winfo_width()
        if width > 1:
            self._ratio = self.paned.sash_coord(0)[0] / width

    # ==================================================================
    # Scene set-up
    # ==================================================================
    def _configure_scene(self) -> None:
        d = self.dest
        kind = self.kind
        self.R_e = P.radius_for(EARTH)
        self.earth_tilt = math.radians(P.AXIAL_TILT["earth"])
        self.rocket_scale = 0.22 * self.R_e
        orbit = self.mission.orbit if self.mission else None
        incl = orbit.inclination_deg if orbit else 28.0
        self.sun_end = None                     # end of the Sun–Earth line (L1 only)
        if kind == "l1":
            # A marked point (no world) circled by a small halo loop that
            # runs across the Sun–Earth line, tilted toward the camera
            self.R = 0.16 * self.R_e
            self.tilt, self.ring, self.ring_r = 0.0, None, 0.0
            self.orbit_r = 0.62 * self.R_e
            self.orbit_rot = matmul(rot_y(-0.6), rot_z(math.pi / 2))
        else:
            # Destination (Earth itself for Earth-orbit missions) at the
            # origin, with its orbit
            self.R = P.radius_for(d)
            self.tilt = math.radians(P.AXIAL_TILT.get(d.id, 0.0))
            self.ring = P.ring_mesh(d.id)
            self.ring_r = self.R * P.ring_outer(d.id) if self.ring else 0.0
            grow = 1.6 if kind == "earth" else 1.4
            self.orbit_r = max(self.R * grow + 0.5, self.ring_r * 1.12)
            self.orbit_rot = matmul(rot_z(self.tilt * 0.35),
                                    rot_x(math.radians(min(incl, 80.0))))
        if kind == "earth":
            self._configure_earth_orbit()
        else:
            self._configure_transfer()
        self.alt_km, self.v_orbit = self._orbit_numbers()
        self._fit_camera()

    def _configure_earth_orbit(self) -> None:
        """Earth-orbit mission: Earth at the origin. The rocket launches
        from a pad beneath the orbit, climbs into it at the point facing
        the camera (moving left to right), flies its laps and deorbits to a
        landing site a little further along the ground track."""
        self.earth = (0.0, 0.0, 0.0)
        front = normalize((0.0, 0.55, 0.85))
        self.theta0 = max((2 * math.pi * k / 120 for k in range(120)),
                          key=lambda th: sum(a * b for a, b in zip(self._orbit_pos(th), front)))
        self.orbit_dir = 1 if self._orbit_tangent(self.theta0, 1)[0] >= 0 else -1
        self.n_launch = normalize(self._orbit_pos(self.theta0 - self.orbit_dir * 0.85))
        self.n_land = normalize(self._orbit_pos(self.theta0 + self.orbit_dir * 0.85))
        half = 1.2 * self.rocket_scale
        self.pad_pos = mul(self.n_launch, self.R_e + half)
        self.land_pos = mul(self.n_land, self.R_e + half * 0.6)
        p_ins = self._orbit_pos(self.theta0)
        t_ins = self._orbit_tangent(self.theta0)
        self.outbound = tuple(map(tuple, smooth_arc(self.pad_pos, self.n_launch, p_ins, t_ins,
                                                    pull=0.5)))
        self.homeward = tuple(map(tuple, smooth_arc(p_ins, t_ins, self.land_pos,
                                                    mul(self.n_land, -1), pull=0.5)))

    def _configure_transfer(self) -> None:
        """Interplanetary (Earth on the left) or L1 (Earth on the right,
        the Sun off beyond the left edge)."""
        # Earth far enough out for the transfer arcs to read
        side = 1 if self.kind == "l1" else -1
        self.earth = (side * (self.orbit_r + 3.4 + 1.6 * self.R_e), -0.25 * self.R_e, 0.0)
        if self.kind == "l1":
            sunward = normalize(sub((0.0, 0.0, 0.0), self.earth))
            self.sun_end = mul(sunward, self.orbit_r + 2.2 * self.R_e)

        # Launch from Earth's upper side facing the target, land on its lower side
        self.n_launch = normalize((-side * 0.8, 0.55, 0.25))
        self.n_land = normalize((-side * 0.8, -0.55, 0.25))
        half = 1.2 * self.rocket_scale                # rocket centre sits this far up
        self.pad_pos = add(self.earth, mul(self.n_launch, self.R_e + half))
        self.land_pos = add(self.earth, mul(self.n_land, self.R_e + half * 0.6))

        # Insertion point: the orbit point facing Earth. Orbit direction is
        # chosen so the rocket arrives heading *down* — the return then
        # leaves underneath, below the outbound arc.
        toward = normalize(sub(self.earth, (0.0, 0.0, 0.0)))
        self.theta0 = max((2 * math.pi * k / 120 for k in range(120)),
                          key=lambda th: sum(a * b for a, b in zip(self._orbit_pos(th), toward)))
        t0 = self._orbit_tangent(self.theta0, 1)
        self.orbit_dir = 1 if t0[1] <= 0 else -1
        p_ins = self._orbit_pos(self.theta0)
        t_ins = self._orbit_tangent(self.theta0)
        cap = 1.6 * self.orbit_r
        self.outbound = tuple(map(tuple, smooth_arc(self.pad_pos, self.n_launch, p_ins, t_ins,
                                                    end_cap=cap)))
        self.homeward = tuple(map(tuple, smooth_arc(p_ins, t_ins, self.land_pos,
                                                    mul(self.n_land, -1), start_cap=cap)))

    def _orbit_numbers(self) -> tuple[float, float | None]:
        """Altitude: the mission orbit if it circles this world, else a
        400 km parking orbit. Speed: real circular velocity sqrt(GM/r)
        (none for the L1 halo loop, which isn't an orbit of a body)."""
        orbit = self.mission.orbit if self.mission else None
        alt = 400.0
        if orbit and orbit.body.lower() == self.dest.name.lower():
            alt = orbit.altitude_km
        if self.kind == "l1":
            return alt, None
        return alt, P.orbital_speed_km_s(self.dest, alt)

    def _orbit_pos(self, theta: float):
        r = self.orbit_r
        return apply(self.orbit_rot, (r * math.cos(theta), 0.0, r * math.sin(theta)))

    def _orbit_tangent(self, theta: float, direction: int | None = None):
        sign = self.orbit_dir if direction is None else direction
        return mul(apply(self.orbit_rot, (-math.sin(theta), 0.0, math.cos(theta))), sign)

    def _orbit_at(self, angle: float):
        """Position after travelling `angle` radians from the insertion point."""
        return self._orbit_pos(self.theta0 + self.orbit_dir * angle)

    # --- framing ------------------------------------------------------------
    def _scene_points(self):
        """(point, padding) pairs that must all be visible."""
        rocket_pad = 1.4 * self.rocket_scale
        pts = [(self.earth, self.R_e * 1.12),
               ((0.0, 0.0, 0.0), max(self.R * 1.08, self.ring_r * 1.02))]
        if self.sun_end is not None:                    # Sun–Earth line + its label
            pts.append((self.sun_end, 0.5 * self.R_e))
        pts += [(self._orbit_pos(2 * math.pi * k / 48), rocket_pad) for k in range(48)]
        for arc in (self.outbound, self.homeward):
            pts += [(along(arc, i / 32)[0], rocket_pad) for i in range(33)]
        return pts

    def _view(self, target, dist: float):
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        position = add(target, (dist * cp * math.sin(self.yaw), dist * sp,
                                dist * cp * math.cos(self.yaw)))
        return Camera(position=position, target=target, fov_deg=FOV)

    def _fits(self, target, dist: float, w: int, h: int, pts) -> bool:
        cam = self._view(target, dist)
        right, up, forward = cam.basis()
        focal = (h / 2) / math.tan(math.radians(FOV) / 2)
        margin = 14
        for p, pad in pts:
            d = sub(p, cam.position)
            z = d[0] * forward[0] + d[1] * forward[1] + d[2] * forward[2]
            if z <= pad + 0.2:
                return False
            x = w / 2 + focal * (d[0] * right[0] + d[1] * right[1] + d[2] * right[2]) / z
            y = h / 2 - focal * (d[0] * up[0] + d[1] * up[1] + d[2] * up[2]) / z
            r = focal * pad / z
            if x - r < margin or x + r > w - margin or y - r < margin or y + r > h - margin:
                return False
        return True

    def _fit_camera(self) -> None:
        """Aim at the middle of the scene and back off just far enough that
        Earth, the planet (and rings), the orbit and both paths all fit."""
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w < 10 or h < 10:
            w, h = MIN_3D_WIDTH * 2, HEIGHT
        pts = self._scene_points()
        xs = [p[0] - r for p, r in pts] + [p[0] + r for p, r in pts]
        ys = [p[1] - r for p, r in pts] + [p[1] + r for p, r in pts]
        self.target = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, 0.0)
        lo, hi = 2.0, 400.0
        for _ in range(28):
            mid = (lo + hi) / 2
            if self._fits(self.target, mid, w, h, pts):
                hi = mid
            else:
                lo = mid
        self.dist = hi

    # ==================================================================
    # Frame loop
    # ==================================================================
    def _tick(self) -> None:
        if not self._running:
            return
        began = time.perf_counter()
        try:
            if self.canvas.winfo_viewable():
                self._frame()
        except tk.TclError:
            return
        spent = int((time.perf_counter() - began) * 1000)
        self._after = self.after(max(8, FPS_MS - spent), self._tick)

    def _frame(self) -> None:
        now = self._now()
        clock = now - self._t0
        self.camera = self._view(self.target, self.dist)

        # --- the two worlds -----------------------------------------------------
        spin = clock * 0.12
        instances = [Instance(P.planet_mesh("earth"),
                              matmul(rot_z(self.earth_tilt), rot_y(spin * 1.4)),
                              self.earth, self.R_e)]
        if self.kind == "interplanetary":
            instances.append(Instance(P.planet_mesh(self.dest.id),
                                      matmul(rot_z(self.tilt), rot_y(spin)), scale=self.R))
        if self.ring is not None:
            instances.append(Instance(self.ring, rot_z(self.tilt), scale=self.R))

        # --- rocket --------------------------------------------------------
        pos, heading, state, info = self._rocket(now, clock)
        if pos is not None:
            roll = clock * 0.4 if self.mode == "idle" else 0.0
            instances.append(Instance(build_rocket(state), align_y(heading, roll), pos,
                                      self.rocket_scale))

        # --- lines: orbit, planned paths, velocity vector ----------------------
        segments = []
        n = 72
        for k in range(0, n, 2):
            a, b = self._orbit_pos(2 * math.pi * k / n), self._orbit_pos(2 * math.pi * (k + 1) / n)
            segments.append((a, b, ORBIT, 1.4))
        if self.kind == "l1":
            segments += self._l1_marker()
        flying = self.mode in ("idle", "flight") and info["phase"] not in ("lost", "home")
        if flying and info["phase"] in ("standby", "launch", "cruise"):
            segments += self._dashed_arc(self.outbound, info["curve"], OUTBOUND)
        if flying:
            segments += self._dashed_arc(self.homeward, info["ret"], RETURN_RGB)
        if pos is not None and self.mode != "home":
            tip = add(pos, mul(heading, 3.2 * self.rocket_scale))
            segments.append((pos, tip, ACCENT, 2.2))
            side = normalize((heading[2], 0.0, -heading[0])) if abs(heading[1]) < 0.95 else (1, 0, 0)
            back = add(tip, mul(heading, -0.7 * self.rocket_scale))
            for sgn in (1, -1):
                segments.append((tip, add(back, mul(side, sgn * 0.4 * self.rocket_scale)),
                                 ACCENT, 2.0))

        # --- explosion debris -----------------------------------------------
        dt = 1 / 30
        alive = []
        for p in self.particles:
            p[0] = add(p[0], mul(p[1], dt))
            p[1] = mul(p[1], 0.96)
            p[3] -= dt
            if p[3] > 0:
                k = p[3] / p[4]
                colour = tuple(int(v * (0.25 + 0.75 * k)) for v in p[2])
                segments.append((p[0], add(p[0], mul(normalize(p[1]), 0.6 * self.rocket_scale * k + 0.01)),
                                 colour, 2 + 4 * k))
                alive.append(p)
        self.particles = alive

        self.renderer.render(self.camera, instances, segments)
        self._update_halos()
        self._update_hud(info, heading)
        self.map.update_marker(info, standby=self.mode == "idle")

    def _l1_marker(self) -> list:
        """The L1 point: a diamond facing the camera, plus the dashed
        Sun–Earth line it sits on."""
        right, up, _forward = self.camera.basis()
        r = self.R
        tips = [mul(right, r), mul(up, r), mul(right, -r), mul(up, -r)]
        out = [(tips[i], tips[(i + 1) % 4], L1_RGB, 2.4) for i in range(4)]
        out.append((mul(right, -0.35 * r), mul(right, 0.35 * r), L1_RGB, 2.0))
        steps = 30
        a, b = self.earth, self.sun_end
        for k in range(0, steps, 2):
            out.append((lerp(a, b, k / steps), lerp(a, b, (k + 1) / steps), SUNLINE_RGB, 1.0))
        return out

    @staticmethod
    def _dashed_arc(arc, start: float, colour, steps: int = 44):
        """Dashed remainder of a planned path, from `start` to its end."""
        out = []
        for k in range(0, steps, 2):
            ta = start + (1 - start) * k / steps
            tb = start + (1 - start) * (k + 1) / steps
            out.append((along(arc, ta)[0], along(arc, tb)[0], colour, 1.3))
        return out

    def _rocket(self, now: float, clock: float):
        """Rocket position, heading, state and HUD info for this frame
        (position None = not drawn: exploded, or landed and gone)."""
        flicker = (math.sin(clock * 37) + 1) / 2
        if self.mode == "idle":
            info = {"phase": "standby", "curve": 0.0, "ret": 0.0, "u": 0.0}
            return self.pad_pos, self.n_launch, RocketState(flicker=flicker), info
        if self.mode == "lost":
            return None, self.n_launch, None, {"phase": "lost", "curve": 0.0, "ret": 0.0}
        if self.mode == "home":
            return None, self.n_land, None, {"phase": "home", "curve": 1.0, "ret": 1.0}

        tau = _clamp01((now - self.flight_start) / self.flight_len)
        info = self.plan.info(tau)
        phase, u = info["phase"], info["u"]
        earth_orbit = self.kind == "earth"
        if phase == "launch":
            pos, tangent = along(self.outbound, info["curve"])
            heading = normalize(lerp(self.n_launch, normalize(tangent), _smooth(u)))
            top_speed = (self.v_orbit or 7.8) if earth_orbit else 11.2
            info.update(speed=top_speed * _smooth(u), alt=min(200.0, self.alt_km) * u * u)
            if not self.launch_ok and u >= 0.5:
                if not self._exploded:
                    self._explode(pos)
                info["phase"] = "lost"
                return None, heading, None, info
            state = RocketState(boosters=_clamp01((u - 0.55) / 0.45) if u > 0.55 else 0.0,
                                flame=1.0, booster_flame=1.0 if u < 0.55 else 0.0,
                                flicker=flicker)
            return pos, heading, state, info
        if not self.launch_ok:
            return None, self.n_launch, None, {"phase": "lost", "curve": 0.0, "ret": 0.0}
        if phase == "cruise":
            c = info["curve"]
            k = (c - LAUNCH_SHARE) / (1 - LAUNCH_SHARE)
            if earth_orbit:                       # climbing to the mission altitude
                start = min(200.0, self.alt_km)
                info["alt"] = start + (self.alt_km - start) * k
            info["range"] = self.dest.distance_from_earth_km * (1 - k)
            state = RocketState(boosters=1.0, arrays=_clamp01((u - 0.1) / 0.4),
                                dish=_clamp01((u - 0.45) / 0.4),
                                flame=0.5 if u > 0.88 else 0.0, flicker=flicker)
            pos, tangent = along(self.outbound, c)
            return pos, normalize(tangent), state, info
        deployed = RocketState(boosters=1.0, arrays=1.0, dish=1.0, flicker=flicker)
        if phase == "ops":
            theta = self.theta0 + self.orbit_dir * info["orbit_angle"]
            return self._orbit_pos(theta), normalize(self._orbit_tangent(theta)), deployed, info
        # Return: along the homeward arc; the rocket vanishes as it lands
        t = info["ret"]
        info["range"] = (self.alt_km if earth_orbit
                         else self.dest.distance_from_earth_km) * (1 - t)
        if t >= 0.995:
            return None, self.n_land, None, info
        deployed.flame = 0.6 if t < 0.12 else 0.0                    # escape burn
        pos, tangent = along(self.homeward, t)
        return pos, normalize(tangent), deployed, info

    def _explode(self, at) -> None:
        self._exploded = True
        rng = random.Random(7)
        palette = [(253, 224, 120), (249, 115, 22), (239, 68, 68), (180, 180, 190)]
        for _ in range(42):
            v = normalize((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
            speed = rng.uniform(0.6, 2.4) * self.R_e
            life = rng.uniform(0.8, 1.6)
            self.particles.append([at, mul(v, speed), rng.choice(palette), life, life])

    # ==================================================================
    # Static layers + HUD
    # ==================================================================
    def _on_resize(self, event) -> None:
        if (event.width, event.height) != self._size:
            self._size = (event.width, event.height)
            self._fit_camera()
            self._draw_static()

    def _draw_static(self) -> None:
        """Stars, atmosphere halos (positioned each frame) and the hint."""
        c = self.canvas
        w, h = max(2, c.winfo_width()), max(2, c.winfo_height())
        for tag in ("star", "halo", "hud"):
            c.delete(tag)
        draw_stars(c, w, h, count=max(80, w * h // 2200), seed=5, tag="star")
        self._halos = []
        bg = _rgb(T.BG)
        for body in dict.fromkeys(("earth", self.dest.id)):
            colour = P.HALO.get(body)
            if not colour:
                continue
            for grow, mixk in ((2, 0.55), (5, 0.32), (9, 0.16), (14, 0.07)):
                col = tuple(int(bg[i] + (colour[i] - bg[i]) * mixk) for i in range(3))
                item = c.create_oval(0, 0, 0, 0, outline="#%02x%02x%02x" % col, width=4,
                                     tags="halo")
                self._halos.append((item, body, grow))
        c.tag_lower("halo")
        c.tag_lower("star")
        c.delete("label3d")
        self._labels = []
        if self.kind == "l1":
            f = T.canvas_font(10, bold=True)
            self._labels.append((c.create_text(0, 0, text="L1", fill=T.SUN, font=f,
                                               tags="label3d"), (0.0, 0.0, 0.0), -16.0))
            self._labels.append((c.create_text(0, 0, text="TO THE SUN", fill=T.TEXT_DIM,
                                               font=T.canvas_font(9, bold=True),
                                               tags="label3d"), self.sun_end, -12.0))
        c.create_text(w - 22, h - 16, anchor="se", fill=T.TEXT_DIM, tags="hud",
                      width=max(100, w - 44), font=T.canvas_font(10),
                      text="Drag to rotate  ·  double-click to reset")
        c.tag_raise("hud")

    def _project(self, point):
        """Screen (x, y, depth) of a scene point for the current camera."""
        c = self.canvas
        w, h = c.winfo_width(), c.winfo_height()
        right, up, forward = self.camera.basis()
        focal = (h / 2) / math.tan(math.radians(FOV) / 2)
        d = sub(point, self.camera.position)
        z = d[0] * forward[0] + d[1] * forward[1] + d[2] * forward[2]
        if z <= 1e-6:
            return None
        return (w / 2 + focal * (d[0] * right[0] + d[1] * right[1] + d[2] * right[2]) / z,
                h / 2 - focal * (d[0] * up[0] + d[1] * up[1] + d[2] * up[2]) / z, z)

    def _update_labels(self) -> None:
        """Keep the 3D scene's text labels on their points."""
        for item, point, dy in self._labels:
            spot = self._project(point)
            if spot is None:
                self.canvas.itemconfigure(item, state="hidden")
                continue
            self.canvas.coords(item, spot[0], spot[1] + dy)
            self.canvas.itemconfigure(item, state="normal")
            self.canvas.tag_raise(item)

    def _update_halos(self) -> None:
        """Keep each atmosphere glow centred on its (moving) planet."""
        self._update_labels()
        if not self._halos:
            return
        c = self.canvas
        w, h = c.winfo_width(), c.winfo_height()
        right, up, forward = self.camera.basis()
        focal = (h / 2) / math.tan(math.radians(FOV) / 2)
        spheres = {self.dest.id: ((0.0, 0.0, 0.0), self.R), "earth": (self.earth, self.R_e)}
        placed = {}
        for body, (centre, radius) in spheres.items():
            d = sub(centre, self.camera.position)
            z = d[0] * forward[0] + d[1] * forward[1] + d[2] * forward[2]
            if z <= radius:
                placed[body] = None
                continue
            x = w / 2 + focal * (d[0] * right[0] + d[1] * right[1] + d[2] * right[2]) / z
            y = h / 2 - focal * (d[0] * up[0] + d[1] * up[1] + d[2] * up[2]) / z
            placed[body] = (x, y, focal * radius / math.sqrt(max(1e-6, z * z - radius * radius)))
        for item, body, grow in self._halos:
            spot = placed.get(body)
            if spot is None:
                c.itemconfigure(item, state="hidden")
                continue
            x, y, r = spot
            r += grow
            c.coords(item, x - r, y - r, x + r, y + r)
            c.itemconfigure(item, state="normal")

    def _set(self, key: str, value: str, colour: str | None = None) -> None:
        self._hud_text[key] = value
        if colour is not None:
            self._status_colour = colour

    def _update_hud(self, info: dict, heading) -> None:
        self._update_hud_text(info, heading)
        self.map.set_readouts(self._hud_text, self._status_colour)

    def _status(self, phase: str, u: float, lap: int) -> tuple[str, str]:
        """Status line (text, colour) for a phase, worded for the mission kind."""
        kind, loops = self.kind, self.plan.loops
        if phase == "cruise":
            lead = {"earth": "ASCENT", "l1": "CRUISE TO L1"}.get(kind, "CRUISE")
            last = {"l1": "HALO ORBIT INSERTION"}.get(kind, "ORBIT INSERTION BURN")
            return (f"{lead} — deploying solar arrays" if u < 0.45
                    else f"{lead} — unfurling comms dish" if u < 0.88 else last), T.ACCENT
        if phase == "ops":
            if kind == "l1":
                return f"STATION-KEEPING AT L1 — loop {lap}/{loops}", T.SUCCESS
            return f"SCIENCE OPERATIONS — orbit {lap}/{loops}", T.SUCCESS
        if phase == "return":
            if kind == "earth":
                return ("DEORBIT BURN" if u < 0.12
                        else "RE-ENTRY — descending to the landing site"), T.ACCENT
            return ("LEAVING L1" if kind == "l1" else "DEPARTING ORBIT") if u < 0.12 \
                else "RETURN CRUISE — heading home", T.ACCENT
        return {
            "standby": ("STANDBY — awaiting launch", T.TEXT_MUTED),
            "launch": ("LIFT-OFF — boosters firing" if u < 0.55 else "BOOSTER SEPARATION",
                       T.WARNING),
            "home": ("BACK ON EARTH — mission complete", T.SUCCESS),
            "lost": ("LOSS OF SIGNAL — launch failure", T.DANGER),
        }[phase]

    def _update_hud_text(self, info: dict, heading) -> None:
        phase = info["phase"]
        u = info.get("u", 0.0)
        status = self._status(phase, u, info.get("lap", 1))
        self._set("status", status[0], status[1])
        if phase in ("lost", "home"):
            for key in ("vector", "range", "speed", "deploy"):
                self._set(key, "")
            return
        az = math.degrees(math.atan2(heading[0], heading[2])) % 360
        el = math.degrees(math.asin(max(-1.0, min(1.0, heading[1]))))
        self._set("vector", f"APPROACH VECTOR  az {az:5.1f}°   el {el:+5.1f}°")
        earth_orbit = self.kind == "earth"
        if phase == "standby":
            self._set("range", f"TARGET ALTITUDE {self.alt_km:,.0f} km" if earth_orbit
                      else f"RANGE           {_km(self.dest.distance_from_earth_km)}")
            self._set("speed", "SPEED           0.0 km/s")
            self._set("deploy", "ARRAYS STOWED · DISH STOWED")
        elif phase == "launch":
            self._set("range", f"ALTITUDE        {info['alt']:,.0f} km")
            self._set("speed", f"SPEED           {info['speed']:.1f} km/s")
            self._set("deploy", "ARRAYS STOWED · DISH STOWED")
        elif phase == "cruise":
            if earth_orbit:
                self._set("range", f"ALTITUDE        {info['alt']:,.0f} km")
                self._set("speed", "SPEED           climbing")
            else:
                self._set("range", f"RANGE           {_km(max(0.0, info['range']))}")
                self._set("speed", "SPEED           coasting")
            arrays, dish = _clamp01((u - 0.1) / 0.4), _clamp01((u - 0.45) / 0.4)
            self._set("deploy", f"ARRAYS {arrays:4.0%} · DISH {dish:4.0%}")
        elif phase == "return":
            if earth_orbit:
                self._set("range", f"ALTITUDE        {max(0.0, info['range']):,.0f} km")
                self._set("speed", "SPEED           deorbit burn" if u < 0.12
                          else "SPEED           re-entry")
            else:
                self._set("range", f"RANGE TO EARTH  {_km(max(0.0, info['range']))}")
                self._set("speed", "SPEED           escape burn" if u < 0.12
                          else "SPEED           coasting")
            self._set("deploy", "ARRAYS 100% · DISH 100%")
        elif self.kind == "l1":
            self._set("range", f"RANGE TO EARTH  {_km(self.dest.distance_from_earth_km)}")
            self._set("speed", "SPEED           holding station")
        else:
            self._set("range", f"ALTITUDE        {self.alt_km:,.0f} km")
            speed = f"{self.v_orbit:.2f} km/s" if self.v_orbit else "—"
            self._set("speed", f"ORBITAL SPEED   {speed}")
            self._set("deploy", "ARRAYS 100% · DISH 100%")

    # ==================================================================
    # Camera interaction
    # ==================================================================
    def _press(self, event) -> None:
        self._drag = (event.x, event.y)

    def _drag_view(self, event) -> None:
        if self._drag is None:
            return
        dx, dy = event.x - self._drag[0], event.y - self._drag[1]
        self._drag = (event.x, event.y)
        self.yaw -= dx * 0.008
        self.pitch = max(-0.35, min(1.25, self.pitch + dy * 0.006))
        self._fit_camera()          # keep everything in frame from the new angle

    def _reset_view(self, _event=None) -> None:
        self.yaw, self.pitch = 0.0, DEFAULT_PITCH
        self._fit_camera()


# ==========================================================================
# 2D transfer map pane
# ==========================================================================
READOUT_KEYS = ("vector", "range", "speed", "deploy")
# Longest texts each readout row can show, keyed like READOUT_KEYS. The
# panel measures these (wrapped at its current width) to size each row.
READOUT_TEMPLATES = {
    "vector": ("APPROACH VECTOR  az 360.0°   el +90.0°",),
    "range": ("RANGE           999.99M km", "ALTITUDE        99,999 km",
              "RANGE TO EARTH  999.99M km", "TARGET ALTITUDE 99,999 km"),
    "speed": ("ORBITAL SPEED   42.45 km/s", "SPEED           coasting",
              "SPEED           holding station"),
    "deploy": ("ARRAYS STOWED · DISH STOWED", "ARRAYS 100% · DISH 100%"),
}
STATUS_TEMPLATES = ("STANDBY — awaiting launch", "LIFT-OFF — boosters firing",
                    "CRUISE — deploying solar arrays", "CRUISE — unfurling comms dish",
                    "SCIENCE OPERATIONS — orbit 3/3", "LOSS OF SIGNAL — launch failure",
                    "RETURN CRUISE — heading home", "BACK ON EARTH — mission complete",
                    "CRUISE TO L1 — deploying solar arrays", "STATION-KEEPING AT L1 — loop 3/3",
                    "RE-ENTRY — descending to the landing site")


class TransferMap(tk.Canvas):
    """2D map of the flight with the live readouts, one layout per kind:

      interplanetary  Sun -> Earth -> destination. Launch from Earth's upper
                      right, a smooth arc into the parking orbit (arriving
                      downward, along the orbit), the laps, then a smooth arc
                      home underneath that lands on Earth's lower right.
      l1              Sun <- L1 <- Earth (schematic, not to scale): the
                      mirror image — Earth on the right, out to the halo loop
                      on the Sun–Earth line, back underneath.
      earth           Earth with the mission orbit around it: lift off from
                      the upper left, insert at the top heading right, laps,
                      deorbit and land on the upper right.

    It is the same flight as the 3D view, laid out the same way, and the
    marker is placed by the shared `FlightPlan.info`, so it is always at
    the same point of the trip as the 3D rocket.

    Layout, recomputed whenever the pane is resized:
      * header: title on the left, compact readout panel top-right (it
        drops below the title instead when the pane is too narrow, so it
        can never sit on top of the map);
      * legend along the bottom;
      * the map in the space left over, centred and scaled to fill 95% of
        it (in whichever direction runs out first).
    """

    PAD = 14
    FILL = 0.95

    def __init__(self, master) -> None:
        super().__init__(master, width=MIN_MAP_WIDTH, height=HEIGHT, bg=T.SURFACE,
                         highlightthickness=0)
        self.dest = EARTH
        self.plan = plan_for(None)
        self.orbit = None
        self._geo: dict = {}
        self._images: list = []
        self._preview: tuple[float, float] | None = None
        self._size = (0, 0)
        self._ro: dict[str, int] = {}
        self._ro_text: dict[str, str] = {}
        self._ro_colour = ""
        self.bind("<Configure>", self._on_resize)

    # --- public --------------------------------------------------------------
    def set_scene(self, dest, plan: FlightPlan, orbit=None) -> None:
        self.dest, self.plan, self.orbit = dest, plan, orbit
        self.redraw()

    def set_destination(self, dest) -> None:
        self.set_scene(dest, self.plan, self.orbit)

    @property
    def kind(self) -> str:
        return self.plan.kind

    def _titles(self) -> tuple[str, str]:
        if self.kind == "earth":
            orbit = self.orbit
            where = (f"{orbit.name}  ·  {orbit.altitude_km:,.0f} km up" if orbit
                     else "Earth orbit")
            return "ORBIT MAP", where
        if self.kind == "l1":
            return "TRANSFER MAP", "Earth → Sun–Earth L1  ·  ~1.5 million km (not to scale)"
        return "TRANSFER MAP", (f"Earth → {self.dest.name}  ·  "
                                f"{self.dest.distance_label.split(' from ')[0]}")

    def preview(self, duration_s: float) -> None:
        self._preview = (time.monotonic(), duration_s)

    def cancel_preview(self) -> None:
        self._preview = None

    def set_readouts(self, texts: dict[str, str], status_colour: str) -> None:
        """Update the readout panel (only items whose text changed)."""
        for key in ("status",) + READOUT_KEYS:
            value = texts.get(key, "")
            if key in self._ro and self._ro_text.get(key) != value:
                self._ro_text[key] = value
                self.itemconfigure(self._ro[key], text=value)
        if "status" in self._ro and status_colour != self._ro_colour:
            self._ro_colour = status_colour
            self.itemconfigure(self._ro["status"], fill=status_colour)

    # --- layout --------------------------------------------------------------
    def _on_resize(self, event) -> None:
        if (event.width, event.height) != self._size:
            self._size = (event.width, event.height)
            self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        self._images.clear()
        self._geo = {}
        self._ro.clear()
        self._ro_text.clear()
        self._ro_colour = ""
        w, h = self.winfo_width(), self.winfo_height()
        if w < 60 or h < 120:
            return
        pad = self.PAD

        # --- readout panel: fixed size, so live values never shift layout ---
        f_title, f_status = T.canvas_font(10, bold=True), T.canvas_font(12, bold=True)
        f_mono = (T.MONO_FAMILY, 10)
        mono = tkfont.Font(font=f_mono)
        widest = max(mono.measure(t) for ts in READOUT_TEMPLATES.values() for t in ts)
        panel_w = min(widest + 24, w - 2 * pad)
        text_w = panel_w - 24
        side_by_side = w - 2 * pad - panel_w - 16 >= 150
        title_w = (w - 2 * pad - panel_w - 16) if side_by_side else (w - 2 * pad)

        # --- title block (left) ---
        heading, subtitle = self._titles()
        title = self.create_text(pad, pad, anchor="nw", text=heading, fill=T.ACCENT,
                                 font=T.canvas_font(11, bold=True))
        sub = self.create_text(pad, self.bbox(title)[3] + 4, anchor="nw", width=title_w,
                               fill=T.TEXT_MUTED, font=T.canvas_font(10), text=subtitle)
        title_bottom = self.bbox(sub)[3]

        # --- readout panel (top-right, or under the title when narrow) ---
        px = w - pad - panel_w
        py = pad if side_by_side else title_bottom + 10
        panel = self.create_rectangle(px, py, px + panel_w, py + 10, fill=T.BG,
                                      outline=T.BORDER_STRONG)
        x, y = px + 12, py + 10
        head = self.create_text(x, y, anchor="nw", text="MISSION STATUS", fill=T.ACCENT,
                                font=f_title)
        y = self.bbox(head)[3] + 6

        def reserve(key: str, font, samples) -> None:
            """Create the row, then give it the height of its tallest
            (most-wrapped) possible text at this width."""
            nonlocal y
            item = self.create_text(x, y, anchor="nw", width=text_w, font=font,
                                    fill=T.TEXT_MUTED)
            tallest = 0
            for sample in samples:
                self.itemconfigure(item, text=sample)
                bb = self.bbox(item)
                tallest = max(tallest, bb[3] - bb[1])
            self.itemconfigure(item, text="")
            self._ro[key] = item
            y += tallest + 3

        reserve("status", f_status, STATUS_TEMPLATES)
        y += 4
        for key in READOUT_KEYS:
            reserve(key, f_mono, READOUT_TEMPLATES[key])
        panel_bottom = y + 6
        self.coords(panel, px, py, px + panel_w, panel_bottom)
        header_bottom = max(title_bottom, panel_bottom)

        # --- legend (bottom, wraps onto extra rows when narrow) ---
        legend_font = tkfont.Font(family=T.FONT_FAMILY, size=10)
        names = {"earth": ("Ascent", "Deorbit", "Mission orbit"),
                 "l1": ("Outbound", "Return", "Halo orbit")}.get(
            self.kind, ("Outbound", "Return", "Parking orbit"))
        items = ((names[0], T.OUTBOUND, (6, 4)), (names[1], T.RETURN, (6, 4)),
                 (names[2], T.ORBIT_RING, (3, 3)))
        rows, row, lx = [], [], pad
        for label, colour, dash in items:
            width = 30 + 8 + legend_font.measure(label)
            if row and lx + width > w - pad:
                rows.append(row)
                row, lx = [], pad
            row.append((lx, label, colour, dash))
            lx += width + 18
        rows.append(row)
        legend_top = h - pad - 16 * len(rows)
        for r, entries in enumerate(rows):
            ly = legend_top + 16 * r + 6
            for lx, label, colour, dash in entries:
                self.create_line(lx, ly, lx + 30, ly, fill=colour, width=2, dash=dash)
                self.create_text(lx + 38, ly, anchor="w", text=label, fill=T.TEXT_MUTED,
                                 font=T.canvas_font(10))

        # --- the map: centred in what's left, filling 95% of it ---
        region = (pad, header_bottom + 10, w - pad, legend_top - 10)
        if region[3] - region[1] < 40:
            return
        self._fit_map(region)

    def _fit_map(self, region) -> None:
        """Draw at a trial scale, measure the real bounding box (labels and
        all), rescale, repeat; then centre it in `region`."""
        rx0, ry0, rx1, ry1 = region
        target_w, target_h = (rx1 - rx0) * self.FILL, (ry1 - ry0) * self.FILL
        scale = 1.0
        for _ in range(5):
            self._draw_map(scale, 0.0, 0.0)
            bx0, by0, bx1, by1 = self.bbox("map")
            k = min(target_w / max(1, bx1 - bx0), target_h / max(1, by1 - by0))
            if abs(k - 1) < 0.005:
                break
            scale *= k
        self._draw_map(scale, 0.0, 0.0)
        bx0, by0, bx1, by1 = self.bbox("map")
        dx = (rx0 + rx1) / 2 - (bx0 + bx1) / 2
        dy = (ry0 + ry1) / 2 - (by0 + by1) / 2
        self._draw_map(scale, dx, dy)

    def _layout(self) -> dict:
        """Map geometry for the mission kind, in abstract units (screen y
        points down). Keys: bodies [(planet, centre, radius)], sun (centre
        or None), l1 (centre or None), outbound / homeward (cubic control
        points), centre / rx / ry of the orbit, and a0 / turn: the orbit
        angle at insertion and its direction (marker = centre +
        (rx cos a, ry sin a), a = a0 + turn * angle)."""
        r_sun, r_earth = 9.0, 12.0
        if self.kind == "earth":
            r_earth = 26.0
            earth = (0.0, 0.0)
            rx, ry = r_earth * 1.95, r_earth * 1.32
            ins = (earth[0], earth[1] - ry)              # top of the orbit, heading right
            n_launch, n_land = (-0.6, -0.8), (0.6, -0.8)
            pad = (earth[0] + n_launch[0] * r_earth, earth[1] + n_launch[1] * r_earth)
            land = (earth[0] + n_land[0] * r_earth, earth[1] + n_land[1] * r_earth)
            return dict(bodies=[(EARTH, earth, r_earth)], sun=None, l1=None,
                        outbound=smooth_arc(pad, n_launch, ins, (1.0, 0.0), pull=0.5),
                        homeward=smooth_arc(ins, (1.0, 0.0), land,
                                            (-n_land[0], -n_land[1]), pull=0.5),
                        centre=earth, rx=rx, ry=ry, a0=-math.pi / 2, turn=1.0)
        if self.kind == "l1":
            sun, l1, earth = (0.0, 0.0), (96.0, -2.0), (170.0, 8.0)
            rx, ry = 10.0, 17.0                          # halo loop across the line
            ins = (l1[0] + rx, l1[1])                    # side facing Earth, heading down
            n_launch, n_land = (-0.8, -0.6), (-0.8, 0.6)
            pad = (earth[0] + n_launch[0] * r_earth, earth[1] + n_launch[1] * r_earth)
            land = (earth[0] + n_land[0] * r_earth, earth[1] + n_land[1] * r_earth)
            cap = 2.2 * ry
            return dict(bodies=[(EARTH, earth, r_earth)], sun=sun, l1=l1,
                        outbound=smooth_arc(pad, n_launch, ins, (0.0, 1.0), end_cap=cap),
                        homeward=smooth_arc(ins, (0.0, 1.0), land,
                                            (-n_land[0], -n_land[1]), start_cap=cap),
                        centre=l1, rx=rx, ry=ry, a0=0.0, turn=1.0)
        r_dest = max(6.0, min(22.0, self.dest.radius_px / 14 * 9))
        rx = r_dest + 14.0
        ry = rx * 0.45
        span = 90.0 if self.dest.id == "moon" else 90.0 + 300.0 * map_fraction(self.dest)
        sun = (0.0, 0.0)
        earth = (44.0, 10.0)
        dest = (earth[0] + span, -8.0)
        intercept = (dest[0] - rx, dest[1])
        # Launch from Earth's upper right, land lower right
        n_launch, n_land = (0.8, -0.6), (0.8, 0.6)
        pad = (earth[0] + n_launch[0] * r_earth, earth[1] + n_launch[1] * r_earth)
        land = (earth[0] + n_land[0] * r_earth, earth[1] + n_land[1] * r_earth)
        down = (0.0, 1.0)                     # orbit direction at the insertion point
        cap = 2.2 * rx                          # turn into / out of the orbit promptly
        return dict(bodies=[(EARTH, earth, r_earth), (self.dest, dest, r_dest)], sun=sun,
                    l1=None,
                    outbound=smooth_arc(pad, n_launch, intercept, down, end_cap=cap),
                    homeward=smooth_arc(intercept, down, land, (-n_land[0], -n_land[1]),
                                        start_cap=cap),
                    centre=dest, rx=rx, ry=ry, a0=math.pi, turn=-1.0)

    def _draw_map(self, s: float, ox: float, oy: float) -> None:
        """Map geometry in abstract units, scaled by `s` and offset."""
        self.delete("map", "marker")
        self._images.clear()

        def at(p):
            return (ox + p[0] * s, oy + p[1] * s)

        g = self._layout()
        outbound, homeward = g["outbound"], g["homeward"]
        centre, rx, ry = g["centre"], g["rx"], g["ry"]
        r_sun = 9.0

        def line(points, colour, dash, width=2.0):
            self.create_line(*[v for pt in points for v in at(pt)], fill=colour, dash=dash,
                             width=width, tags="map")

        if g["l1"] is not None:                   # the Sun–Earth line L1 sits on
            line([g["sun"], g["bodies"][0][1]], T.BORDER_STRONG, (2, 4), 1.0)
        line([(centre[0] + rx * math.cos(a), centre[1] + ry * math.sin(a))
              for a in (2 * math.pi * i / 60 for i in range(61))], T.ORBIT_RING, (3, 3), 1.4)

        if g["sun"] is not None:
            cx, cy = at(g["sun"])
            for grow, colour in ((6.0, "#2A2208"), (3.0, "#5C4A12"), (0.0, T.SUN)):
                r = (r_sun + grow) * s
                self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=colour, outline="",
                                 tags="map")
            if g["l1"] is not None:
                self.create_text(cx, cy + (r_sun + 10) * s, text="Sun", fill=T.TEXT_MUTED,
                                 font=T.canvas_font(10, bold=True), tags="map")
        for planet, pt, r in g["bodies"]:
            px, py = at(pt)
            rr = r * s
            img = assets.canvas_photo(assets.PLANET_DIR / f"{planet.id}.png", max(4, int(2 * rr)))
            if img:
                self._images.append(img)
                self.create_image(px, py, image=img, tags="map")
            else:
                self.create_oval(px - rr, py - rr, px + rr, py + rr, fill=planet.color,
                                 outline="", tags="map")
            self.create_text(px, py + rr + 10, text=planet.name, fill=T.TEXT_MUTED,
                             font=T.canvas_font(10, bold=True), tags="map")
        if g["l1"] is not None:                   # the L1 point itself
            px, py = at(g["l1"])
            d = max(4.0, 4.5 * s)
            self.create_polygon(px, py - d, px + d, py, px, py + d, px - d, py, fill=T.SUN,
                                outline="", tags="map")
            self.create_text(px, py - ry * s - 10, text="L1", fill=T.SUN,
                             font=T.canvas_font(10, bold=True), tags="map")
        # Paths on top of the bodies (the Earth-orbit ascent starts on Earth)
        line([cubic(*homeward, i / 80) for i in range(81)], T.RETURN, (6, 4), 1.6)
        line([cubic(*outbound, i / 80) for i in range(81)], T.OUTBOUND, (6, 4))

        r_m = max(4.0, min(7.0, 5 * s))     # marker stays small on big maps
        halo = self.create_oval(0, 0, 0, 0, outline=T.ACCENT, width=2, state="hidden",
                                tags="marker")
        dot = self.create_oval(0, 0, 0, 0, fill=T.TEXT, outline="", state="hidden",
                               tags="marker")
        self._geo = dict(outbound=tuple(at(p) for p in outbound),
                         homeward=tuple(at(p) for p in homeward),
                         dest=at(centre), rx=rx * s, ry=ry * s, a0=g["a0"], turn=g["turn"],
                         dot=dot, halo=halo, r=r_m)

    def _orbit_point(self, angle: float):
        """Orbit position after travelling `angle` from the insertion point,
        in the same direction as the 3D rocket."""
        g = self._geo
        a = g["a0"] + g["turn"] * angle
        return (g["dest"][0] + g["rx"] * math.cos(a), g["dest"][1] + g["ry"] * math.sin(a))

    def _point_for(self, info: dict):
        """Marker position for a `flight_info` dict (None = hidden)."""
        g = self._geo
        phase = info["phase"]
        if phase in ("standby", "launch", "cruise"):
            return along(g["outbound"], info.get("curve", 0.0))[0]
        if phase == "ops":
            return self._orbit_point(info.get("orbit_angle", 0.0))
        if phase == "return":
            return None if info.get("ret", 0.0) >= 0.995 else along(g["homeward"], info["ret"])[0]
        return None                                   # landed (home) or lost

    # --- live marker ---------------------------------------------------------
    def update_marker(self, info: dict, standby: bool) -> None:
        g = self._geo
        if not g:
            return
        if self._preview is not None and standby:
            start, length_s = self._preview
            s = (time.monotonic() - start) / length_s
            if s >= 1.0:
                self._preview = None
            else:
                info = self.plan.info(s)
        point = self._point_for(info)
        if point is None:
            self.itemconfigure(g["dot"], state="hidden")
            self.itemconfigure(g["halo"], state="hidden")
            return
        x, y, r = point[0], point[1], g["r"]
        self.coords(g["dot"], x - r, y - r, x + r, y + r)
        self.coords(g["halo"], x - r - 4, y - r - 4, x + r + 4, y + r + 4)
        self.itemconfigure(g["dot"], state="normal")
        self.itemconfigure(g["halo"], state="normal")
