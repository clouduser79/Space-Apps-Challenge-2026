"""Lightweight 3D engine for tk.Canvas, plus Tharun's Rocket.

No OpenGL, no numpy: plain Python maths drawing filled polygons on a
tk.Canvas. That keeps the game dependency-free and runs anywhere Tk does.

Pipeline (one call to `Renderer.render` per frame):
  1. Model -> world: every `Instance` is a mesh + rotation + scale +
     position. Vertices are transformed once per mesh (meshes are indexed,
     so shared corners aren't recomputed).
  2. Back-face culling: faces pointing away from the camera are skipped
     (panels, dishes and flames are marked double-sided).
  3. Flat (Lambert) shading: brightness = ambient + diffuse * (normal · light).
     Emissive faces (rocket flames) ignore lighting.
  4. Perspective projection through a look-at camera.
  5. Painter's algorithm: faces are sorted far-to-near and written into a
     *pool* of reusable canvas polygons. Re-using items (instead of
     deleting and recreating ~600 polygons every frame) is what makes
     25+ fps possible in Tk.

Line segments (orbit rings, approach vectors) are drawn as thin screen-
space quads and sorted with the faces, so the far side of an orbit is
correctly hidden behind its planet.

`build_rocket(state)` returns Tharun's Rocket as a mesh for a given
`RocketState`: strap-on boosters that separate, solar-array wings that
unfold, a high-gain comms dish that opens, and engine flames.

Run this file directly for a turntable preview of the rocket deploying.
"""

from __future__ import annotations

import math
import tkinter as tk
from dataclasses import dataclass

Vec = tuple[float, float, float]
Mat = tuple[tuple[float, float, float], tuple[float, float, float],
            tuple[float, float, float]]

# Face flags
DOUBLE_SIDED = 1    # never culled; lit from whichever side faces the camera
EMISSIVE = 2        # flat colour, no lighting (flames, glows)


# ==========================================================================
# Vector / matrix helpers
# ==========================================================================
def add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def length(a: Vec) -> float:
    return math.sqrt(dot(a, a))


def normalize(a: Vec) -> Vec:
    n = length(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0.0, 1.0, 0.0)


def lerp(a: Vec, b: Vec, t: float) -> Vec:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)


IDENTITY: Mat = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def rot_x(a: float) -> Mat:
    c, s = math.cos(a), math.sin(a)
    return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))


def rot_y(a: float) -> Mat:
    c, s = math.cos(a), math.sin(a)
    return ((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c))


def rot_z(a: float) -> Mat:
    c, s = math.cos(a), math.sin(a)
    return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))


def matmul(a: Mat, b: Mat) -> Mat:
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3))
                 for i in range(3))  # type: ignore[return-value]


def apply(m: Mat, v: Vec) -> Vec:
    return (m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2])


def align_y(direction: Vec, roll: float = 0.0) -> Mat:
    """Rotation taking the model's +Y axis (the rocket's nose) onto
    `direction`, with an optional roll about that axis."""
    y = normalize(direction)
    helper = (0.0, 0.0, 1.0) if abs(y[2]) < 0.9 else (1.0, 0.0, 0.0)
    x = normalize(cross(y, helper))
    z = cross(x, y)
    basis = ((x[0], y[0], z[0]), (x[1], y[1], z[1]), (x[2], y[2], z[2]))
    return matmul(basis, rot_y(roll)) if roll else basis


# ==========================================================================
# Meshes
# ==========================================================================
class Mesh:
    """Indexed polygon mesh. Each face is (vertex indices, rgb, flags, ambient)."""

    __slots__ = ("verts", "faces")

    def __init__(self) -> None:
        self.verts: list[Vec] = []
        self.faces: list[tuple[tuple[int, ...], tuple[int, int, int], int, float]] = []

    def vertex(self, v: Vec) -> int:
        self.verts.append(v)
        return len(self.verts) - 1

    def face(self, idx: tuple[int, ...], rgb, flags: int = 0, ambient: float = 0.35) -> None:
        self.faces.append((idx, rgb, flags, ambient))

    def poly(self, points: list[Vec], rgb, flags: int = 0, ambient: float = 0.35) -> None:
        """Add a face from raw points (convenience for one-off parts)."""
        self.face(tuple(self.vertex(p) for p in points), rgb, flags, ambient)

    def extend(self, other: "Mesh", m: Mat = IDENTITY, offset: Vec = (0, 0, 0),
               scale: float = 1.0) -> None:
        """Merge `other` into this mesh with a transform applied."""
        base = len(self.verts)
        self.verts.extend(add(apply(m, mul(v, scale)), offset) for v in other.verts)
        self.faces.extend((tuple(i + base for i in idx), rgb, flags, amb)
                          for idx, rgb, flags, amb in other.faces)


