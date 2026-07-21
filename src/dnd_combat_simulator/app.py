"""Streamlit application entry point."""

import streamlit as st

from dnd_combat_simulator import APP_TITLE


def main() -> None:
    """Render the initial Streamlit page."""
    st.title(APP_TITLE)


if __name__ == "__main__":
    main()
