"""XP shop window: spend XP to unlock premium parts, orbits and rockets."""

from __future__ import annotations

import customtkinter as ctk

from src.game.profile import buy
from src.game.shop import KIND_LABELS, SHOP_ITEMS
from src.game.spacecraft import BUS_COMPONENTS
from src.ui import theme as T
from src.ui.widgets import Badge, Card, ScrollFrame, ghost_button, primary_button, text


def item_name(app, item) -> str:
    """Display name of a shop item, looked up in its game catalogue."""
    if item.kind == "bus":
        return BUS_COMPONENTS[item.id].name
    if item.kind == "instrument":
        return app.instruments[item.id].name
    if item.kind == "orbit":
        return app.orbits[item.id].name
    return app.launch_vehicles[item.id].name


class ShopDialog(ctk.CTkToplevel):
    """Modal shop. `focus` highlights one item (e.g. after clicking a locked
    card). Buying updates the profile immediately and refreshes the game."""

    def __init__(self, app, focus: str | None = None) -> None:
        super().__init__(app, fg_color=T.SURFACE)
        self.app = app
        self.focus_id = focus
        self.title("XP Shop")
        self.geometry(f"640x{min(720, app.winfo_height() - 60)}")
        self.minsize(520, 420)
        self.transient(app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=T.PAD_LG, pady=(T.PAD_LG, T.PAD))
        head.grid_columnconfigure(0, weight=1)
        text(head, "🛒  XP Shop", T.H1).grid(row=0, column=0, sticky="w")
        self.balance = Badge(head, "", "violet")
        self.balance.grid(row=0, column=1, sticky="e")
        text(head, "Earn XP by flying missions, then unlock better parts, orbits and "
                   "rockets. Spending XP never lowers your rank.",
             T.SMALL, T.TEXT_MUTED, wraplength=560).grid(row=1, column=0, columnspan=2,
                                                         sticky="w", pady=(4, 0))

        self.body = ScrollFrame(self)
        self.body.grid(row=1, column=0, sticky="nsew", padx=(T.PAD_LG, T.PAD_SM))
        self.body.grid_columnconfigure(0, weight=1)
        ghost_button(self, "Close", self.destroy).grid(row=2, column=0, sticky="ew",
                                                       padx=T.PAD_LG, pady=T.PAD_LG)
        self._render()
        self.after(60, self._grab)

    def _grab(self) -> None:
        try:
            self.grab_set()
            self.focus_force()
        except Exception:
            pass

    def _render(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()
        profile = self.app.profile
        self.balance.set(f"{profile.balance:,} XP to spend", "violet")
        for kind, label in KIND_LABELS.items():
            items = [i for i in SHOP_ITEMS if i.kind == kind]
            if not items:
                continue
            text(self.body, label.upper(), T.CAPTION, T.ACCENT).grid(
                sticky="w", pady=(T.PAD, 6), padx=(0, T.PAD_SM))
            for item in sorted(items, key=lambda i: i.price):
                self._row(item, profile)

    def _row(self, item, profile) -> None:
        owned = item.id in profile.unlocks
        focused = item.id == self.focus_id
        card = Card(self.body, border_color=T.ACCENT if focused else T.BORDER,
                    border_width=2 if focused else 1)
        card.grid(sticky="ew", pady=(0, 8), padx=(0, T.PAD_SM))
        card.grid_columnconfigure(0, weight=1)
        text(card, item_name(self.app, item), T.H3).grid(row=0, column=0, sticky="w",
                                                         padx=T.PAD, pady=(12, 0))
        text(card, item.pitch, T.SMALL, T.TEXT_MUTED, wraplength=380).grid(
            row=1, column=0, sticky="w", padx=T.PAD, pady=(2, 12))
        right = ctk.CTkFrame(card, fg_color="transparent")
        right.grid(row=0, column=1, rowspan=2, sticky="e", padx=T.PAD)
        if owned:
            Badge(right, "✓ Unlocked", "success").pack()
            return
        Badge(right, f"{item.price:,} XP", "violet").pack(anchor="e", pady=(0, 6))
        short = item.price - profile.balance
        if short > 0:
            ghost_button(right, f"Need {short:,} more XP", lambda: None, width=150,
                         height=32, state="disabled").pack()
        else:
            primary_button(right, "Unlock", lambda i=item: self._buy(i), width=150,
                           height=32).pack()

    def _buy(self, item) -> None:
        if buy(self.app.profile, item.id):
            self.app.on_profile_changed()
            self.app.toast(f"Unlocked {item_name(self.app, item)}!", "success", "🔓", 2200)
            self._render()


def open_shop(app, focus: str | None = None) -> None:
    """Open the shop (blocks until closed)."""
    dialog = ShopDialog(app, focus)
    app.wait_window(dialog)
