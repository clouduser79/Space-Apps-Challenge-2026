"""2D trajectory visualization widget.

Draws the Sun, Earth, destination planet, outbound and return transfer
arcs, an orbit path around the destination, and a marker at the orbit
intercept point (potential landing site), all over a star field.
Animates a rocket through the full mission: Earth -> planet -> orbit ->
Earth, leaving a bright trail along the path already flown.
"""

from __future__ import annotations

import math
import tkinter as tk
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from src.game.planets import EARTH, Planet
from src.ui import theme as T
from src.ui.widgets import draw_stars

try:
    from PIL import Image, ImageTk
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

IMAGE_DIR = Path(__file__).resolve().parents[2] / "planetImages"
ROCKET_IMAGE = Path(__file__).resolve().parents[2] / "rocket.png"

BG = T.BG
SUN_COLOR = T.SUN
TRAJECTORY_COLOR = T.OUTBOUND
RETURN_COLOR = T.RETURN
ORBIT_COLOR = T.ORBIT_RING
LANDING_COLOR = T.LANDING
ROCKET_COLOR = T.TEXT
TRAIL_COLOR = "#F1F5FF"
LABEL_COLOR = T.TEXT_MUTED


# --------------------------------------------------------------------------
# Shared geometry conventions (also used by the 3D viewport's HUD minimap)
# --------------------------------------------------------------------------
def bezier(p0, p1, p2, t: float) -> tuple[float, float]:
    """Point on a quadratic Bezier curve — every transfer arc uses this."""
    mt = 1 - t
    return (mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0],
            mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1])


def control_point(p0, p2, arc_dir: float = -1.0, max_height: float = 200.0,
                  ratio: float = 0.45) -> tuple[float, float]:
    """Control point that bows a transfer arc away from the straight line:
    up (arc_dir -1) for the outbound leg, down (+1) for the return leg."""
    mx, my = (p0[0] + p2[0]) / 2, (p0[1] + p2[1]) / 2
    height = min(max_height, abs(p2[0] - p0[0]) * ratio)
    return mx, my + arc_dir * height


def map_fraction(dest: Planet) -> float:
    """0..1 horizontal placement of a destination on a transfer map: a
    log-ish scale so Mercury isn't on top of Earth and Neptune fits."""
    return (math.log1p(dest.distance_au) / math.log1p(30.1)) ** 0.8


