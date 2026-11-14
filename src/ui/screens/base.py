"""Base class shared by every wizard screen."""

from __future__ import annotations

import customtkinter as ctk

from src.ui import theme as T
from src.ui.widgets import glossary_text


class Screen(ctk.CTkFrame):
    """One step of the mission designer.

    Subclasses build their widgets once in `__init__` and then only
    *update* them in `refresh()` — nothing is torn down and rebuilt on
    each click, which keeps the UI responsive.
    """

    key = ""                 # internal id, e.g. "bus"
    title = ""               # shown in the stepper and page header
    subtitle = ""            # one-line explanation under the title
    show_telemetry = True    # whether the live sidebar is visible here

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app

    @property
    def mission(self):
        return self.app.mission

    # --- lifecycle hooks -------------------------------------------------
    def refresh(self) -> None:
        """Sync widgets with the mission. Called when shown and after
        every design change while this screen is visible."""

    def on_show(self) -> None:
        self.refresh()

    def on_hide(self) -> None:
        """Called when the player navigates away."""

    # --- shared layout ---------------------------------------------------
    def page_header(self, parent=None) -> ctk.CTkFrame:
        """Title + subtitle block used at the top of each screen."""
        parent = parent or self
        box = ctk.CTkFrame(parent, fg_color="transparent")
        glossary_text(box, self.title, T.H1).pack(fill="x")
        if self.subtitle:
            glossary_text(box, self.subtitle, T.BODY, T.TEXT_MUTED).pack(
                fill="x", pady=(2, 0))
        return box
