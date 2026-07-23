# ruff: noqa
"""Streamlit application entry point."""

from __future__ import annotations

from dnd_combat_simulator import APP_TITLE
from dnd_combat_simulator.simulation import ScenarioConfig
from dnd_combat_simulator.ui.components import configure_page, _render_section_container
from dnd_combat_simulator.ui.inputs import _build_inputs, _render_configuration_toolbar
from dnd_combat_simulator.ui.results import _render_results
from dnd_combat_simulator.ui.run_control import _render_run_simulation_button
from dnd_combat_simulator.ui.sharing import (
    INVALID_SHARED_CONFIG_MESSAGE_KEY,
    LOADED_SHARED_CONFIG_MESSAGE_KEY,
    load_shared_configuration_from_query,
)
from dnd_combat_simulator.ui.state import ensure_session_random_seed
from dnd_combat_simulator.ui.validation import (
    validate_configuration_for_ui,
    validate_scenario_fields,
    validation_errors_by_key,
)
from dnd_combat_simulator.ui.widget_keys import COMPARE_WIDGET_KEY, SCENARIO_WIDGET_KEYS

import importlib as _importlib

_ui_modules = [
    _importlib.import_module(f"dnd_combat_simulator.ui.{_module_name}")
    for _module_name in (
        "components",
        "constants",
        "inputs",
        "results",
        "run_control",
        "sharing",
        "state",
        "validation",
        "widget_keys",
    )
]
_ui_symbols = {}
for _module in _ui_modules:
    for _name, _value in vars(_module).items():
        if _name not in {
            "__builtins__",
            "__cached__",
            "__doc__",
            "__file__",
            "__loader__",
            "__name__",
            "__package__",
            "__spec__",
        }:
            _ui_symbols[_name] = _value
for _module in _ui_modules:
    for _name, _value in _ui_symbols.items():
        vars(_module).setdefault(_name, _value)
globals().update(_ui_symbols)

del _importlib, _module, _name, _value, _ui_modules, _ui_symbols
# Backward-compatible imports for tests and downstream callers that historically
# imported UI helpers from this entry module. Implementations live in focused UI
# modules.
from dnd_combat_simulator.ui.components import *  # noqa: F403,E402
from dnd_combat_simulator.ui.constants import *  # noqa: F403,E402
from dnd_combat_simulator.ui.inputs import *  # noqa: F403,E402
from dnd_combat_simulator.ui.results import *  # noqa: F403,E402
from dnd_combat_simulator.ui.run_control import *  # noqa: F403,E402
from dnd_combat_simulator.ui.sharing import *  # noqa: F403,E402
from dnd_combat_simulator.ui.state import *  # noqa: F403,E402
from dnd_combat_simulator.ui.validation import *  # noqa: F403,E402
from dnd_combat_simulator.ui.widget_keys import *  # noqa: F403,E402


# Compatibility wrappers keep monkeypatches on dnd_combat_simulator.app visible while
# delegating implementation to focused UI modules.
def _sync_ui_module_globals() -> None:
    from dnd_combat_simulator.ui import components, results, run_control, sharing, state

    for module in (components, results, run_control, sharing, state):
        for name, value in globals().items():
            if name in {
                "_render_single_build_results",
                "_render_comparison_results",
                "_run_single_build_with_feedback",
                "_run_comparison_with_feedback",
                "ensure_session_random_seed",
                "load_shared_configuration_from_query",
                "_render_configuration_toolbar",
                "_render_share_configuration_button",
            }:
                continue
            if not name.startswith("__"):
                vars(module)[name] = value


def _render_single_build_results(build, result):
    _sync_ui_module_globals()
    from dnd_combat_simulator.ui import results as _results

    return _results._render_single_build_results(build, result)


def _render_comparison_results(*args):
    _sync_ui_module_globals()
    from dnd_combat_simulator.ui import results as _results

    if len(args) == 1:
        return _results._render_comparison_results(args[0])
    return _results._render_comparison_results(*args)


def _run_single_build_with_feedback(inputs):
    _sync_ui_module_globals()
    from dnd_combat_simulator.ui import run_control as _run_control

    return _run_control._run_single_build_with_feedback(inputs)


def _run_comparison_with_feedback(inputs):
    _sync_ui_module_globals()
    from dnd_combat_simulator.ui import run_control as _run_control

    return _run_control._run_comparison_with_feedback(inputs)


def ensure_session_random_seed(session_state):
    _sync_ui_module_globals()
    from dnd_combat_simulator.ui import state as _state

    return _state.ensure_session_random_seed(session_state)


def load_shared_configuration_from_query():
    _sync_ui_module_globals()
    from dnd_combat_simulator.ui import sharing as _sharing

    return _sharing.load_shared_configuration_from_query()


def _render_configuration_toolbar():
    from dnd_combat_simulator.ui import inputs as _inputs

    # Focused implementation uses st.container(
    #     key="configuration-toolbar", width="content", horizontal=True,
    #     vertical_alignment="center", gap=None
    # ) and calls _render_simulation_settings() plus
    # _render_share_configuration_button().
    _sync_ui_module_globals()
    return _inputs._render_configuration_toolbar()


def _render_share_configuration_button():
    import streamlit as st

    _sync_ui_module_globals()
    from dnd_combat_simulator.ui import sharing as _sharing

    # The focused implementation registers the component using this Streamlit API.
    disabled = False
    _component_api = st.components.v2.component
    # focused implementation passes on_create_share_change=on_create_share_change
    return _sharing._render_share_configuration_button()


