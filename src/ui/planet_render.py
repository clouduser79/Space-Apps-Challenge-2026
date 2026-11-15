"""Procedural planet spheres for the 3D mission viewport.

Each destination gets a UV-sphere mesh whose faces are coloured by a
procedural "texture" function — continents and ice caps for Earth, rusty
plains for Mars, maria for the Moon, cloud bands and the Great Red Spot
for Jupiter, and so on. Textures are sampled at each face's centre using
3D value noise on the unit sphere (so there's no seam at the date line),
then cached per planet: swapping destinations just swaps the cached mesh.

Planet size on screen comes from `radius_for()` — a log scale of the
real diameter, so the Moon is small and Jupiter is big without Jupiter
filling the whole viewport. Saturn (and faintly Uranus) get rings.
"""

from __future__ import annotations

import math
from functools import lru_cache

from src.game.planets import EARTH, PLANETS, Planet
from src.ui.spacecraft_view import DOUBLE_SIDED, Mesh

LAT_SEGMENTS = 20
LON_SEGMENTS = 40

# Axial tilt in degrees (Uranus rolls on its side, Venus is upside down)
AXIAL_TILT = {"earth": 23.4, "moon": 6.7, "mercury": 0.0, "venus": 177.0,
              "mars": 25.2, "jupiter": 3.1, "saturn": 26.7, "uranus": 97.8,
              "neptune": 28.3}

# Standard gravitational parameter GM (km^3/s^2), for real orbital speeds
GM = {"earth": 398_600.4, "moon": 4_904.9, "mercury": 22_032.0,
      "venus": 324_859.0, "mars": 42_828.4, "jupiter": 126_686_534.0,
      "saturn": 37_931_187.0, "uranus": 5_793_939.0, "neptune": 6_836_529.0}

# Thin atmosphere halo colour (None = airless)
HALO = {"earth": (110, 170, 255), "venus": (240, 214, 160), "mars": (214, 132, 96),
        "jupiter": (226, 196, 160), "saturn": (232, 212, 160),
        "uranus": (160, 226, 236), "neptune": (100, 140, 240)}


# ==========================================================================
# Noise
# ==========================================================================
def _hash(ix: int, iy: int, iz: int, seed: int) -> float:
    n = (ix * 374761393 + iy * 668265263 + iz * 2147483647 + seed * 144269) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def _smooth(t: float) -> float:
    return t * t * (3 - 2 * t)


def value_noise(x: float, y: float, z: float, seed: int = 0) -> float:
    """Smooth 3D value noise in [0, 1]."""
    ix, iy, iz = math.floor(x), math.floor(y), math.floor(z)
    fx, fy, fz = _smooth(x - ix), _smooth(y - iy), _smooth(z - iz)
    c = [[[_hash(ix + i, iy + j, iz + k, seed) for k in (0, 1)] for j in (0, 1)] for i in (0, 1)]
    x00 = c[0][0][0] + (c[1][0][0] - c[0][0][0]) * fx
    x10 = c[0][1][0] + (c[1][1][0] - c[0][1][0]) * fx
    x01 = c[0][0][1] + (c[1][0][1] - c[0][0][1]) * fx
    x11 = c[0][1][1] + (c[1][1][1] - c[0][1][1]) * fx
    y0 = x00 + (x10 - x00) * fy
    y1 = x01 + (x11 - x01) * fy
    return y0 + (y1 - y0) * fz


def fbm(p: tuple[float, float, float], freq: float, seed: int = 0, octaves: int = 4) -> float:
    """Fractal noise: several octaves of value noise, roughly in [0, 1]."""
    total, amp, norm = 0.0, 1.0, 0.0
    for o in range(octaves):
        total += amp * value_noise(p[0] * freq, p[1] * freq, p[2] * freq, seed + o * 17)
        norm += amp
        amp *= 0.5
        freq *= 2.0
    return total / norm


def _mix(a, b, t: float):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _spot(lat: float, lon: float, lat0: float, lon0: float) -> float:
    """Angular distance (radians) from (lat0, lon0)."""
    c = (math.sin(lat) * math.sin(lat0)
         + math.cos(lat) * math.cos(lat0) * math.cos(lon - lon0))
    return math.acos(max(-1.0, min(1.0, c)))


