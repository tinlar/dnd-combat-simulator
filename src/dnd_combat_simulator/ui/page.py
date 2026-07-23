"""Top-level Streamlit page orchestration."""

from __future__ import annotations

import logging
import time

from dnd_combat_simulator import APP_TITLE
from dnd_combat_simulator.sharing import SharedConfigurationError
from dnd_combat_simulator.simulation import ScenarioConfig
from dnd_combat_simulator.ui.components import (
    _SHARE_TOOLBAR_COMPONENT,
    ATTACK_TOOLBAR_CSS,
    CONFIGURATION_TOOLBAR_CSS,
    PAGE_WIDTH_CSS,
    SHARE_TOOLBAR_CSS,
    SHARE_TOOLBAR_HTML,
    SHARE_TOOLBAR_JS,
    _render_section_container,
    configure_page,
)
from dnd_combat_simulator.ui.constants import (
    ATTACK_DELETE_CONFIRMATION_KEY,
    COMPARE_WIDGET_KEY,
    DAMAGE_FORMULA_HELP,
    FEATURE_HELP,
    GENERATED_SHARE_FINGERPRINT_KEY,
    GENERATED_SHARE_URL_KEY,
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
    _average_attack_executions_per_combat,
    _average_attack_executions_per_round,
    _average_targets_damaged_per_combat,
    _average_targets_damaged_per_round,
    _comparison_round_chart_data,
    _profile_breakdown_rows,
    _profile_contribution_chart_data,
    _profile_damage_per_use_chart_data,
    _render_comparison_charts,
    _render_resource_usage,
    _render_single_build_charts,
    _result_rows,
    _round_breakdown_rows,
    _round_chart_data,
    _single_result_rows,
    _single_round_breakdown_rows,
    format_damage,
    format_rate,
)
from dnd_combat_simulator.ui.run_control import (
    ComparisonInputs,
    SimulationInputs,
    SingleBuildInputs,
    _render_run_simulation_button,
    run_comparison_from_inputs,
    run_simulation_from_inputs,
    run_single_build_from_inputs,
    validate_simulation_inputs,
)
from dnd_combat_simulator.ui.sharing import (
    INVALID_SHARED_CONFIG_MESSAGE_KEY,
    LOADED_SHARE_ID_KEY,
    LOADED_SHARED_CONFIG_MESSAGE_KEY,
    LOADED_SHARED_CONFIG_TOKEN_KEY,
    SHARE_ERROR_MESSAGE_KEY,
    _current_shared_configuration_url,
    _share_configuration_fingerprint,
    get_streamlit_share_store,
    get_supabase_share_store_from_secrets,
    serialize_shared_configuration,
)
from dnd_combat_simulator.ui.state import (
    ATTACK_WIDGET_STATE_FIELDS,
    _build_from_state,
    _clear_resource_from_profiles,
    _copy_attack_widget_state,
    _delete_attack_state,
    _duplicate_attack_state,
    _generate_default_seed,
    _resource_usage_profile_keys,
    hydrate_session_state_from_shared_configuration,
    next_default_attack_name,
)
from dnd_combat_simulator.ui.validation import (
    FieldValidationError,
    _field_error,
    _friendly_validation_message,
    validate_build_fields,
    validate_configuration_for_ui,
    validate_scenario_fields,
    validation_errors_by_key,
)
from dnd_combat_simulator.ui.widget_keys import (
    attack_widget_prefix,
    build_attack_ids_key,
    feature_widget_key,
    profile_widget_key,
    trigger_expanded_state_key,
)

__all__ = (
    "main",
    "configure_page",
    "ATTACK_TOOLBAR_CSS",
    "CONFIGURATION_TOOLBAR_CSS",
    "PAGE_WIDTH_CSS",
    "SHARE_TOOLBAR_CSS",
    "SHARE_TOOLBAR_HTML",
    "SHARE_TOOLBAR_JS",
    "_SHARE_TOOLBAR_COMPONENT",
    "DAMAGE_FORMULA_HELP",
    "FEATURE_HELP",
    "ATTACK_DELETE_CONFIRMATION_KEY",
    "COMPARE_WIDGET_KEY",
    "GENERATED_SHARE_FINGERPRINT_KEY",
    "GENERATED_SHARE_URL_KEY",
    "SCENARIO_WIDGET_KEYS",
    "SIMULATION_DURATION_MESSAGE_KEY",
    "SIMULATION_PENDING_KEY",
    "SIMULATION_RUNNING_KEY",
    "SHARE_ERROR_MESSAGE_KEY",
    "LOADED_SHARE_ID_KEY",
    "LOADED_SHARED_CONFIG_MESSAGE_KEY",
    "LOADED_SHARED_CONFIG_TOKEN_KEY",
    "_attack_profile_inputs",
    "_build_config_from_profiles",
    "_feature_inputs",
    "_profile_definitions",
    "_build_inputs",
    "_render_configuration_toolbar",
    "_render_simulation_settings",
    "_trigger_settings_expander",
    "_trigger_source_options",
    "_render_managed_resources",
    "_average_attack_executions_per_combat",
    "_average_attack_executions_per_round",
    "_average_targets_damaged_per_combat",
    "_average_targets_damaged_per_round",
    "_comparison_round_chart_data",
    "_profile_breakdown_rows",
    "_profile_contribution_chart_data",
    "_profile_damage_per_use_chart_data",
    "_render_comparison_charts",
    "_render_resource_usage",
    "_render_single_build_charts",
    "_result_rows",
    "_round_breakdown_rows",
    "_round_chart_data",
    "_single_result_rows",
    "_single_round_breakdown_rows",
    "format_damage",
    "format_rate",
    "_render_comparison_results",
    "_render_single_build_results",
    "ComparisonInputs",
    "SingleBuildInputs",
    "SimulationInputs",
    "run_comparison_from_inputs",
    "run_single_build_from_inputs",
    "run_simulation_from_inputs",
    "validate_simulation_inputs",
    "_render_run_simulation_button",
    "get_streamlit_share_store",
    "get_supabase_share_store_from_secrets",
    "load_shared_configuration_from_query",
    "serialize_shared_configuration",
    "_current_shared_configuration_url",
    "_share_configuration_fingerprint",
    "ATTACK_WIDGET_STATE_FIELDS",
    "_build_from_state",
    "_clear_resource_from_profiles",
    "_copy_attack_widget_state",
    "_delete_attack_state",
    "_duplicate_attack_state",
    "_generate_default_seed",
    "_resource_usage_profile_keys",
    "ensure_session_random_seed",
    "hydrate_session_state_from_shared_configuration",
    "next_default_attack_name",
    "attack_widget_prefix",
    "build_attack_ids_key",
    "feature_widget_key",
    "profile_widget_key",
    "trigger_expanded_state_key",
    "FieldValidationError",
    "_field_error",
    "_friendly_validation_message",
    "validate_build_fields",
    "validate_configuration_for_ui",
    "validate_scenario_fields",
    "validation_errors_by_key",
)

