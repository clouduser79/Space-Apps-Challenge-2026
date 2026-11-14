"""2D trajectory visualization widget.

Draws the Sun, Earth, destination planet, outbound and return transfer
arcs, an orbit path around the destination, and a marker at the outbound
trajectory's halfway point (potential landing site). Animates a rocket
through the full mission: Earth -> planet -> orbit -> Earth.
"""

from __future__ import annotations

import math
import tkinter as tk
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from src.game.planets import EARTH, Planet

try:
    from PIL import Image, ImageTk
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

IMAGE_DIR = Path(__file__).resolve().parents[2] / "planetImages"
ROCKET_IMAGE = Path(__file__).resolve().parents[2] / "rocket.png"

BG = "#242424"
SUN_COLOR = "#F4D03F"
TRAJECTORY_COLOR = "#7FB3E8"
RETURN_COLOR = "#B08CE8"
ORBIT_COLOR = "#E8A33D"
LANDING_COLOR = "#7BE382"
ROCKET_COLOR = "#E8E8E8"


class TrajectoryCanvas(ctk.CTkFrame):
    """Canvas showing the full Earth -> planet -> orbit -> Earth mission."""

    W = 1150
    H = 600

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, width=self.W, height=self.H,
                                bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._dest: Planet | None = None
        self._anim_after = None
        self._rocket_id = None
        self._rocket_img_id = None
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
        img = img.resize((diameter_px, diameter_px), Image.LANCZOS)
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
                          fill=planet.color, outline="white")
            if planet.id == "saturn":
                c.create_oval(pos[0] - r - 14, pos[1] - (r + 14) // 3,
                              pos[0] + r + 14, pos[1] + (r + 14) // 3,
                              outline="#C9B896", width=3)
                c.create_arc(pos[0] - r - 14, pos[1] - (r + 14) // 3,
                             pos[0] + r + 14, pos[1] + (r + 14) // 3,
                             start=0, extent=180, outline="#C9B896", width=3)
        c.create_text(pos[0], pos[1] + r + 18, text=planet.name,
                      fill="white", font=("Segoe UI", 11, "bold"))
        return r

    def _canvas_w(self) -> float:
        w = self.canvas.winfo_width()
        return w if w > 1 else self.W

    def _canvas_h(self) -> float:
        h = self.canvas.winfo_height()
        return h if h > 1 else self.H

    def _on_resize(self, event) -> None:
        size = (event.width, event.height)
        if size != self._last_size and self._dest is not None:
            self._last_size = size
            self.plot(self._dest)

    # ---------- geometry ----------
    def _earth_pos(self) -> tuple[float, float]:
        return 170.0, self._canvas_h() / 2

    def _dest_pos(self, dest: Planet) -> tuple[float, float]:
        # Log-ish scale so Moon isn't on top of Earth and Jupiter isn't off-screen
        if dest.id == "moon":
            x = 300.0
        else:
            # Log scale so Mercury isn't on top of Earth and Neptune isn't off-screen
            x = 170.0 + (math.log1p(dest.distance_au) / math.log1p(30.1)) ** 0.8 * (self._canvas_w() - 270.0)
        y = self._canvas_h() / 2 - 40  # slight vertical offset for visual interest
        return x, y

    def _bezier(self, p0, p1, p2, t: float) -> tuple[float, float]:
        mt = 1 - t
        x = mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0]
        y = mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1]
        return x, y

    def _control_point(self, p0, p2, arc_dir: float = -1.0) -> tuple[float, float]:
        mx = (p0[0] + p2[0]) / 2
        my = (p0[1] + p2[1]) / 2
        dist = abs(p2[0] - p0[0])
        height = min(200.0, dist * 0.45)
        return mx, my + arc_dir * height

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
    def plot(self, dest: Planet) -> None:
        """Draw the static scene: Sun, Earth, destination, arcs, orbit, marker."""
        self.clear()
        self._dest = dest
        c = self.canvas

        # Sun
        c.create_oval(30, self._canvas_h() / 2 - 35, 100, self._canvas_h() / 2 + 35,
                      fill=SUN_COLOR, outline="")
        c.create_text(65, self._canvas_h() / 2 + 55, text="Sun", fill="#AAAAAA",
                      font=("Segoe UI", 11))

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
        c.create_text(land[0], land[1] - 22,
                      text="Potential landing site (near-side orbit)",
                      fill=LANDING_COLOR, font=("Segoe UI", 10))

        # Legend
        legend_y = self._canvas_h() - 30
        c.create_line(30, legend_y, 60, legend_y, fill=TRAJECTORY_COLOR,
                      width=2, dash=(6, 4))
        c.create_text(68, legend_y, text="Outbound", fill="#AAAAAA",
                      font=("Segoe UI", 10), anchor="w")
        c.create_line(160, legend_y, 190, legend_y, fill=RETURN_COLOR,
                      width=2, dash=(6, 4))
        c.create_text(198, legend_y, text="Return", fill="#AAAAAA",
                      font=("Segoe UI", 10), anchor="w")
        c.create_line(280, legend_y, 310, legend_y, fill=ORBIT_COLOR,
                      width=1, dash=(3, 3))
        c.create_text(318, legend_y, text="Orbit", fill="#AAAAAA",
                      font=("Segoe UI", 10), anchor="w")

        # Distance label
        c.create_text((p0[0] + p2[0]) / 2, max(p0[1], p2[1]) + 45,
                      text=f"Transfer distance: {dest.distance_label}",
                      fill="#AAAAAA", font=("Segoe UI", 11))

        # Precompute full path for animation
        self._path = self._build_path(dest)

    def clear(self) -> None:
        self.canvas.delete("all")
        self._rocket_id = None
        self._rocket_img_id = None
        self._path = []

    # ---------- animation ----------
    def animate(self, dest: Planet, duration_ms: int = 9000,
                on_done: Callable[[], None] | None = None) -> None:
        """Animate a rocket through the full mission profile."""
        self.stop_animation()
        self.plot(dest)
        c = self.canvas
        if not self._path:
            return

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
                if on_done:
                    on_done()
                return
            x, y = self._path[i]
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

    def stop_animation(self) -> None:
        if self._anim_after is not None:
            try:
                self.after_cancel(self._anim_after)
            except Exception:
                pass
            self._anim_after = None
