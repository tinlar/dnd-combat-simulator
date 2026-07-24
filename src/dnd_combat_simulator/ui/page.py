"""Top-level Streamlit page orchestration."""

from __future__ import annotations

import logging
import os

from dnd_combat_simulator import APP_TITLE
from dnd_combat_simulator.sharing import SharedConfigurationError
from dnd_combat_simulator.simulation import ScenarioConfig
from dnd_combat_simulator.ui.components import (
    _render_section_container,
    configure_page,
)
from dnd_combat_simulator.ui.constants import (
    COMPARE_WIDGET_KEY,
    SCENARIO_WIDGET_KEYS,
    SIMULATION_DURATION_MESSAGE_KEY,
    SIMULATION_PENDING_KEY,
)
from dnd_combat_simulator.ui.inputs import (
    _build_inputs,
    _render_configuration_toolbar,
)
from dnd_combat_simulator.ui.results import (
    _render_comparison_results,
    _render_single_build_results,
)
from dnd_combat_simulator.ui.run_control import (
    ComparisonInputs,
    SingleBuildInputs,
    _render_run_simulation_button,
    _run_comparison_with_feedback,
    _run_single_build_with_feedback,
)
from dnd_combat_simulator.ui.sharing import (
    INVALID_SHARED_CONFIG_MESSAGE_KEY,
    LOADED_SHARED_CONFIG_MESSAGE_KEY,
    load_shared_configuration_from_query,
)
from dnd_combat_simulator.ui.state import (
    _build_from_state,
    ensure_session_random_seed,
)
from dnd_combat_simulator.ui.validation import (
    ValidationScope,
    _friendly_validation_message,
    validate_build_fields,
    validate_scenario_fields,
)
from dnd_combat_simulator.ui.validation_rendering import (
    _field_error,
    validation_errors_by_key,
)
from dnd_combat_simulator.ui.widget_tracking import (
    rendered_widget_keys,
    track_streamlit_widget_keys,
)

__all__ = ("main",)


def _build_level_validation_errors(errors):
    """Return legitimate non-field errors that still need an actionable message."""
    return [
        error
        for error in errors
        if (
            not error.key
            or error.key.endswith("-attack-ids")
            or error.scope in {ValidationScope.BUILD, ValidationScope.SCENARIO}
        )
    ]


def _active_rendered_validation_errors(errors, rendered_keys=None):
    """Return visible field errors plus actionable build/scenario errors."""
    rendered = set(rendered_keys or [])
    active = []
    for error in errors:
        if error.key and error.key in rendered:
            active.append(error)
        elif not error.key or error.key.endswith("-attack-ids"):
            active.append(error)
    return active


def _render_build_level_validation_errors(errors):
    import streamlit as st

    for error in _build_level_validation_errors(errors):
        target = error.build_key or "Scenario"
        if error.attack_id:
            target = f"{target} attack {error.attack_id}"
        st.error(f"{target}: {error.message}", icon="⚠️")


def _validation_diagnostics_enabled() -> bool:
    return os.environ.get("DND_VALIDATION_DIAGNOSTICS", "").lower() in {
        "1",
        "true",
        "yes",
    }


def _render_validation_diagnostics(errors, rendered_keys, builds):
    if not _validation_diagnostics_enabled():
        return
    import streamlit as st

    build_names = {prefix: build.name for prefix, build in builds.items()}
    attack_names = {
        (prefix, profile.attack_id): profile.name
        for prefix, build in builds.items()
        for profile in build.attack_profiles
    }
    attack_ids = {key for key in attack_names}
    with st.expander("Development validation diagnostics", expanded=False):
        for issue in errors:
            exists = (
                (issue.build_key, issue.attack_id) in attack_ids
                if issue.attack_id
                else "n/a"
            )
            rendered = bool(issue.key and issue.key in rendered_keys)
            visible = rendered
            st.markdown(
                "\n".join(
                    [
                        f"- Build: `{issue.build_key or 'scenario'}` / "
                        f"`{build_names.get(issue.build_key or '', 'Scenario')}`",
                        f"- Attack ID: `{issue.attack_id or ''}`",
                        f"- Attack name: "
                        f"`{attack_names.get((issue.build_key or '', issue.attack_id), '') if issue.attack_id else ''}`",
                        f"- Scope: `{issue.scope}`",
                        f"- Field: `{issue.field or ''}`",
                        f"- Widget key: `{issue.key}`",
                        f"- Message: {issue.message}",
                        f"- Widget rendered this run: `{rendered}`",
                        f"- Attack card exists: `{exists}`",
                        f"- Controlling field enabled and visible: `{visible}`",
                    ]
                )
            )


logger = logging.getLogger(__name__)


def main() -> None:
    """Render the Streamlit simulation page."""
    import streamlit as st

    with track_streamlit_widget_keys(st):
        _main_tracked(st)


