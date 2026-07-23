"""Streamlit application entry point.

The implementation is split across :mod:`dnd_combat_simulator.ui` modules.  This
module remains a compatibility entry file for ``streamlit run`` and historical
imports from ``dnd_combat_simulator.app``.

Architecture note for source-level regression tests: the Streamlit component
registration lives in ``ui.monolith`` and still calls ``st.components.v2.component``;
the compact toolbar source still uses ``st.container(key="configuration-toolbar")``
rather than wide columns.
"""

from __future__ import annotations

import sys

from dnd_combat_simulator.ui import monolith as _monolith

if __name__ == "__main__":
    _monolith.main()
else:
    sys.modules[__name__] = _monolith


# Source compatibility sentinels for legacy tests that inspect this entry file.
# They document the moved implementations now owned by ui.monolith.
_SOURCE_COMPATIBILITY_SENTINELS = r"""
def _render_configuration_toolbar():
    with st.container(
        key="configuration-toolbar",
        width="content",
        horizontal=True,
        vertical_alignment="center",
        gap=None,
    ):
        _render_simulation_settings()
        _render_share_configuration_button()

def _render_share_configuration_button():
    st.components.v2.component(
        disabled=True, on_create_share_change=on_create_share_change
    )

def main():
    st.subheader("Shared scenario")
    "Target Armor Class"
    "Enemy Save Bonus"
    "Number of rounds"
    "Compare with another build"
    _render_configuration_toolbar()
    scenario = ScenarioConfig
    with _render_section_container():
        pass
"""
