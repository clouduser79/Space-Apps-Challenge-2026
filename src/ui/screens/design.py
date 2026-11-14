"""Spacecraft Bus and Payload screens.

Both are catalogues of toggleable part cards grouped by role. Cards are
built once; `refresh()` only restyles them, so clicking Add/Remove is
instant and the scroll position never jumps.
"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from src.game.spacecraft import BUS_COMPONENTS
from src.ui import theme as T
from src.ui.screens.base import Screen
from src.ui.widgets import (Badge, Chip, ScrollFrame, SelectableCard,
                            glossary_text, style_toggle, text)

COLUMNS = 2


class PartCard(SelectableCard):
    """Catalogue card: name + toggle, description, stat chips, tags."""

    def __init__(self, master, name: str, description: str,
                 chips: list[tuple[str, str]], on_toggle: Callable[[], None],
                 tags: list[str] | None = None) -> None:
        super().__init__(master, command=on_toggle)
        self.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(sticky="ew", padx=T.PAD, pady=(14, 0))
        top.grid_columnconfigure(0, weight=1)
        glossary_text(top, name, T.H3).grid(row=0, column=0, sticky="ew",
                                            padx=(0, T.PAD_SM))
        self.toggle = ctk.CTkButton(top, text="", width=92, height=30,
                                    corner_radius=T.RADIUS_SM, border_width=1,
                                    font=T.font(12, "bold"), command=on_toggle)
        self.toggle.grid(row=0, column=1, sticky="e")

        glossary_text(self, description, T.SMALL, T.TEXT_MUTED).grid(
            sticky="ew", padx=T.PAD, pady=(4, 0))

        chip_row = ctk.CTkFrame(self, fg_color="transparent")
        chip_row.grid(sticky="w", padx=T.PAD, pady=(10, 0 if tags else 14))
        for i, (label, tone) in enumerate(chips):
            Chip(chip_row, label, tone).grid(row=0, column=i, padx=(0, 6))

        if tags:
            tag_row = ctk.CTkFrame(self, fg_color="transparent")
            tag_row.grid(sticky="w", padx=T.PAD, pady=(8, 14))
            for i, tag in enumerate(tags):
                Badge(tag_row, tag.replace("_", " "), "violet").grid(
                    row=0, column=i, padx=(0, 6))
        self.finalize()

    def set_installed(self, installed: bool) -> None:
        self.set_selected(installed)
        style_toggle(self.toggle, installed)


class GroupHeader(ctk.CTkFrame):
    """Section title with an optional REQUIRED badge and live status."""

    def __init__(self, master, title: str, blurb: str, required: bool) -> None:
        super().__init__(master, fg_color="transparent")
        self.required = required
        self.grid_columnconfigure(1, weight=1)
        glossary_text(self, title, T.H2, natural=True).grid(row=0, column=0, sticky="w")
        if required:
            Badge(self, "Required", "warning").grid(row=0, column=1, sticky="w",
                                                    padx=10)
        self.status = text(self, "", (12, "bold"), anchor="e")
        self.status.grid(row=0, column=2, sticky="e")
        if blurb:
            glossary_text(self, blurb, T.SMALL, T.TEXT_DIM).grid(
                row=1, column=0, columnspan=3, sticky="ew", pady=(2, 0))

    def set_count(self, installed: int) -> None:
        if installed:
            self.status.configure(text=f"✓  {installed} installed", text_color=T.SUCCESS)
        elif self.required:
            self.status.configure(text="✕  Needed to fly", text_color=T.DANGER)
        else:
            self.status.configure(text="Optional", text_color=T.TEXT_DIM)


class CatalogScreen(Screen):
    """Shared layout: page header, then grouped cards in a 2-column grid."""

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.page_header().grid(row=0, column=0, sticky="ew", pady=(0, T.PAD))
        self.extra_header(row=1)
        self.body = ScrollFrame(self)
        self.body.grid(row=2, column=0, sticky="nsew")
        for col in range(COLUMNS):
            self.body.grid_columnconfigure(col, weight=1, uniform="card")
        self.cards: dict[str, PartCard] = {}
        self.headers: list[tuple[GroupHeader, list[str]]] = []
        self._row = 0

    def extra_header(self, row: int) -> None:
        """Optional strip between the page header and the catalogue."""

    def add_group(self, title: str, blurb: str, required: bool,
                  items: list[tuple[str, PartCard]]) -> None:
        header = GroupHeader(self.body, title, blurb, required)
        header.grid(row=self._row, column=0, columnspan=COLUMNS, sticky="ew",
                    pady=(0 if self._row == 0 else T.PAD_LG, 10), padx=(0, T.PAD_SM))
        self._row += 1
        for i, (key, card) in enumerate(items):
            card.grid(row=self._row + i // COLUMNS, column=i % COLUMNS, sticky="nsew",
                      padx=(0, T.PAD_SM), pady=(0, T.PAD_SM))
            self.cards[key] = card
        self._row += (len(items) + COLUMNS - 1) // COLUMNS
        self.headers.append((header, [k for k, _ in items]))

    def installed_ids(self) -> set[str]:
        raise NotImplementedError

    def refresh(self) -> None:
        owned = self.installed_ids()
        for key, card in self.cards.items():
            card.set_installed(key in owned)
        for header, keys in self.headers:
            header.set_count(sum(1 for k in keys if k in owned))


# ==========================================================================
# Spacecraft bus
# ==========================================================================
class BusScreen(CatalogScreen):
    key = "bus"
    title = "Spacecraft Bus"
    subtitle = ("The bus keeps your spacecraft alive. Every part adds mass, "
                "cost and power draw — watch the telemetry panel react.")

    # (title, blurb, component ids). Required groups match the systems
    # Spacecraft.missing_essentials() checks.
    GROUPS = [
        ("Power Generation", "Solar arrays are cheap near the Sun; RTGs work "
         "anywhere, even in long eclipses.",
         ["solar_small", "solar_standard", "solar_large", "rtg"]),
        ("Communications", "Downlink rate decides how much of your science "
         "data actually reaches Earth.", ["comms_basic", "comms_high"]),
        ("Attitude Control", "Points the spacecraft. Precise pointing is needed "
         "for sharp, high-resolution imaging.", ["adcs_basic", "adcs_precise"]),
        ("Avionics & Storage", "The onboard computer runs the mission and stores "
         "data between ground passes.", ["avionics", "storage_expanded"]),
        ("Structure", "The frame everything mounts to — bigger structures carry "
         "bigger payloads.", ["structure_small", "structure_standard", "structure_heavy"]),
        ("Propulsion", "Engines for orbit maintenance and big manoeuvres.",
         ["propulsion_basic", "propulsion_advanced"]),
    ]
    REQUIRED = {"Power Generation", "Communications", "Attitude Control",
                "Avionics & Storage"}

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        placed: set[str] = set()
        for title, blurb, ids in self.GROUPS:
            ids = [cid for cid in ids if cid in BUS_COMPONENTS]
            placed.update(ids)
            self._add(title, blurb, title in self.REQUIRED, ids)
        rest = [cid for cid in BUS_COMPONENTS if cid not in placed]
        if rest:   # any catalogue entries added later still show up
            self._add("Other", "", False, rest)

    def _add(self, title, blurb, required, ids) -> None:
        if ids:
            self.add_group(title, blurb, required,
                           [(cid, self._card(cid)) for cid in ids])

    def _card(self, cid: str) -> PartCard:
        c = BUS_COMPONENTS[cid]
        chips = [(f"{c.mass_kg:g} kg", "neutral"), (T.money(c.cost_usd), "neutral")]
        if c.power_w:
            chips.append((f"−{c.power_w:g} W", "neutral"))
        if c.power_gen_w:
            chips.append((f"+{c.power_gen_w:g} W gen", "success"))
        if c.comms_mbps:
            chips.append((f"{c.comms_mbps:g} Mbps", "accent"))
        if c.storage_gb:
            chips.append((f"{c.storage_gb:,.0f} GB", "accent"))
        return PartCard(self.body, c.name, c.description, chips,
                        on_toggle=lambda: self._toggle(cid))

    def installed_ids(self) -> set[str]:
        return {c.id for c in self.mission.spacecraft.bus}

    def _toggle(self, cid: str) -> None:
        if cid in self.installed_ids():
            self.mission.remove_bus_component(cid)
        else:
            self.mission.add_bus_component(BUS_COMPONENTS[cid])
        self.app.on_design_changed()


# ==========================================================================
# Science payload
# ==========================================================================
class PayloadScreen(CatalogScreen):
    key = "payload"
    title = "Science Payload"
    subtitle = ("Instruments are why you fly. More science means more mass, "
                "power, cost — and more data to send home.")

    TAG_GROUPS = [
        ("imaging", "Imaging & Mapping", "Cameras for context, mapping and detail."),
        ("spectroscopy", "Spectroscopy & Composition", "What surfaces and "
         "atmospheres are made of."),
        ("subsurface", "Subsurface & Ice", "Seeing beneath the surface."),
        ("space_weather", "Space Weather", "Fields and particles around the spacecraft."),
        ("sample_return", "Sample Return", "Bring a piece of another world home."),
        ("comms", "Communications", "Relay payloads."),
    ]

    def extra_header(self, row: int) -> None:
        # Required-capability strip, rebuilt per mission in refresh()
        self.needs = ctk.CTkFrame(self, fg_color="transparent")
        self.needs.grid(row=row, column=0, sticky="ew", pady=(0, T.PAD))
        self._needs_key = None

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self._built_for = None

    def _build_catalog(self) -> None:
        """(Re)build cards when the scenario changes (allowed instruments)."""
        for child in self.body.winfo_children():
            child.destroy()
        self.cards.clear()
        self.headers.clear()
        self._row = 0
        allowed = self.mission.scenario.allowed_instruments
        groups: dict[str, list] = {}
        for iid, inst in self.app.instruments.items():
            if allowed and iid not in allowed:
                continue
            tag = next((t for t, _, _ in self.TAG_GROUPS if t in inst.tags), "other")
            groups.setdefault(tag, []).append((iid, inst))
        meta = [(t, title, blurb) for t, title, blurb in self.TAG_GROUPS]
        meta.append(("other", "Other Instruments", ""))
        for tag, title, blurb in meta:
            if tag in groups:
                self.add_group(title, blurb, False,
                               [(iid, self._card(iid, inst)) for iid, inst in groups[tag]])
        self._built_for = self.mission.scenario.id

    def _card(self, iid: str, inst) -> PartCard:
        chips = [(f"{inst.mass_kg:g} kg", "neutral"),
                 (f"{inst.power_w:g} W", "neutral"),
                 (T.money(inst.cost_usd), "neutral"),
                 (f"{inst.data_rate_mbps:g} Mbps", "accent"),
                 (f"Science {inst.science_value:g}", "violet")]
        return PartCard(self.body, inst.name, inst.description, chips,
                        on_toggle=lambda: self._toggle(iid), tags=inst.tags)

    def _refresh_needs(self) -> None:
        scenario = self.mission.scenario
        caps = self.mission.spacecraft.capabilities
        key = (scenario.id, frozenset(caps & set(scenario.required_capabilities)))
        if key == self._needs_key:
            return
        self._needs_key = key
        for child in self.needs.winfo_children():
            child.destroy()
        if not scenario.required_capabilities:
            self.needs.grid_remove()
            return
        self.needs.grid()
        text(self.needs, "This mission needs:", T.SMALL, T.TEXT_MUTED).pack(
            side="left", padx=(0, 10))
        for cap in scenario.required_capabilities:
            ok = cap in caps
            Badge(self.needs, ("✓ " if ok else "✕ ") + cap.replace("_", " "),
                  "success" if ok else "danger").pack(side="left", padx=(0, 6))

    def installed_ids(self) -> set[str]:
        return {i.id for i in self.mission.spacecraft.payload}

    def refresh(self) -> None:
        if self._built_for != self.mission.scenario.id:
            self._build_catalog()
        self._refresh_needs()
        super().refresh()

    def _toggle(self, iid: str) -> None:
        if iid in self.installed_ids():
            self.mission.remove_instrument(iid)
        else:
            try:
                self.mission.add_instrument(self.app.instruments[iid])
            except ValueError as exc:
                self.app.toast(str(exc), "danger")
        self.app.on_design_changed()
