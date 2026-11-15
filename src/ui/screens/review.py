"""Mission Review (dashboard): resources, design issues, manifest,
save/load and the leaderboard."""

from __future__ import annotations

import customtkinter as ctk

from src.game.save_load import SAVE_DIR, load_leaderboard, load_mission, save_mission
from src.ui import theme as T
from src.ui.screens.base import Screen
from src.ui.telemetry import readiness, resource_readings, systems_check
from src.ui.widgets import (Badge, Card, Chip, Meter, ScrollFrame, StatusRow,
                            auto_wrap, eyebrow, ghost_button, glossary_text,
                            primary_button, text)


class ReviewScreen(Screen):
    key = "dash"
    title = "Mission Review"
    subtitle = "One last look at every budget before you commit to launch."
    show_telemetry = False

    METERS = [("budget", "Budget"), ("mass", "Launch mass"), ("power", "Power load"),
              ("data", "Data vs downlink"), ("comms", "Downlink"), ("time", "Mission time")]

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.page_header().grid(row=0, column=0, sticky="ew", pady=(0, T.PAD))
        body = ScrollFrame(self)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=3, uniform="col")
        body.grid_columnconfigure(1, weight=2, uniform="col")
        left = ctk.CTkFrame(body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, T.PAD))
        left.grid_columnconfigure(0, weight=1)
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(0, T.PAD_SM))
        right.grid_columnconfigure(0, weight=1)

        self._build_resources(left)
        self._build_issues(left)
        self._build_manifest(left)
        self._build_readiness(right)
        self._build_saves(right)
        self._build_leaderboard(right)

    @staticmethod
    def _card(parent, title: str, color: str = T.ACCENT) -> Card:
        card = Card(parent)
        card.grid(sticky="ew", pady=(0, T.PAD))
        card.grid_columnconfigure(0, weight=1)
        eyebrow(card, title, color).grid(sticky="w", padx=T.PAD_LG - 4, pady=(T.PAD, 10))
        return card

    def _inner(self, card) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(card, fg_color="transparent")
        frame.grid(sticky="ew", padx=T.PAD_LG - 4, pady=(0, T.PAD))
        frame.grid_columnconfigure(0, weight=1)
        return frame

    # ------------------------------------------------------------------
    def _build_resources(self, parent) -> None:
        card = self._card(parent, "Resource budgets")
        grid = self._inner(card)
        grid.grid_columnconfigure((0, 1), weight=1, uniform="m")
        self.meters = {}
        for i, (key, caption) in enumerate(self.METERS):
            meter = Meter(grid, caption)
            meter.grid(row=i // 2, column=i % 2, sticky="ew",
                       padx=(0 if i % 2 == 0 else T.PAD_LG, 0), pady=(0, 14))
            self.meters[key] = meter

    def _build_issues(self, parent) -> None:
        card = self._card(parent, "Design issues", T.WARNING)
        self.issues = self._inner(card)

    def _build_manifest(self, parent) -> None:
        card = self._card(parent, "Spacecraft manifest", T.VIOLET_TEXT)
        self.manifest = self._inner(card)

    def _build_readiness(self, parent) -> None:
        card = self._card(parent, "Launch readiness")
        box = self._inner(card)
        self.ready_badge = Badge(box, "—")
        self.ready_badge.grid(sticky="w")
        self.ready_text = text(box, "", T.H2)
        self.ready_text.grid(sticky="ew", pady=(6, 10))
        auto_wrap(self.ready_text, box, padding=0)
        self.checks = ctk.CTkFrame(box, fg_color="transparent")
        self.checks.grid(sticky="ew")
        self.checks.grid_columnconfigure(0, weight=1)
        self._check_rows: list[StatusRow] = []
        primary_button(box, "Continue to launch  →",
                       lambda: self.app.show_screen("sim")).grid(sticky="ew", pady=(T.PAD, 0))

    def _build_saves(self, parent) -> None:
        card = self._card(parent, "Save & share")
        box = self._inner(card)
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.grid(sticky="ew")
        row.grid_columnconfigure((0, 1), weight=1, uniform="b")
        ghost_button(row, "Save design", self._save).grid(row=0, column=0, sticky="ew",
                                                          padx=(0, 4))
        ghost_button(row, "Load design", self._load).grid(row=0, column=1, sticky="ew",
                                                          padx=(4, 0))
        self.save_status = text(box, "Designs are stored in src/game/saves/.",
                                T.SMALL, T.TEXT_DIM)
        self.save_status.grid(sticky="ew", pady=(8, 0))

    def _build_leaderboard(self, parent) -> None:
        card = self._card(parent, "Leaderboard", T.WARNING)
        self.board = self._inner(card)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        m = self.mission
        for key, reading in resource_readings(m).items():
            self.meters[key].set(reading.fraction, reading.value, reading.tone, reading.hint)
        self._refresh_issues()
        self._refresh_manifest()
        self._refresh_readiness()
        self._refresh_leaderboard()

    def _refresh_issues(self) -> None:
        for child in self.issues.winfo_children():
            child.destroy()
        errors, warnings = self.mission.preflight_check()
        if not errors and not warnings:
            row = StatusRow(self.issues, "No issues — the design is feasible.")
            row.set("success")
            row.grid(sticky="ew")
            return
        for tone, items in (("danger", errors), ("warning", warnings)):
            for item in items:
                row = ctk.CTkFrame(self.issues, fg_color=T.TONES[tone][1], corner_radius=8)
                row.grid(sticky="ew", pady=(0, 6))
                row.grid_columnconfigure(1, weight=1)
                text(row, "✕" if tone == "danger" else "!", (13, "bold"),
                     T.TONES[tone][0], width=18, anchor="center").grid(
                    row=0, column=0, padx=(12, 8), pady=8, sticky="n")
                glossary_text(row, item, T.SMALL, T.TEXT).grid(
                    row=0, column=1, sticky="ew", padx=(0, 12), pady=8)

    def _refresh_manifest(self) -> None:
        for child in self.manifest.winfo_children():
            child.destroy()
        sc = self.mission.spacecraft
        for title, parts, tone in (("Bus", sc.bus, "neutral"),
                                   ("Payload", sc.payload, "violet")):
            text(self.manifest, title, (12, "bold"), T.TEXT_MUTED).grid(
                sticky="w", pady=(0, 6))
            flow = ctk.CTkFrame(self.manifest, fg_color="transparent")
            flow.grid(sticky="ew", pady=(0, 12))
            if not parts:
                text(flow, "Nothing installed yet", T.SMALL, T.TEXT_DIM).grid(sticky="w")
            for i, part in enumerate(parts):           # 3 chips per line
                Chip(flow, part.name, tone).grid(row=i // 3, column=i % 3, sticky="w",
                                                 padx=(0, 6), pady=(0, 6))

    def _refresh_readiness(self) -> None:
        label, tone = readiness(self.mission)
        self.ready_badge.set(label, tone)
        self.ready_text.configure(text={
            "success": "All systems go.",
            "warning": "Flyable, with cautions.",
            "danger": "Not ready — fix the issues first."}[tone])
        rows = systems_check(self.mission)
        while len(self._check_rows) < len(rows):
            row = StatusRow(self.checks, "")
            row.grid(sticky="ew", pady=2)
            self._check_rows.append(row)
        for row, (name, row_tone, detail) in zip(self._check_rows, rows):
            row.set(row_tone, detail, label=name)

    def _refresh_leaderboard(self) -> None:
        for child in self.board.winfo_children():
            child.destroy()
        entries = load_leaderboard()[:8]
        if not entries:
            text(self.board, "No missions flown yet. Yours could be first.",
                 T.SMALL, T.TEXT_DIM).grid(sticky="w")
            return
        self.board.grid_columnconfigure(1, weight=1)
        for i, e in enumerate(entries):
            rank_color = (T.GOLD, T.SILVER, T.BRONZE)[i] if i < 3 else T.TEXT_DIM
            text(self.board, f"{i + 1}", (13, "bold"), rank_color, width=22).grid(
                row=i, column=0, sticky="w", pady=3)
            text(self.board, e.get("mission_name", "?"), T.SMALL).grid(
                row=i, column=1, sticky="w", padx=(4, 8))
            score = float(e.get("score", 0))
            text(self.board, f"{score:.1f}", (13, "bold"),
                 T.TONES[T.score_tone(score)][0]).grid(row=i, column=2, sticky="e")
            Badge(self.board, "Success" if e.get("success") else "Partial",
                  "success" if e.get("success") else "neutral").grid(
                row=i, column=3, sticky="e", padx=(8, 0))

    # ------------------------------------------------------------------
    def _save(self) -> None:
        try:
            safe = "".join(c if c.isalnum() or c in "-_ " else "_"
                           for c in self.mission.name).strip() or "mission"
            path = save_mission(self.mission, f"{safe}.json")
            self.save_status.configure(text=f"✓  Saved to {path.name}", text_color=T.SUCCESS)
        except Exception as exc:
            self.save_status.configure(text=f"Save failed: {exc}", text_color=T.DANGER)

    def _load(self) -> None:
        files = sorted(SAVE_DIR.glob("*.json")) if SAVE_DIR.exists() else []
        if not files:
            self.save_status.configure(text="No saved designs found.", text_color=T.WARNING)
            return
        picked = LoadDialog(self.app, [f.name for f in files]).result
        if not picked:
            return
        try:
            self.app.replace_mission(load_mission(picked))
            self.save_status.configure(text=f"✓  Loaded {picked}", text_color=T.SUCCESS)
        except Exception as exc:
            self.save_status.configure(text=f"Load failed: {exc}", text_color=T.DANGER)