logger = logging.getLogger(__name__)


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


# Test seams for page orchestration: keep monkeypatches local to the owning page module
# while delegating behavior to focused implementation modules.
def _page_mount_unified_share_component(data, on_create_share_change):
    import streamlit as st

    component = st.components.v2.component(
        "share_toolbar",
        html=SHARE_TOOLBAR_HTML,
        css=SHARE_TOOLBAR_CSS,
        js=SHARE_TOOLBAR_JS,
    )
    return component(
        data=data,
        key="unified-share-configuration",
        on_create_share_change=on_create_share_change,
    )


def _render_single_build_results(build, result):
    from dnd_combat_simulator.ui import results as _results

    _results._render_single_build_charts = _render_single_build_charts
    return _results._render_single_build_results(build, result)


def _render_comparison_results(comparison):
    from dnd_combat_simulator.ui import results as _results

    _results._render_comparison_charts = _render_comparison_charts
    return _results._render_comparison_results(comparison)


def _run_single_build_with_feedback(inputs):
    from dnd_combat_simulator.ui import run_control as _run_control

    original_run = _run_control.run_single_build_from_inputs
    original_perf = _run_control.time.perf_counter
    _run_control.run_single_build_from_inputs = run_single_build_from_inputs
    _run_control.time.perf_counter = time.perf_counter
    try:
        return _run_control._run_single_build_with_feedback(inputs)
    finally:
        _run_control.run_single_build_from_inputs = original_run
        _run_control.time.perf_counter = original_perf


def _run_comparison_with_feedback(inputs):
    from dnd_combat_simulator.ui import run_control as _run_control

    original_run = _run_control.run_comparison_from_inputs
    original_perf = _run_control.time.perf_counter
    _run_control.run_comparison_from_inputs = run_comparison_from_inputs
    _run_control.time.perf_counter = time.perf_counter
    try:
        return _run_control._run_comparison_with_feedback(inputs)
    finally:
        _run_control.run_comparison_from_inputs = original_run
        _run_control.time.perf_counter = original_perf


def _mark_simulation_pending():
    from dnd_combat_simulator.ui.run_control import _mark_simulation_pending as impl

    return impl()


def ensure_session_random_seed(session_state):
    from dnd_combat_simulator.ui import state as _state

    original = _state._generate_default_seed
    _state._generate_default_seed = _generate_default_seed
    try:
        return _state.ensure_session_random_seed(session_state)
    finally:
        _state._generate_default_seed = original


def load_shared_configuration_from_query():
    from dnd_combat_simulator.ui import sharing as _sharing

    original = _sharing.get_streamlit_share_store
    _sharing.get_streamlit_share_store = get_streamlit_share_store
    try:
        return _sharing.load_shared_configuration_from_query()
    finally:
        _sharing.get_streamlit_share_store = original


def _current_short_shared_configuration_url(store):
    from dnd_combat_simulator.ui import sharing as _sharing

    original = _sharing.get_streamlit_share_store
    _sharing.get_streamlit_share_store = get_streamlit_share_store
    try:
        return _sharing._current_short_shared_configuration_url(store)
    finally:
        _sharing.get_streamlit_share_store = original


def _render_share_configuration_button():
    from dnd_combat_simulator.ui import sharing as _sharing

    original_store = _sharing.get_streamlit_share_store
    original_mount = _sharing._mount_unified_share_component
    original_fingerprint = _sharing._share_configuration_fingerprint
    original_serialize = _sharing.serialize_shared_configuration
    _sharing.get_streamlit_share_store = get_streamlit_share_store
    _sharing._mount_unified_share_component = _page_mount_unified_share_component
    _sharing._share_configuration_fingerprint = _share_configuration_fingerprint
    _sharing.serialize_shared_configuration = serialize_shared_configuration
    # st.components.v2.component is used by _mount_unified_share_component.
    try:
        return _sharing._render_share_configuration_button()
    finally:
        _sharing.get_streamlit_share_store = original_store
        _sharing._mount_unified_share_component = original_mount
        _sharing._share_configuration_fingerprint = original_fingerprint
        _sharing.serialize_shared_configuration = original_serialize