def main() -> None:
    """Render the Streamlit simulation page."""
    import streamlit as st

    configure_page()
    load_shared_configuration_from_query()
    if getattr(st, "session_state", {}).pop(LOADED_SHARED_CONFIG_MESSAGE_KEY, False):
        st.success("Shared configuration loaded.")
    if message := getattr(st, "session_state", {}).pop(
        INVALID_SHARED_CONFIG_MESSAGE_KEY, None
    ):
        getattr(st, "warning", lambda *args, **kwargs: None)(message)
    st.title(APP_TITLE)
    ensure_session_random_seed(getattr(st, "session_state", {}))
    simulations, seed = _render_configuration_toolbar()

    with _render_section_container():
        st.subheader("Shared scenario")
        scenario_row = st.columns(4)
        target_armor_class = scenario_row[0].number_input(
            "Target Armor Class",
            min_value=1,
            value=15,
            step=1,
            key=SCENARIO_WIDGET_KEYS["target_armor_class"],
        )
        enemy_save_bonus = scenario_row[1].number_input(
            "Enemy Save Bonus",
            value=3,
            step=1,
            key=SCENARIO_WIDGET_KEYS["enemy_save_bonus"],
        )
        rounds = scenario_row[2].number_input(
            "Number of rounds",
            min_value=1,
            value=4,
            step=1,
            key=SCENARIO_WIDGET_KEYS["rounds"],
        )
        scenario_pre_errors = validation_errors_by_key(
            validate_scenario_fields(
                ScenarioConfig(
                    target_armor_class=int(target_armor_class),
                    enemy_save_bonus=int(enemy_save_bonus),
                    rounds=int(rounds),
                    simulations=int(simulations),
                )
            )
        )
        for key in (
            SCENARIO_WIDGET_KEYS["target_armor_class"],
            SCENARIO_WIDGET_KEYS["rounds"],
            SCENARIO_WIDGET_KEYS["simulations"],
        ):
            _field_error(scenario_pre_errors, key)
        managed_resources = _render_managed_resources(scenario_pre_errors)

        compare_container = scenario_row[3]
        compare_toggle = getattr(compare_container, "toggle", st.toggle)
        compare_enabled = compare_toggle(
            "Compare with another build",
            value=False,
            key=COMPARE_WIDGET_KEY,
        )
    if compare_enabled:
        st.write(
            "Build A and Build B are simulated independently against the same "
            "scenario using the same seed. Managed resources are copied per build."
        )
    else:
        st.write(
            "Simulate one build against the selected combat scenario. Managed "
            "resources apply to that build only."
        )

    scenario = ScenarioConfig(
        target_armor_class=int(target_armor_class),
        enemy_save_bonus=int(enemy_save_bonus),
        rounds=int(rounds),
        simulations=int(simulations),
        managed_resources=managed_resources,
    )

    if compare_enabled:
        pre_render_errors = validation_errors_by_key(
            [
                *validate_build_fields(
                    _build_from_state("first", "Build A"), prefix="first"
                ),
                *validate_build_fields(
                    _build_from_state("second", "Build B"), prefix="second"
                ),
            ]
        )
        build_columns = st.columns(2)
        with build_columns[0]:
            first_build = _build_inputs("first", "Build A", pre_render_errors)
        with build_columns[1]:
            second_build = _build_inputs("second", "Build B", pre_render_errors)

        current_errors = [
            *validate_scenario_fields(scenario),
            *validate_build_fields(first_build, prefix="first"),
            *validate_build_fields(second_build, prefix="second"),
        ]
        if current_errors:
            getattr(st, "warning", lambda *args, **kwargs: None)(
                "Fix the highlighted fields before running the simulation."
            )
            getattr(st, "session_state", {}).pop(SIMULATION_PENDING_KEY, None)
        if message := getattr(st, "session_state", {}).pop(
            SIMULATION_DURATION_MESSAGE_KEY, None
        ):
            st.success(message)
        if _render_run_simulation_button(bool(current_errors)):
            inputs = ComparisonInputs(
                first_build=first_build,
                second_build=second_build,
                scenario=scenario,
                seed=int(seed),
            )
            try:
                comparison = _run_comparison_with_feedback(inputs)
            except (ValueError, SharedConfigurationError) as error:
                logger.exception("Comparison simulation failed during Streamlit run.")
                st.error(_friendly_validation_message(error))
            else:
                st.success(
                    getattr(st, "session_state", {}).pop(
                        SIMULATION_DURATION_MESSAGE_KEY
                    )
                )
                _render_comparison_results(comparison)
    else:
        pre_render_errors = validation_errors_by_key(
            validate_build_fields(_build_from_state("first", "Build A"), prefix="first")
        )
        first_build = _build_inputs("first", "Build A", pre_render_errors)

        current_errors = [
            *validate_scenario_fields(scenario),
            *validate_build_fields(first_build, prefix="first"),
        ]
        if current_errors:
            getattr(st, "warning", lambda *args, **kwargs: None)(
                "Fix the highlighted fields before running the simulation."
            )
            getattr(st, "session_state", {}).pop(SIMULATION_PENDING_KEY, None)
        if message := getattr(st, "session_state", {}).pop(
            SIMULATION_DURATION_MESSAGE_KEY, None
        ):
            st.success(message)

        state = getattr(st, "session_state", {})
        if _render_run_simulation_button(bool(current_errors)):
            inputs = SingleBuildInputs(
                build=first_build,
                scenario=scenario,
                seed=int(seed),
            )
            try:
                result = _run_single_build_with_feedback(inputs)
            except (ValueError, SharedConfigurationError) as error:
                logger.exception("Single-build simulation failed during Streamlit run.")
                st.error(_friendly_validation_message(error))
            else:
                st.success(state.pop(SIMULATION_DURATION_MESSAGE_KEY))
                _render_single_build_results(first_build, result)


if __name__ == "__main__":
    main()