class LoadDialog(ctk.CTkToplevel):
    """Modal picker listing saved designs. Blocks until closed."""

    def __init__(self, root, names: list[str]) -> None:
        super().__init__(root, fg_color=T.SURFACE)
        self.result: str | None = None
        self.title("Load mission design")
        self.geometry("420x420")
        self.transient(root)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        text(self, "Saved designs", T.H2).grid(sticky="w", padx=T.PAD_LG, pady=(T.PAD_LG, 8))
        listing = ScrollFrame(self)
        listing.grid(row=1, sticky="nsew", padx=T.PAD_LG)
        listing.grid_columnconfigure(0, weight=1)
        for name in names:
            ctk.CTkButton(listing, text=name, anchor="w", height=40, font=T.font(13),
                          fg_color=T.CARD, hover_color=T.CARD_HOVER, text_color=T.TEXT,
                          corner_radius=T.RADIUS_SM, border_width=1, border_color=T.BORDER,
                          command=lambda n=name: self._choose(n)).grid(
                sticky="ew", pady=(0, 6), padx=(0, T.PAD_SM))
        ghost_button(self, "Cancel", self.destroy).grid(sticky="ew", padx=T.PAD_LG,
                                                        pady=T.PAD_LG)
        self.after(50, self._grab)        # grab once the window is mapped
        root.wait_window(self)

    def _grab(self) -> None:
        try:
            self.grab_set()
            self.focus_force()
        except Exception:
            pass

    def _choose(self, name: str) -> None:
        self.result = name
        self.destroy()
