"""Streamlit application compatibility entry point."""

from __future__ import annotations

from dnd_combat_simulator.ui.components import configure_page
from dnd_combat_simulator.ui.page import main

__all__ = ("configure_page", "main")


if __name__ == "__main__":
    main()