# --- primitives (all built along the Y axis) ------------------------------
def frustum(mesh: Mesh, r0: float, y0: float, r1: float, y1: float, rgb,
            segments: int = 14, cap0: bool = False, cap1: bool = False,
            flags: int = 0, ambient: float = 0.35, offset: Vec = (0, 0, 0)) -> None:
    """Cylinder (r0 == r1), cone (r1 == 0) or truncated cone between y0 and y1."""
    ox, oy, oz = offset
    ring0, ring1 = [], []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        c, s = math.cos(a), math.sin(a)
        ring0.append(mesh.vertex((ox + r0 * c, oy + y0, oz + r0 * s)))
        ring1.append(mesh.vertex((ox + r1 * c, oy + y1, oz + r1 * s)))
    for i in range(segments):
        j = (i + 1) % segments
        if r1 <= 1e-9:
            mesh.face((ring0[i], ring1[i], ring0[j]), rgb, flags, ambient)
        elif r0 <= 1e-9:
            mesh.face((ring0[i], ring1[i], ring1[j]), rgb, flags, ambient)
        else:
            mesh.face((ring0[i], ring1[i], ring1[j], ring0[j]), rgb, flags, ambient)
    if cap0 and r0 > 1e-9:
        mesh.face(tuple(ring0), rgb, flags, ambient)
    if cap1 and r1 > 1e-9:
        mesh.face(tuple(reversed(ring1)), rgb, flags, ambient)