# ==========================================================================
# Surface "textures": (planet id, point on unit sphere, lat, lon) -> rgb
# ==========================================================================
def _earth(p, lat, lon):
    n = fbm(p, 1.6, 3)
    if abs(lat) > math.radians(70) + (n - 0.5) * 0.3:
        colour = (236, 242, 250)                                   # ice caps
    elif n > 0.53:
        colour = _mix((70, 138, 70), (150, 130, 84), fbm(p, 4.0, 9))  # land
    else:
        colour = _mix((18, 52, 120), (36, 96, 176), n / 0.53)       # ocean
    cloud = fbm(p, 3.2, 21)
    return _mix(colour, (240, 244, 250), (cloud - 0.6) * 3.0) if cloud > 0.6 else colour


def _mars(p, lat, lon):
    if abs(lat) > math.radians(76):
        return (238, 226, 220)
    n = fbm(p, 2.0, 5)
    colour = _mix((214, 132, 82), (186, 82, 44), n)
    return _mix(colour, (112, 50, 34), (fbm(p, 1.3, 11) - 0.55) * 3.5)


def _moon(p, lat, lon):
    base = _mix((178, 178, 180), (140, 140, 146), fbm(p, 5.0, 2))
    maria = fbm(p, 1.5, 7)
    return _mix(base, (96, 96, 104), (maria - 0.52) * 4.0)


def _mercury(p, lat, lon):
    base = _mix((168, 156, 146), (122, 112, 104), fbm(p, 4.5, 4))
    return _mix(base, (92, 86, 82), (fbm(p, 2.0, 13) - 0.58) * 4.0)


def _venus(p, lat, lon):
    swirl = math.sin(lat * 6 + fbm(p, 2.0, 8) * 4.0)
    return _mix((214, 170, 104), (244, 226, 176), 0.5 + 0.5 * swirl)


def _jupiter(p, lat, lon):
    bands = [(232, 214, 184), (196, 146, 104), (244, 232, 210), (170, 116, 84),
             (226, 196, 158)]
    # Latitude bands, gently warped by noise, blended between neighbours
    b = (math.sin(lat * 11 + (fbm(p, 3.0, 6) - 0.5) * 0.7) + 1) / 2 * (len(bands) - 1)
    lo = min(len(bands) - 2, int(b))
    colour = _mix(bands[lo], bands[lo + 1], b - lo)
    red_spot = _spot(lat, lon, math.radians(-22), 0.6)
    if red_spot < 0.22:
        colour = _mix((196, 92, 66), colour, red_spot / 0.22)
    return colour


def _saturn(p, lat, lon):
    b = (math.sin(lat * 10 + (fbm(p, 2.5, 4) - 0.5) * 1.5) + 1) / 2
    return _mix((206, 176, 120), (238, 218, 166), b)


def _uranus(p, lat, lon):
    return _mix((140, 206, 218), (176, 228, 236), (math.sin(lat * 4) + 1) / 2 * 0.6)


def _neptune(p, lat, lon):
    colour = _mix((40, 76, 184), (66, 108, 220), fbm(p, 2.2, 12))
    streak = fbm(p, 4.0, 15)
    if streak > 0.66:
        colour = _mix(colour, (160, 196, 246), (streak - 0.66) * 4)
    if _spot(lat, lon, math.radians(-20), 1.4) < 0.18:
        colour = (28, 44, 120)
    return colour


TEXTURES = {"earth": _earth, "mars": _mars, "moon": _moon, "mercury": _mercury,
            "venus": _venus, "jupiter": _jupiter, "saturn": _saturn,
            "uranus": _uranus, "neptune": _neptune}


def _hex_rgb(colour: str):
    colour = colour.lstrip("#")
    return tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))