def _main_tracked(st) -> None:
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
    )

    if compare_enabled:
        pre_render_errors = validation_errors_by_key(
            [
                *validate_build_fields(
                    _build_from_state("first", "Build A"),
                    prefix="first",
                    available_resource_ids=frozenset(
                        r.resource_id
                        for r in _build_from_state("first", "Build A").managed_resources
                    ),
                ),
                *validate_build_fields(
                    _build_from_state("second", "Build B"),
                    prefix="second",
                    available_resource_ids=frozenset(
                        r.resource_id
                        for r in _build_from_state(
                            "second", "Build B"
                        ).managed_resources
                    ),
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
                available_resource_ids=frozenset(
                    r.resource_id for r in first_build.managed_resources
                ),
            ),
            *validate_build_fields(
                second_build,
                prefix="second",
                available_resource_ids=frozenset(
                    r.resource_id for r in second_build.managed_resources
                ),
            ),
        ]
        rendered_keys = rendered_widget_keys(getattr(st, "session_state", {}))
        active_errors = _active_rendered_validation_errors(current_errors, rendered_keys)
        if active_errors:
            getattr(st, "warning", lambda *args, **kwargs: None)(
                "Fix the highlighted fields before running the simulation."
            )
            _render_build_level_validation_errors(active_errors)
            _render_validation_diagnostics(
                current_errors,
                rendered_keys,
                {"first": first_build, "second": second_build},
            )
            getattr(st, "session_state", {}).pop(SIMULATION_PENDING_KEY, None)
        if message := getattr(st, "session_state", {}).pop(
            SIMULATION_DURATION_MESSAGE_KEY, None
        ):
            st.success(message)
        if _render_run_simulation_button(bool(active_errors)):
            fallback_errors = _active_rendered_validation_errors(
                [
                    *validate_scenario_fields(scenario),
                    *validate_build_fields(
                        _build_from_state("first", "Build A"),
                        prefix="first",
                        available_resource_ids=frozenset(
                            r.resource_id
                            for r in _build_from_state(
                                "first", "Build A"
                            ).managed_resources
                        ),
                    ),
                    *validate_build_fields(
                        _build_from_state("second", "Build B"),
                        prefix="second",
                        available_resource_ids=frozenset(
                            r.resource_id
                            for r in _build_from_state(
                                "second", "Build B"
                            ).managed_resources
                        ),
                    ),
                ],
                rendered_widget_keys(getattr(st, "session_state", {})),
            )
            if fallback_errors:
                getattr(st, "warning", lambda *args, **kwargs: None)(
                    "Fix the highlighted fields before running the simulation."
                )
                _render_build_level_validation_errors(fallback_errors)
                getattr(st, "session_state", {}).pop(SIMULATION_PENDING_KEY, None)
                return
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
        first_state_build = _build_from_state("first", "Build A")
        pre_render_errors = validation_errors_by_key(
            validate_build_fields(
                first_state_build,
                prefix="first",
                available_resource_ids=frozenset(
                    r.resource_id for r in first_state_build.managed_resources
                ),
            )
        )
        first_build = _build_inputs("first", "Build A", pre_render_errors)

        current_errors = [
            *validate_scenario_fields(scenario),
            *validate_build_fields(
                first_build,
                prefix="first",
                available_resource_ids=frozenset(
                    r.resource_id for r in first_build.managed_resources
                ),
            ),
        ]
        rendered_keys = rendered_widget_keys(getattr(st, "session_state", {}))
        active_errors = _active_rendered_validation_errors(current_errors, rendered_keys)
        if active_errors:
            getattr(st, "warning", lambda *args, **kwargs: None)(
                "Fix the highlighted fields before running the simulation."
            )
            _render_build_level_validation_errors(active_errors)
            _render_validation_diagnostics(
                current_errors,
                rendered_keys,
                {"first": first_build, "second": second_build},
            )
            getattr(st, "session_state", {}).pop(SIMULATION_PENDING_KEY, None)
        if message := getattr(st, "session_state", {}).pop(
            SIMULATION_DURATION_MESSAGE_KEY, None
        ):
            st.success(message)

        state = getattr(st, "session_state", {})
        if _render_run_simulation_button(bool(active_errors)):
            fallback_build = _build_from_state("first", "Build A")
            fallback_errors = _active_rendered_validation_errors(
                [
                    *validate_scenario_fields(scenario),
                    *validate_build_fields(
                        fallback_build,
                        prefix="first",
                        available_resource_ids=frozenset(
                            r.resource_id for r in fallback_build.managed_resources
                        ),
                    ),
                ],
                rendered_widget_keys(getattr(st, "session_state", {})),
            )
            if fallback_errors:
                getattr(st, "warning", lambda *args, **kwargs: None)(
                    "Fix the highlighted fields before running the simulation."
                )
                _render_build_level_validation_errors(fallback_errors)
                getattr(st, "session_state", {}).pop(SIMULATION_PENDING_KEY, None)
                return
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