class TrajectoryCanvas(ctk.CTkFrame):
    """Canvas showing the full Earth -> planet -> orbit -> Earth mission."""

    # Requested size only — the canvas stretches to fill its container
    W = 640
    H = 360

    def __init__(self, master, **kwargs) -> None:
        kwargs.setdefault("fg_color", BG)
        kwargs.setdefault("corner_radius", 0)
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, width=self.W, height=self.H,
                                bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._dest: Planet | None = None
        self._anim_after = None
        self._rocket_id = None
        self._rocket_img_id = None
        self._trail_id = None
        self._on_done: Callable[[], None] | None = None
        self.flight_completed = False   # True once a flight reached Earth
        self._path: list[tuple[float, float]] = []
        self._last_size = (0, 0)
        self._img_cache: dict[tuple[str, int], tk.PhotoImage] = {}
        self.canvas.bind("<Configure>", self._on_resize)

    def _planet_photo(self, planet: Planet, diameter_px: int
                      ) -> tk.PhotoImage | None:
        """Load (and cache) a planet image resized to diameter_px."""
        if not _HAS_PIL:
            return None
        key = (planet.id, diameter_px)
        if key in self._img_cache:
            return self._img_cache[key]
        path = IMAGE_DIR / f"{planet.id}.png"
        if not path.exists():
            return None
        img = Image.open(path).convert("RGBA")
        # Height = planet diameter; width follows the art's aspect ratio so
        # Saturn keeps its rings instead of being squashed into a square
        width_px = max(1, round(diameter_px * img.width / img.height))
        img = img.resize((width_px, diameter_px), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        self._img_cache[key] = photo  # keep reference so Tk doesn't GC it
        return photo

    def _rocket_photo(self, angle_deg: float, size: int = 28
                      ) -> tk.PhotoImage | None:
        """Load rocket.png rotated so its nose points along angle_deg
        (screen coords, degrees clockwise from +x). Cached per angle."""
        if not _HAS_PIL or not ROCKET_IMAGE.exists():
            return None
        bucket = round(angle_deg / 5) * 5  # 5-degree buckets limit cache size
        key = ("rocket", bucket, size)
        if key in self._img_cache:
            return self._img_cache[key]
        img = Image.open(ROCKET_IMAGE).convert("RGBA")
        img.thumbnail((size, size), Image.LANCZOS)
        # Rocket art points up (-90 deg on screen); rotate to travel direction
        img = img.rotate(-(bucket + 90), expand=True, resample=Image.BICUBIC)
        photo = ImageTk.PhotoImage(img)
        self._img_cache[key] = photo
        return photo

    def _draw_planet(self, c: tk.Canvas, planet: Planet,
                     pos: tuple[float, float], diameter_px: int) -> float:
        """Draw a planet image (or colored fallback) at pos.
        Returns the on-screen radius in px so routes can orbit it."""
        r = diameter_px / 2
        photo = self._planet_photo(planet, diameter_px)
        if photo is not None:
            c.create_image(pos[0], pos[1], image=photo)
        else:
            c.create_oval(pos[0] - r, pos[1] - r, pos[0] + r, pos[1] + r,
                          fill=planet.color, outline="")
            if planet.id == "saturn":
                c.create_oval(pos[0] - r - 14, pos[1] - (r + 14) // 3,
                              pos[0] + r + 14, pos[1] + (r + 14) // 3,
                              outline="#C9B896", width=3)
                c.create_arc(pos[0] - r - 14, pos[1] - (r + 14) // 3,
                             pos[0] + r + 14, pos[1] + (r + 14) // 3,
                             start=0, extent=180, outline="#C9B896", width=3)
        c.create_text(pos[0], pos[1] + r + 18, text=planet.name.upper(),
                      fill=T.TEXT, font=T.canvas_font(11, bold=True))
        return r

    def _canvas_w(self) -> float:
        w = self.canvas.winfo_width()
        return w if w > 1 else self.W

    def _canvas_h(self) -> float:
        h = self.canvas.winfo_height()
        return h if h > 1 else self.H

    def _on_resize(self, event) -> None:
        size = (event.width, event.height)
        if size == self._last_size:
            return
        self._last_size = size
        if self._dest is not None:
            # Geometry changed: any running flight is no longer on the path
            self._finish_animation()
            self.plot(self._dest)
        else:
            self._draw_backdrop()
            self._draw_empty_state()

    # ---------- geometry ----------
    def _earth_pos(self) -> tuple[float, float]:
        return 170.0, self._canvas_h() / 2

    def _dest_pos(self, dest: Planet) -> tuple[float, float]:
        # Log-ish scale so Moon isn't on top of Earth and Jupiter isn't off-screen
        if dest.id == "moon":
            x = 300.0
        else:
            # Log scale so Mercury isn't on top of Earth and Neptune isn't off-screen
            x = 170.0 + map_fraction(dest) * (self._canvas_w() - 270.0)
        y = self._canvas_h() / 2 - 40  # slight vertical offset for visual interest
        return x, y

    def _bezier(self, p0, p1, p2, t: float) -> tuple[float, float]:
        return bezier(p0, p1, p2, t)

    def _control_point(self, p0, p2, arc_dir: float = -1.0) -> tuple[float, float]:
        return control_point(p0, p2, arc_dir)

    def _orbit_points(self, center, radius: float, loops: int = 1,
                      n_per_loop: int = 80, start_angle: float = 0.0
                      ) -> list[tuple[float, float]]:
        """Ellipse points around the destination planet."""
        rx = radius + 45.0
        ry = rx * 0.45
        pts = []
        for i in range(loops * n_per_loop):
            a = start_angle + 2 * math.pi * (i / n_per_loop)
            pts.append((center[0] + rx * math.cos(a),
                        center[1] + ry * math.sin(a)))
        return pts

    def _orbit_point(self, center, radius: float, angle: float
                     ) -> tuple[float, float]:
        """Single point on the orbit ellipse at a given angle."""
        rx = radius + 45.0
        ry = rx * 0.45
        return (center[0] + rx * math.cos(angle),
                center[1] + ry * math.sin(angle))

    def _spiral_points(self, center, radius: float, start_angle: float,
                       n: int = 40) -> list[tuple[float, float]]:
        """Gradual departure spiral: orbit radius grows while unwinding."""
        rx0 = radius + 45.0
        pts = []
        for i in range(n):
            t = i / (n - 1)
            r = rx0 + 80.0 * t
            a = start_angle + 1.3 * math.pi * t
            pts.append((center[0] + r * math.cos(a),
                        center[1] + r * 0.45 * math.sin(a)))
        return pts

    def _build_path(self, dest: Planet) -> list[tuple[float, float]]:
        """Full mission path: transfer -> orbit intercept -> 2 loops ->
        spiral departure -> return to Earth."""
        p0 = self._earth_pos()
        p2 = self._dest_pos(dest)
        r = float(dest.radius_px)  # displayed radius (image diameter / 2)
        intercept_angle = math.pi  # near-side of orbit, facing Earth
        intercept = self._orbit_point(p2, r, intercept_angle)
        out_ctrl = self._control_point(p0, intercept, arc_dir=-1.0)

        # Precompute spiral end for the return leg
        spiral = self._spiral_points(p2, r, intercept_angle + 4 * math.pi)
        spiral_end = spiral[-1]
        ret_ctrl = self._control_point(spiral_end, p0, arc_dir=1.0)

        path: list[tuple[float, float]] = []
        # Outbound transfer (Earth -> orbit intercept, never touches planet)
        for i in range(80):
            path.append(self._bezier(p0, out_ctrl, intercept, i / 79))
        # Orbit the destination (2 loops, starting at intercept point)
        path.extend(self._orbit_points(p2, r, loops=2,
                                       start_angle=intercept_angle))
        # Gradual spiral departure
        path.extend(spiral)
        # Return transfer (spiral end -> Earth)
        for i in range(1, 80):
            path.append(self._bezier(spiral_end, ret_ctrl, p0, i / 79))
        return path

    # ---------- drawing ----------
    def _draw_backdrop(self) -> None:
        """Star field behind everything else."""
        self.canvas.delete("all")
        w, h = int(self._canvas_w()), int(self._canvas_h())
        draw_stars(self.canvas, w, h, count=max(60, w * h // 4500))

    def _draw_empty_state(self) -> None:
        self.canvas.create_text(
            self._canvas_w() / 2, self._canvas_h() / 2,
            text="Choose a destination in “Orbit & Launch” to plot a trajectory",
            fill=T.TEXT_DIM, font=T.canvas_font(13))

    def _draw_sun(self) -> None:
        """Sun with a soft halo built from concentric discs."""
        c, cy = self.canvas, self._canvas_h() / 2
        for radius, color in ((58, "#1C1708"), (50, "#3A2E0C"), (43, "#6B5413"),
                              (35, SUN_COLOR)):
            c.create_oval(65 - radius, cy - radius, 65 + radius, cy + radius,
                          fill=color, outline="")
        c.create_text(65, cy + 72, text="SUN", fill=LABEL_COLOR,
                      font=T.canvas_font(10, bold=True))

    def show_empty(self) -> None:
        """No destination yet: star field plus a hint."""
        self._finish_animation()
        self.clear()
        self._dest = None
        self._draw_backdrop()
        self._draw_empty_state()

    @property
    def is_animating(self) -> bool:
        return self._anim_after is not None

    def plot(self, dest: Planet) -> None:
        """Draw the static scene: Sun, Earth, destination, arcs, orbit, marker."""
        if self.is_animating:
            self._finish_animation()
        self.clear()
        self._dest = dest
        c = self.canvas
        self._draw_backdrop()
        self._draw_sun()

        p0 = self._earth_pos()
        p2 = self._dest_pos(dest)
        # Display size drives everything: routes orbit the rendered planet
        dest_diameter = dest.radius_px * 2
        r = dest_diameter / 2
        intercept_angle = math.pi
        intercept = self._orbit_point(p2, r, intercept_angle)
        out_ctrl = self._control_point(p0, intercept, arc_dir=-1.0)

        # Spiral departure preview (for drawing + return arc start)
        spiral = self._spiral_points(p2, r, intercept_angle + 4 * math.pi)
        spiral_end = spiral[-1]
        ret_ctrl = self._control_point(spiral_end, p0, arc_dir=1.0)

        # Outbound transfer arc (dashed) — ends at orbit, not the planet
        pts = []
        for i in range(81):
            x, y = self._bezier(p0, out_ctrl, intercept, i / 80)
            pts.extend([x, y])
        c.create_line(*pts, fill=TRAJECTORY_COLOR, width=2, dash=(6, 4))

        # Spiral departure path (dashed)
        pts = []
        for x, y in spiral:
            pts.extend([x, y])
        c.create_line(*pts, fill=RETURN_COLOR, width=2, dash=(6, 4))

        # Return transfer arc (dashed, different color)
        pts = []
        for i in range(81):
            x, y = self._bezier(spiral_end, ret_ctrl, p0, i / 80)
            pts.extend([x, y])
        c.create_line(*pts, fill=RETURN_COLOR, width=2, dash=(6, 4))

        # Orbit ellipse around destination (dashed)
        orbit_pts = self._orbit_points(p2, r, loops=1, n_per_loop=80)
        flat = []
        for x, y in orbit_pts:
            flat.extend([x, y])
        flat.extend([orbit_pts[0][0], orbit_pts[0][1]])
        c.create_line(*flat, fill=ORBIT_COLOR, width=1, dash=(3, 3))

        # Earth (image if available)
        earth_diameter = EARTH.radius_px * 2
        self._draw_planet(c, EARTH, p0, earth_diameter)

        # Destination planet (image includes its own rings for Saturn)
        self._draw_planet(c, dest, p2, dest_diameter)

        # Potential landing site — orbit intercept point (near-side, facing Earth)
        land = intercept
        c.create_oval(land[0] - 8, land[1] - 8, land[0] + 8, land[1] + 8,
                      outline=LANDING_COLOR, width=2)
        c.create_line(land[0] - 14, land[1], land[0] + 14, land[1],
                      fill=LANDING_COLOR, width=1)
        c.create_line(land[0], land[1] - 14, land[0], land[1] + 14,
                      fill=LANDING_COLOR, width=1)
        c.create_text(land[0], land[1] - 24,
                      text="Potential landing site",
                      fill=LANDING_COLOR, font=T.canvas_font(10, bold=True))

        # Legend (bottom-left) and transfer distance (bottom-right)
        legend_y = self._canvas_h() - 24
        x = 24
        for label, color, dash in (("Outbound", TRAJECTORY_COLOR, (6, 4)),
                                   ("Return", RETURN_COLOR, (6, 4)),
                                   ("Parking orbit", ORBIT_COLOR, (3, 3))):
            c.create_line(x, legend_y, x + 28, legend_y, fill=color,
                          width=2, dash=dash)
            item = c.create_text(x + 36, legend_y, text=label, fill=LABEL_COLOR,
                                 font=T.canvas_font(10), anchor="w")
            x = c.bbox(item)[2] + 22
        c.create_text(self._canvas_w() - 24, legend_y, anchor="e",
                      text=f"Transfer distance: {dest.distance_label}",
                      fill=LABEL_COLOR, font=T.canvas_font(10))

        # Precompute full path for animation
        self._path = self._build_path(dest)

    def clear(self) -> None:
        self.canvas.delete("all")
        self._rocket_id = None
        self._rocket_img_id = None
        self._trail_id = None
        self._path = []

    # ---------- animation ----------
    def animate(self, dest: Planet, duration_ms: int = 9000,
                on_done: Callable[[], None] | None = None) -> None:
        """Animate a rocket through the full mission profile."""
        self._finish_animation()
        self.flight_completed = False
        self.plot(dest)
        c = self.canvas
        if not self._path:
            if on_done:
                on_done()
            return
        self._on_done = on_done

        # Bright trail over the part of the path already flown
        self._trail_id = c.create_line(*self._path[0], *self._path[0],
                                       fill=TRAIL_COLOR, width=2)

        # Rocket: image if available, else small triangle
        self._rocket_id = c.create_polygon(0, 0, 0, 0, 0, 0,
                                           fill=ROCKET_COLOR, outline="",
                                           state="hidden")
        self._rocket_img_id = c.create_image(0, 0, image="")
        steps = len(self._path) - 1
        interval = max(10, duration_ms // steps)
        state = {"i": 0}

        def step() -> None:
            i = state["i"]
            if i >= steps:
                self.flight_completed = True
                self._anim_after = None
                self._finish_animation()
                return
            x, y = self._path[i]
            if i >= 1:
                flown = [v for point in self._path[:i + 1] for v in point]
                c.coords(self._trail_id, *flown)
            x2, y2 = self._path[min(i + 1, steps)]
            ang = math.degrees(math.atan2(y2 - y, x2 - x))
            photo = self._rocket_photo(ang)
            if photo is not None:
                c.itemconfig(self._rocket_img_id, image=photo)
                c.coords(self._rocket_img_id, x, y)
                c.itemconfig(self._rocket_img_id, state="normal")
                c.itemconfig(self._rocket_id, state="hidden")
            else:
                c.itemconfig(self._rocket_img_id, state="hidden")
                c.itemconfig(self._rocket_id, state="normal")
                size = 9
                rad = math.radians(ang)
                tip = (x + size * math.cos(rad), y + size * math.sin(rad))
                left = (x - size * math.cos(rad - 0.5), y - size * math.sin(rad - 0.5))
                right = (x - size * math.cos(rad + 0.5), y - size * math.sin(rad + 0.5))
                c.coords(self._rocket_id, *tip, *left, *right)
            state["i"] += 1
            self._anim_after = self.after(interval, step)

        step()

    def cancel_animation(self) -> None:
        """Interrupt a running flight (e.g. when leaving the screen)."""
        self._finish_animation()

    def _finish_animation(self) -> None:
        """Stop the flight (finished or interrupted) and notify the owner
        exactly once so it can re-enable its controls."""
        self.stop_animation()
        callback, self._on_done = self._on_done, None
        if callback:
            callback()

    def stop_animation(self) -> None:
        if self._anim_after is not None:
            try:
                self.after_cancel(self._anim_after)
            except Exception:
                pass
            self._anim_after = None
