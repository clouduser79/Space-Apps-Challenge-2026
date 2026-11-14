"""Scientific instruments catalog.

Each instrument trades scientific value against mass, power, cost,
and data generation — the core trade-off system of the game.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass
class Instrument:
    """A scientific instrument the player can select."""

    id: str
    name: str
    mass_kg: float
    power_w: float
    cost_usd: float
    data_rate_mbps: float
    science_value: float          # 0-100 scale
    description: str
    tags: list[str] = field(default_factory=list)  # e.g. ["imaging", "spectroscopy"]

    def impact_summary(self) -> str:
        """One-line consequence preview."""
        return (f"{self.name}: +{self.mass_kg:g} kg, +{self.power_w:g} W, "
                f"+${self.cost_usd / 1e6:.1f}M, +{self.data_rate_mbps:g} Mbps data, "
                f"science {self.science_value:g}/100")


def _guess_tags(inst: dict) -> list[str]:
    """Infer capability tags from name/description for requirement checks."""
    text = f"{inst['name']} {inst.get('description', '')}".lower()
    tags = []
    if any(w in text for w in ("imag", "camera", "photo", "map")):
        tags.append("imaging")
    if any(w in text for w in ("spectro", "composition", "chem")):
        tags.append("spectroscopy")
    if any(w in text for w in ("radar", "subsurface", "ice")):
        tags.append("subsurface")
    if any(w in text for w in ("magnet", "space weather", "solar wind")):
        tags.append("space_weather")
    if any(w in text for w in ("sample", "return")):
        tags.append("sample_return")
    if any(w in text for w in ("relay", "communication")):
        tags.append("comms")
    return tags


def load_catalog(path: Path | None = None) -> dict[str, Instrument]:
    """Load instrument definitions from JSON into a catalog."""
    path = path or DATA_DIR / "instruments.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    catalog = {}
    for entry in raw["instruments"]:
        inst = Instrument(
            id=entry["id"],
            name=entry["name"],
            mass_kg=float(entry["mass_kg"]),
            power_w=float(entry["power_w"]),
            cost_usd=float(entry["cost_usd"]),
            data_rate_mbps=float(entry["data_rate_mbps"]),
            science_value=float(entry["science_value"]),
            description=entry.get("description", ""),
            tags=_guess_tags(entry),
        )
        catalog[inst.id] = inst
    return catalog


_catalog: dict[str, Instrument] | None = None


def get_catalog() -> dict[str, Instrument]:
    global _catalog
    if _catalog is None:
        _catalog = load_catalog()
    return _catalog
