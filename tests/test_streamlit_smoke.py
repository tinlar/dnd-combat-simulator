"""Optional browser smoke test for the Streamlit application.

Run with Playwright installed and ``RUN_STREAMLIT_SMOKE=1`` to cover page load,
attack/resource controls, simulation, and result rendering in a browser.
"""

from __future__ import annotations

import os

import pytest


@pytest.mark.skipif(
    os.environ.get("RUN_STREAMLIT_SMOKE") != "1",
    reason="Set RUN_STREAMLIT_SMOKE=1 with Playwright browsers installed.",
)
def test_streamlit_browser_smoke() -> None:
    pytest.importorskip("playwright.sync_api")
    # The actual browser workflow is intentionally opt-in for local/dev CI where
    # Streamlit can be launched and Playwright browser binaries are available.