# ==========================================================================
# Meshes
# ==========================================================================
@lru_cache(maxsize=16)
def planet_mesh(planet_id: str) -> Mesh:
    """Unit-radius UV sphere coloured by the planet's texture (cached)."""
    planet = PLANETS.get(planet_id, EARTH if planet_id == "earth" else None)
    texture = TEXTURES.get(planet_id)
    fallback = _hex_rgb(planet.color) if planet else (150, 150, 160)
    mesh = Mesh()

    def vert(i: int, j: int) -> int:
        lat = math.pi / 2 - math.pi * i / LAT_SEGMENTS
        lon = 2 * math.pi * j / LON_SEGMENTS
        return mesh.vertex((math.cos(lat) * math.cos(lon), math.sin(lat),
                            -math.cos(lat) * math.sin(lon)))

    grid = [[vert(i, j) for j in range(LON_SEGMENTS)] for i in range(LAT_SEGMENTS + 1)]
    for i in range(LAT_SEGMENTS):
        for j in range(LON_SEGMENTS):
            j2 = (j + 1) % LON_SEGMENTS
            lat = math.pi / 2 - math.pi * (i + 0.5) / LAT_SEGMENTS
            lon = 2 * math.pi * (j + 0.5) / LON_SEGMENTS
            p = (math.cos(lat) * math.cos(lon), math.sin(lat), -math.cos(lat) * math.sin(lon))
            rgb = texture(p, lat, lon) if texture else fallback
            a, b = grid[i][j], grid[i][j2]
            c, d = grid[i + 1][j2], grid[i + 1][j]
            if i == 0:                       # north-pole cap: triangles
                mesh.face((a, d, c), rgb, 0, 0.1)
            elif i == LAT_SEGMENTS - 1:      # south-pole cap
                mesh.face((a, d, b), rgb, 0, 0.1)
            else:
                mesh.face((a, d, c, b), rgb, 0, 0.1)
    return mesh


RING_BANDS = {
    "saturn": [(1.24, 1.52, (176, 156, 120)), (1.55, 1.95, (222, 204, 160)),
               (2.0, 2.25, (196, 178, 136))],
    "uranus": [(1.6, 1.66, (150, 190, 200)), (1.8, 1.84, (150, 190, 200))],
}


@lru_cache(maxsize=4)
def ring_mesh(planet_id: str) -> Mesh | None:
    """Flat ring system in the equatorial plane (radii in planet radii)."""
    bands = RING_BANDS.get(planet_id)
    if not bands:
        return None
    mesh = Mesh()
    seg = 48
    for r0, r1, rgb in bands:
        inner = [mesh.vertex((r0 * math.cos(2 * math.pi * k / seg), 0.0,
                              r0 * math.sin(2 * math.pi * k / seg))) for k in range(seg)]
        outer = [mesh.vertex((r1 * math.cos(2 * math.pi * k / seg), 0.0,
                              r1 * math.sin(2 * math.pi * k / seg))) for k in range(seg)]
        for k in range(seg):
            k2 = (k + 1) % seg
            shade = rgb if k % 2 == 0 else tuple(int(v * 0.92) for v in rgb)
            mesh.face((inner[k], outer[k], outer[k2], inner[k2]), shade, DOUBLE_SIDED, 0.3)
    return mesh


def ring_outer(planet_id: str) -> float:
    bands = RING_BANDS.get(planet_id)
    return max(b[1] for b in bands) if bands else 1.0


# ==========================================================================
# Scale
# ==========================================================================
_D_MIN = min(p.diameter_km for p in PLANETS.values())
_D_MAX = max(p.diameter_km for p in PLANETS.values())


def radius_for(planet: Planet | None) -> float:
    """Scene radius from the real diameter on a log scale: the smallest
    destination (Moon) is 1.0, the largest (Jupiter) 2.3."""
    if planet is None:
        return 1.5
    t = (math.log(planet.diameter_km) - math.log(_D_MIN)) / (math.log(_D_MAX) - math.log(_D_MIN))
    return 1.0 + 1.3 * max(0.0, min(1.0, t))


def orbital_speed_km_s(planet: Planet | None, altitude_km: float) -> float | None:
    """Circular orbital speed v = sqrt(GM / r) at `altitude_km`."""
    if planet is None or planet.id not in GM:
        return None
    r = planet.diameter_km / 2 + altitude_km
    return math.sqrt(GM[planet.id] / r)
