"""Top-level Streamlit page orchestration."""

from __future__ import annotations

import logging
import time

from dnd_combat_simulator import APP_TITLE
from dnd_combat_simulator.sharing import SharedConfigurationError
from dnd_combat_simulator.simulation import ScenarioConfig

# Imported attributes below are transitional test seams while tests finish moving to
# owner modules; they are intentionally omitted from __all__.
from dnd_combat_simulator.ui.components import (
    _SHARE_TOOLBAR_COMPONENT,
    ATTACK_TOOLBAR_CSS,
    CONFIGURATION_TOOLBAR_CSS,
    PAGE_WIDTH_CSS,
    SHARE_TOOLBAR_HTML,
    SHARE_TOOLBAR_JS,
    _render_section_container,
    configure_page,
)
from dnd_combat_simulator.ui.constants import (
    COMPARE_WIDGET_KEY,
    FEATURE_HELP,
    SCENARIO_WIDGET_KEYS,
    SIMULATION_DURATION_MESSAGE_KEY,
    SIMULATION_PENDING_KEY,
    SIMULATION_RUNNING_KEY,
)
from dnd_combat_simulator.ui.inputs import (
    _attack_profile_inputs,
    _build_config_from_profiles,
    _build_inputs,
    _feature_inputs,
    _profile_definitions,
    _render_configuration_toolbar,
    _render_managed_resources,
    _render_simulation_settings,
    _trigger_settings_expander,
    _trigger_source_options,
)
from dnd_combat_simulator.ui.results import (
    _comparison_round_chart_data,
    _profile_breakdown_rows,
    _profile_contribution_chart_data,
    _profile_damage_per_use_chart_data,
    _render_comparison_results,
    _render_single_build_results,
    _result_rows,
    _round_chart_data,
    _single_result_rows,
    _single_round_breakdown_rows,
)
from dnd_combat_simulator.ui.run_control import (
    ComparisonInputs,
    SingleBuildInputs,
    _mark_simulation_pending,
    _render_run_simulation_button,
    _run_comparison_with_feedback,
    _run_single_build_with_feedback,
)
from dnd_combat_simulator.ui.sharing import (
    INVALID_SHARED_CONFIG_MESSAGE_KEY,
    LOADED_SHARED_CONFIG_MESSAGE_KEY,
    LOADED_SHARED_CONFIG_TOKEN_KEY,
    _current_shared_configuration_url,
    _current_short_shared_configuration_url,
    _render_share_configuration_button,
    get_streamlit_share_store,
    load_shared_configuration_from_query,
)
from dnd_combat_simulator.ui.state import (
    _build_from_state,
    _copy_attack_widget_state,
    _delete_attack_state,
    _duplicate_attack_state,
    ensure_session_random_seed,
    hydrate_session_state_from_shared_configuration,
    next_default_attack_name,
)
from dnd_combat_simulator.ui.validation import (
    _friendly_validation_message,
    validate_build_fields,
    validate_configuration_for_ui,
    validate_scenario_fields,
)
from dnd_combat_simulator.ui.validation_rendering import (
    _field_error,
    validation_errors_by_key,
)
from dnd_combat_simulator.ui.widget_keys import (
    attack_widget_prefix,
    build_attack_ids_key,
    feature_widget_key,
    profile_widget_key,
)

__all__ = ("main",)

logger = logging.getLogger(__name__)

_TRANSITIONAL_TEST_SEAMS = (
    ATTACK_TOOLBAR_CSS,
    CONFIGURATION_TOOLBAR_CSS,
    PAGE_WIDTH_CSS,
    SHARE_TOOLBAR_HTML,
    SHARE_TOOLBAR_JS,
    _SHARE_TOOLBAR_COMPONENT,
    FEATURE_HELP,
    SIMULATION_RUNNING_KEY,
    _attack_profile_inputs,
    _build_config_from_profiles,
    _feature_inputs,
    _profile_definitions,
    _render_simulation_settings,
    _trigger_settings_expander,
    _trigger_source_options,
    _comparison_round_chart_data,
    _profile_breakdown_rows,
    _profile_contribution_chart_data,
    _profile_damage_per_use_chart_data,
    _result_rows,
    _round_chart_data,
    _single_result_rows,
    _single_round_breakdown_rows,
    _mark_simulation_pending,
    LOADED_SHARED_CONFIG_TOKEN_KEY,
    _current_shared_configuration_url,
    _current_short_shared_configuration_url,
    _render_share_configuration_button,
    get_streamlit_share_store,
    _copy_attack_widget_state,
    _delete_attack_state,
    _duplicate_attack_state,
    hydrate_session_state_from_shared_configuration,
    next_default_attack_name,
    validate_configuration_for_ui,
    attack_widget_prefix,
    build_attack_ids_key,
    feature_widget_key,
    profile_widget_key,
    time,
)


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
    available_resource_ids = frozenset(
        resource.resource_id for resource in managed_resources if resource.resource_id
    )

    if compare_enabled:
        pre_render_errors = validation_errors_by_key(
            [
                *validate_build_fields(
                    _build_from_state("first", "Build A"),
                    prefix="first",
                    available_resource_ids=available_resource_ids,
                ),
                *validate_build_fields(
                    _build_from_state("second", "Build B"),
                    prefix="second",
                    available_resource_ids=available_resource_ids,
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
            *validate_build_fields(
                first_build,
                prefix="first",
                available_resource_ids=available_resource_ids,
            ),
            *validate_build_fields(
                second_build,
                prefix="second",
                available_resource_ids=available_resource_ids,
            ),
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
            validate_build_fields(
                _build_from_state("first", "Build A"),
                prefix="first",
                available_resource_ids=available_resource_ids,
            )
        )
        first_build = _build_inputs("first", "Build A", pre_render_errors)

        current_errors = [
            *validate_scenario_fields(scenario),
            *validate_build_fields(
                first_build,
                prefix="first",
                available_resource_ids=available_resource_ids,
            ),
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
            single_inputs = SingleBuildInputs(
                build=first_build,
                scenario=scenario,
                seed=int(seed),
            )
            try:
                result = _run_single_build_with_feedback(single_inputs)
            except (ValueError, SharedConfigurationError) as error:
                logger.exception("Single-build simulation failed during Streamlit run.")
                st.error(_friendly_validation_message(error))
            else:
                st.success(state.pop(SIMULATION_DURATION_MESSAGE_KEY))
                _render_single_build_results(first_build, result)