def box(mesh: Mesh, center: Vec, size: Vec, rgb, ambient: float = 0.35,
        side_rgb=None) -> None:
    cx, cy, cz = center
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    v = [mesh.vertex((cx + sx * hx, cy + sy * hy, cz + sz * hz))
         for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    side = side_rgb or rgb
    # index = (sx>0)*4 + (sy>0)*2 + (sz>0); faces wound counter-clockwise from outside
    for idx, colour in (((0, 1, 3, 2), side), ((4, 6, 7, 5), side),   # -x, +x
                        ((0, 4, 5, 1), rgb), ((2, 3, 7, 6), rgb),     # -y, +y
                        ((0, 2, 6, 4), side), ((1, 5, 7, 3), side)):  # -z, +z
        mesh.face(tuple(v[i] for i in idx), colour, 0, ambient)


# ==========================================================================
# Camera + renderer
# ==========================================================================
@dataclass
class Camera:
    position: Vec = (0.0, 2.0, 10.0)
    target: Vec = (0.0, 0.0, 0.0)
    fov_deg: float = 50.0
    near: float = 0.1

    def basis(self) -> tuple[Vec, Vec, Vec]:
        forward = normalize(sub(self.target, self.position))
        right = normalize(cross(forward, (0.0, 1.0, 0.0)))
        up = cross(right, forward)
        return right, up, forward


@dataclass
class Instance:
    """A mesh placed in the world."""
    mesh: Mesh
    rotation: Mat = IDENTITY
    position: Vec = (0.0, 0.0, 0.0)
    scale: float = 1.0


class Renderer:
    """Draws instances and segments onto a tk.Canvas with a polygon pool.

    Items tagged "poly" belong to the pool. Anything the owner tags "hud"
    is kept above the 3D scene; anything created before the first render
    (e.g. stars) stays below it.
    """

    def __init__(self, canvas: tk.Canvas) -> None:
        self.canvas = canvas
        self._pool: list[int] = []
        self._fills: list[str] = []
        self._shown: list[bool] = []
        self._hex: dict[tuple[int, int, int], str] = {}
        self.light: Vec = normalize((-0.55, 0.45, 0.7))
        self.last_count = 0

    def _color(self, rgb, k: float) -> str:
        key = (min(255, int(rgb[0] * k)), min(255, int(rgb[1] * k)), min(255, int(rgb[2] * k)))
        hx = self._hex.get(key)
        if hx is None:
            hx = self._hex[key] = "#%02x%02x%02x" % key
        return hx

    def render(self, camera: Camera, instances: list[Instance],
               segments: list[tuple[Vec, Vec, tuple[int, int, int], float]] = ()) -> None:
        """segments: (world a, world b, rgb, width_px)."""
        c = self.canvas
        w, h = max(2, c.winfo_width()), max(2, c.winfo_height())
        cx, cy = w / 2, h / 2
        focal = (h / 2) / math.tan(math.radians(camera.fov_deg) / 2)
        right, up, forward = camera.basis()
        cam = camera.position
        near = camera.near
        light = self.light
        drawn: list[tuple[float, list[float], str]] = []

        for inst in instances:
            m, pos, s = inst.rotation, inst.position, inst.scale
            world = [add(apply(m, (v[0] * s, v[1] * s, v[2] * s)), pos) for v in inst.mesh.verts]
            proj = []
            for v in world:
                d = (v[0] - cam[0], v[1] - cam[1], v[2] - cam[2])
                z = d[0] * forward[0] + d[1] * forward[1] + d[2] * forward[2]
                if z <= near:
                    proj.append(None)
                    continue
                x = d[0] * right[0] + d[1] * right[1] + d[2] * right[2]
                y = d[0] * up[0] + d[1] * up[1] + d[2] * up[2]
                proj.append((cx + focal * x / z, cy - focal * y / z, z))

            for idx, rgb, flags, ambient in inst.mesh.faces:
                pts = [proj[i] for i in idx]
                if None in pts:
                    continue
                a, b, c3 = world[idx[0]], world[idx[1]], world[idx[2]]
                n = cross(sub(b, a), sub(c3, a))
                facing = dot(n, sub(cam, a))
                if facing <= 0:
                    if not flags & DOUBLE_SIDED:
                        continue
                    n = (-n[0], -n[1], -n[2])
                if flags & EMISSIVE:
                    k = 1.0
                else:
                    nl = length(n)
                    lam = max(0.0, dot(n, light) / nl) if nl > 1e-12 else 0.0
                    k = ambient + (1.0 - ambient) * lam
                coords = [v for p in pts for v in p[:2]]
                depth = sum(p[2] for p in pts) / len(pts)
                drawn.append((depth, coords, self._color(rgb, k)))

        for a, b, rgb, width in segments:
            quad = self._segment(a, b, cam, right, up, forward, focal, cx, cy, near, width)
            if quad:
                drawn.append((quad[0], quad[1], self._color(rgb, 1.0)))

        drawn.sort(key=lambda item: -item[0])
        self._write(drawn)

    @staticmethod
    def _segment(a, b, cam, right, up, forward, focal, cx, cy, near, width):
        pts = []
        for v in (a, b):
            d = sub(v, cam)
            z = dot(d, forward)
            if z <= near:
                return None
            pts.append((cx + focal * dot(d, right) / z, cy - focal * dot(d, up) / z, z))
        (x0, y0, z0), (x1, y1, z1) = pts
        dx, dy = x1 - x0, y1 - y0
        n = math.hypot(dx, dy)
        if n < 1e-6:
            return None
        ox, oy = -dy / n * width / 2, dx / n * width / 2
        return ((z0 + z1) / 2,
                [x0 + ox, y0 + oy, x1 + ox, y1 + oy, x1 - ox, y1 - oy, x0 - ox, y0 - oy])

    def _write(self, drawn) -> None:
        c = self.canvas
        grew = False
        while len(self._pool) < len(drawn):
            self._pool.append(c.create_polygon(0, 0, 0, 0, 0, 0, fill="", outline="",
                                               tags="poly"))
            self._fills.append("")
            self._shown.append(True)
            grew = True
        if grew:
            c.tag_raise("hud")
        for i, (_depth, coords, fill) in enumerate(drawn):
            item = self._pool[i]
            c.coords(item, coords)
            if self._fills[i] != fill:
                c.itemconfigure(item, fill=fill, outline=fill)
                self._fills[i] = fill
            if not self._shown[i]:
                c.itemconfigure(item, state="normal")
                self._shown[i] = True
        for i in range(len(drawn), len(self._pool)):
            if self._shown[i]:
                c.itemconfigure(self._pool[i], state="hidden")
                self._shown[i] = False
        self.last_count = len(drawn)

    def reset(self) -> None:
        """Forget the pool (call after canvas.delete('all'))."""
        self._pool.clear()
        self._fills.clear()
        self._shown.clear()


def dashed(a: Vec, b: Vec, rgb, width: float = 1.5, dashes: int = 12):
    """Split a segment into dashes for Renderer.render(segments=...)."""
    out = []
    for i in range(dashes):
        t0, t1 = i / dashes, (i + 0.55) / dashes
        out.append((lerp(a, b, t0), lerp(a, b, t1), rgb, width))
    return out


# ==========================================================================
# Tharun's Rocket
# ==========================================================================
WHITE = (228, 233, 242)
LIGHT = (196, 204, 218)
DARK = (58, 64, 78)
STEEL = (120, 128, 142)
GOLD = (214, 168, 64)
GOLD_DARK = (170, 128, 44)
STRIPE = (56, 189, 248)
CELL_A = (38, 76, 168)
CELL_B = (28, 58, 134)
DISH = (226, 230, 238)
FLAME_OUT = (249, 115, 22)
FLAME_IN = (253, 224, 120)

CORE_R = 0.17
BUS_Y = 0.62          # centre of the spacecraft bus
BUS_HALF = 0.17


@dataclass
class RocketState:
    """Everything that changes on the rocket during the flight (0..1 values)."""
    boosters: float = 0.0     # 0 attached, 0..1 separating, >= 1 gone
    arrays: float = 0.0       # solar array deployment
    dish: float = 0.0         # comms dish deployment
    flame: float = 0.0        # main-engine throttle (flame length)
    booster_flame: float = 0.0
    flicker: float = 0.0      # 0..1 noise so flames shimmer


def _ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _flame(mesh: Mesh, y: float, radius: float, length_: float, flicker: float,
           offset: Vec = (0, 0, 0)) -> None:
    if length_ <= 0.01:
        return
    l_out = length_ * (0.9 + 0.2 * flicker)
    frustum(mesh, radius, y, 0.0, y - l_out, FLAME_OUT, 10, flags=EMISSIVE | DOUBLE_SIDED,
            offset=offset)
    frustum(mesh, radius * 0.6, y - 0.01, 0.0, y - l_out * 0.6, FLAME_IN, 8,
            flags=EMISSIVE | DOUBLE_SIDED, offset=offset)


def _booster(state: RocketState, side: int) -> Mesh:
    """One strap-on booster, built at the origin; positioned by the caller."""
    m = Mesh()
    frustum(m, 0.085, -0.95, 0.085, 0.05, LIGHT, 10)
    frustum(m, 0.085, 0.05, 0.0, 0.3, WHITE, 10)                 # nose cone
    frustum(m, 0.06, -0.95, 0.09, -1.05, DARK, 8, flags=DOUBLE_SIDED)  # nozzle
    m.poly([(0.0, -0.95, 0.0), (side * 0.13, -1.0, 0.0), (0.0, -0.7, 0.0)],
           STRIPE, DOUBLE_SIDED)                                    # fin
    _flame(m, -1.05, 0.08, 0.45 * state.booster_flame, state.flicker)
    return m


def _array_wing(deploy: float, side: int) -> Mesh:
    """Solar wing hinged at the bus side. Folded flat against the body
    (pointing down), it swings out to horizontal and its three panels
    unfold accordion-style."""
    m = Mesh()
    d = _ease(deploy)
    panel_len = 0.30 * (0.33 + 0.67 * d)        # panels slide out as they unfold
    width = 0.26
    yoke = 0.05
    # Panels lie in the XY plane, so they face forward (toward +z) and the
    # hinge swing (about z) keeps them flat — broad side visible, not edge-on.
    m.poly([(0, -0.012, 0), (yoke, -0.012, 0), (yoke, 0.012, 0), (0, 0.012, 0)],
           STEEL, DOUBLE_SIDED)
    for i in range(3):
        x0 = yoke + i * (panel_len + 0.012)
        x1 = x0 + panel_len
        m.poly([(x0, -width / 2, 0), (x1, -width / 2, 0), (x1, width / 2, 0), (x0, width / 2, 0)],
               CELL_A if i % 2 == 0 else CELL_B, DOUBLE_SIDED, ambient=0.3)
    # Hinge: 0 = hanging down along the body, 1 = straight out
    angle = (-math.pi / 2) * (1 - d)
    swing = rot_z(angle if side > 0 else -angle)
    flip = IDENTITY if side > 0 else ((-1.0, 0, 0), (0, 1.0, 0), (0, 0, 1.0))
    out = Mesh()
    out.extend(m, matmul(swing, flip))
    return out


def _dish(deploy: float) -> Mesh:
    """High-gain antenna: a paraboloid that opens like an umbrella."""
    m = Mesh()
    d = _ease(deploy)
    radius = 0.06 + 0.2 * d
    depth = 0.09 * (0.3 + 0.7 * d)
    seg = 16
    centre = m.vertex((0.0, 0.0, 0.0))
    ring1 = [m.vertex((radius * 0.5 * math.cos(2 * math.pi * i / seg),
                       radius * 0.5 * math.sin(2 * math.pi * i / seg), depth * 0.25))
             for i in range(seg)]
    ring2 = [m.vertex((radius * math.cos(2 * math.pi * i / seg),
                       radius * math.sin(2 * math.pi * i / seg), depth))
             for i in range(seg)]
    for i in range(seg):
        j = (i + 1) % seg
        shade = DISH if i % 2 == 0 else LIGHT
        m.face((centre, ring1[i], ring1[j]), shade, DOUBLE_SIDED, 0.4)
        m.face((ring1[i], ring2[i], ring2[j], ring1[j]), shade, DOUBLE_SIDED, 0.4)
    # Feed horn on a short strut at the focus
    m.poly([(-0.008, 0, 0), (0.008, 0, 0), (0.008, 0, depth + 0.1 * d),
            (-0.008, 0, depth + 0.1 * d)], STEEL, DOUBLE_SIDED)
    return m


def build_rocket(state: RocketState) -> Mesh:
    """Tharun's Rocket in model space: nose along +Y, ~2.4 units tall."""
    m = Mesh()
    # Core stage, built in coloured sections (no overlapping faces)
    for y0, y1, colour in ((-1.0, -0.25, WHITE), (-0.25, -0.15, STRIPE),
                           (-0.15, 0.38, WHITE)):
        frustum(m, CORE_R, y0, CORE_R, y1, colour, 14, cap0=(y0 == -1.0))
    frustum(m, CORE_R, 0.38, CORE_R, 0.45, DARK, 14)                     # interstage
    frustum(m, 0.11, -1.0, 0.17, -1.2, DARK, 12, flags=DOUBLE_SIDED)     # engine bell
    for k in range(4):                                                   # core fins
        a = math.pi / 4 + k * math.pi / 2
        cx, cz = math.cos(a), math.sin(a)
        m.poly([(CORE_R * cx, -1.0, CORE_R * cz), ((CORE_R + 0.16) * cx, -1.05, (CORE_R + 0.16) * cz),
                (CORE_R * cx, -0.72, CORE_R * cz)], DARK, DOUBLE_SIDED)
    _flame(m, -1.2, 0.15, 0.7 * state.flame, state.flicker)

    # Spacecraft bus wrapped in gold foil, with its nose fairing on top
    box(m, (0.0, BUS_Y, 0.0), (2 * BUS_HALF, 0.34, 2 * BUS_HALF), GOLD, 0.35, GOLD_DARK)
    frustum(m, CORE_R, BUS_Y + 0.17, 0.0, BUS_Y + 0.6, WHITE, 14)

    # Solar wings on +x / -x faces of the bus
    for side in (1, -1):
        m.extend(_array_wing(state.arrays, side), offset=(side * BUS_HALF, BUS_Y, 0.0))

    # Comms dish on the +z face, tilting up as it deploys
    tilt = rot_x(-0.5 * _ease(state.dish))
    m.extend(_dish(state.dish), tilt, offset=(0.0, BUS_Y + 0.02, BUS_HALF + 0.005))

    # Boosters: attached at +-x, then drift outward, tumble and fall back
    if state.boosters < 1.0:
        sep = max(0.0, state.boosters)
        for side in (1, -1):
            offset = (side * (CORE_R + 0.09 + 0.9 * sep), -0.05 - 1.3 * sep ** 1.5, 0.0)
            spin = rot_z(side * 1.1 * sep)
            m.extend(_booster(state, side), spin, offset)
    return m


# ==========================================================================
# Stand-alone preview:  python -m src.ui.spacecraft_view
# ==========================================================================
def _preview() -> None:  # pragma: no cover - manual tool
    import time
    root = tk.Tk()
    root.title("Tharun's Rocket — preview")
    canvas = tk.Canvas(root, width=720, height=520, bg="#060A13", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    renderer = Renderer(canvas)
    camera = Camera(position=(0.0, 0.8, 5.0), target=(0.0, 0.1, 0.0))
    start = time.monotonic()

    def frame() -> None:
        t = time.monotonic() - start
        cycle = (t % 10.0) / 10.0
        state = RocketState(boosters=max(0.0, (cycle - 0.1) * 4), arrays=(cycle - 0.35) * 3,
                            dish=(cycle - 0.6) * 3, flame=1.0 if cycle < 0.35 else 0.0,
                            booster_flame=1.0 if cycle < 0.1 else 0.0, flicker=(t * 7) % 1)
        renderer.render(camera, [Instance(build_rocket(state), rot_y(t * 0.6))])
        root.after(33, frame)

    frame()
    root.mainloop()


if __name__ == "__main__":
    _preview()
