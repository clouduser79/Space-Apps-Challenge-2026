"""XP shop: premium parts that must be unlocked with XP before use.

A starter set stays free so every built-in scenario can be completed on
a brand-new profile:
  Earth Observation   wide-angle camera, SSO/LEO, small or medium launcher
  Mars Reconnaissance spectrometer, Low Mars Orbit, medium launcher
  Deep Space Weather  magnetometer, Sun-Earth L1, medium launcher
Everything below is locked until bought. Prices rise with how much the
part opens up (more power, more data, more science, farther reach).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShopItem:
    id: str          # catalogue id of the part / orbit / launcher
    kind: str        # "bus" | "instrument" | "orbit" | "launcher"
    price: int       # XP
    pitch: str       # why it's worth buying


SHOP_ITEMS: list[ShopItem] = [
    # Spacecraft bus
    ShopItem("storage_expanded", "bus", 100, "4x the onboard storage for data-hungry payloads."),
    ShopItem("solar_large", "bus", 150, "2,000 W of solar power for power-hungry instruments."),
    ShopItem("adcs_precise", "bus", 150, "Arcsecond pointing for razor-sharp imaging."),
    ShopItem("structure_heavy", "bus", 150, "A flagship-sized frame for big payloads."),
    ShopItem("comms_high", "bus", 200, "10x faster downlink — send more science home."),
    ShopItem("propulsion_advanced", "bus", 250, "Big engines for large orbit changes and deep space."),
    ShopItem("rtg", "bus", 300, "Nuclear power that works in the dark, far from the Sun."),
    # Science payload
    ShopItem("high_res_imager", "instrument", 200, "Detailed surface images — big science value."),
    ShopItem("radar_sounder", "instrument", 300, "See beneath the surface: ice and buried geology."),
    ShopItem("sample_return", "instrument", 500, "Bring a piece of another world home. Top science."),
    # Orbit & launch
    ShopItem("geo", "orbit", 150, "Hover over one spot — the classic comms orbit."),
    ShopItem("lmo", "orbit", 200, "Skim the Moon for close-up lunar mapping."),
    ShopItem("heavy_launcher", "launcher", 400, "Flagship rocket: huge payloads and the outer planets."),
]
ITEMS_BY_ID = {item.id: item for item in SHOP_ITEMS}
KIND_LABELS = {"bus": "Spacecraft bus", "instrument": "Science payload",
               "orbit": "Orbits", "launcher": "Launch vehicles"}


def price_of(item_id: str) -> int | None:
    """XP price if the item is sold in the shop, else None (always free)."""
    item = ITEMS_BY_ID.get(item_id)
    return item.price if item else None


def is_unlocked(profile, item_id: str) -> bool:
    return item_id not in ITEMS_BY_ID or item_id in profile.unlocks
