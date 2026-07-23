"""Streamlit application entry point.

Only ``main`` and ``configure_page`` are retained as intentional compatibility
imports for external callers that historically imported the application entry
point or page setup hook from this module. UI helper internals live in their
owning ``dnd_combat_simulator.ui`` modules.
"""

from __future__ import annotations

import time

# Additional explicit legacy imports kept temporarily for older tests and notebooks;
# they are intentionally excluded from __all__ so the public surface stays narrow.
from dnd_combat_simulator.ui.components import (
    _SHARE_TOOLBAR_COMPONENT,
    ATTACK_TOOLBAR_CSS,
    PAGE_WIDTH_CSS,
    _mount_unified_share_component,
    _render_section_container,
    configure_page,
)
from dnd_combat_simulator.ui.constants import (
    COMPARE_WIDGET_KEY,
    DAMAGE_FORMULA_HELP,
    FEATURE_HELP,
    LOADED_SHARED_CONFIG_TOKEN_KEY,
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
    _trigger_source_options,
)
from dnd_combat_simulator.ui.page import main
from dnd_combat_simulator.ui.results import (
    _comparison_round_chart_data,
    _profile_breakdown_rows,
    _profile_contribution_chart_data,
    _profile_damage_per_use_chart_data,
    _render_comparison_charts,
    _render_comparison_results,
    _render_single_build_charts,
    _render_single_build_results,
    _result_rows,
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
    _mark_simulation_pending,
    _render_run_simulation_button,
    _run_comparison_with_feedback,
    _run_single_build_with_feedback,
    run_comparison_from_inputs,
    run_simulation_from_inputs,
    run_single_build_from_inputs,
    validate_simulation_inputs,
)
from dnd_combat_simulator.ui.sharing import (
    _current_shared_configuration_url,
    _render_share_configuration_button,
    get_streamlit_share_store,
    load_shared_configuration_from_query,
    validate_configuration_for_ui,
)
from dnd_combat_simulator.ui.state import (
    _build_from_state,
    _copy_attack_widget_state,
    _delete_attack_state,
    _duplicate_attack_state,
    _managed_resources_from_state,
    hydrate_session_state_from_shared_configuration,
    next_default_attack_name,
)
from dnd_combat_simulator.ui.validation import validate_build_fields
from dnd_combat_simulator.ui.widget_keys import (
    attack_widget_prefix,
    build_attack_ids_key,
    feature_widget_key,
    managed_resource_widget_key,
    profile_widget_key,
)

__all__ = ("main", "configure_page")

_LEGACY_COMPATIBILITY_NAMES = (
    ATTACK_TOOLBAR_CSS,
    PAGE_WIDTH_CSS,
    DAMAGE_FORMULA_HELP,
    FEATURE_HELP,
    COMPARE_WIDGET_KEY,
    LOADED_SHARED_CONFIG_TOKEN_KEY,
    SCENARIO_WIDGET_KEYS,
    _attack_profile_inputs,
    _build_config_from_profiles,
    _feature_inputs,
    _profile_definitions,
    _comparison_round_chart_data,
    _profile_breakdown_rows,
    _profile_contribution_chart_data,
    _profile_damage_per_use_chart_data,
    _result_rows,
    _round_chart_data,
    _single_result_rows,
    _single_round_breakdown_rows,
    format_damage,
    format_rate,
    ComparisonInputs,
    SimulationInputs,
    SingleBuildInputs,
    run_comparison_from_inputs,
    run_simulation_from_inputs,
    run_single_build_from_inputs,
    validate_simulation_inputs,
    _current_shared_configuration_url,
    _build_from_state,
    hydrate_session_state_from_shared_configuration,
    next_default_attack_name,
    validate_build_fields,
    feature_widget_key,
    profile_widget_key,
    time,
    SIMULATION_DURATION_MESSAGE_KEY,
    SIMULATION_PENDING_KEY,
    SIMULATION_RUNNING_KEY,
    _SHARE_TOOLBAR_COMPONENT,
    _mount_unified_share_component,
    _render_section_container,
    _build_inputs,
    _render_configuration_toolbar,
    _render_managed_resources,
    _trigger_source_options,
    _render_comparison_charts,
    _render_comparison_results,
    _render_single_build_charts,
    _render_single_build_results,
    _mark_simulation_pending,
    _render_run_simulation_button,
    _run_comparison_with_feedback,
    _run_single_build_with_feedback,
    _render_share_configuration_button,
    get_streamlit_share_store,
    load_shared_configuration_from_query,
    validate_configuration_for_ui,
    _copy_attack_widget_state,
    _delete_attack_state,
    _duplicate_attack_state,
    _managed_resources_from_state,
    attack_widget_prefix,
    build_attack_ids_key,
    managed_resource_widget_key,
)


if __name__ == "__main__":
    main()
