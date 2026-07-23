"""Focused Streamlit UI helpers."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import nullcontext
from typing import Any

from dnd_combat_simulator.build_math import BuildMathDefaults
from dnd_combat_simulator.combat import (
    AttackFeature,
    AttackRollMode,
    ResolutionType,
    SuccessfulSaveDamage,
    is_feature_available,
)
from dnd_combat_simulator.simulation import (
    AttackProfile,
    BuildConfig,
    ManagedResource,
    ResourceCost,
    TriggerFrequency,
    TriggerType,
    resolve_attack_profile_values,
)
from dnd_combat_simulator.ui.components import (
    CONFIGURATION_TOOLBAR_CSS,
    _render_section_container,
)
from dnd_combat_simulator.ui.constants import (
    ATTACK_DELETE_CONFIRMATION_KEY,
    DAMAGE_FORMULA_HELP,
    DAMAGE_FORMULA_PLACEHOLDER,
    FEATURE_HELP,
    FEATURE_LABELS,
    FEATURE_ORDER,
    MANAGED_RESOURCE_COUNT_KEY,
    MANAGED_RESOURCE_EXPANDED_KEY,
    MANAGED_RESOURCE_IDS_KEY,
    MAX_ATTACKS_PER_BUILD,
    NO_ELIGIBLE_TRIGGER_SOURCE_MESSAGE,
    RESOURCE_DELETE_CONFIRMATION_KEY,
    SCENARIO_WIDGET_KEYS,
)
from dnd_combat_simulator.ui.sharing import _render_share_configuration_button
from dnd_combat_simulator.ui.state import (
    _attack_confirmation_id,
    _attack_display_heading,
    _attack_ids_from_state,
    _clear_resource_from_profiles,
    _default_attack_name,
    _delete_attack_state,
    _delete_managed_resource_state,
    _dependent_attack_names,
    _duplicate_attack_state,
    _looks_like_widget_prefix,
    _managed_resource_ids_from_state,
    _managed_resources_from_state,
    _new_attack_id,
    _new_resource_id,
    _reset_triggers_referencing_attack,
    _resource_usage_profile_keys,
    features_summary,
    next_default_attack_name,
    resource_summary,
    trigger_summary,
)
from dnd_combat_simulator.ui.validation import _validate_profile_fields
from dnd_combat_simulator.ui.validation_rendering import _field_error, _render_error
from dnd_combat_simulator.ui.widget_keys import (
    _state_widget_prefix,
    attack_widget_prefix,
    build_attack_ids_key,
    build_math_state_key,
    feature_widget_key,
    managed_resource_widget_key,
    profile_prefix,
    profile_widget_key,
    trigger_expanded_state_key,
)


def format_features(features: frozenset[AttackFeature]) -> str:
    """Format selected profile features in stable interface order."""
    selected = [
        FEATURE_LABELS[feature] for feature in FEATURE_ORDER if feature in features
    ]
    return ", ".join(selected) if selected else "None"


def _features_summary_from_state(prefix: str) -> str:
    import streamlit as st

    features = frozenset(
        feature
        for feature in FEATURE_ORDER
        if getattr(st, "session_state", {}).get(
            feature_widget_key(prefix, feature), False
        )
    )
    return features_summary(features)


def _trigger_summary_from_state(build_prefix: str, attack_id: str) -> str:
    profile = _profile_from_state_for_summary(build_prefix, attack_id)
    profiles = tuple(
        _profile_from_state_for_summary(build_prefix, source_id)
        for source_id in _attack_ids_from_state(
            getattr(__import__("streamlit"), "session_state", {}), build_prefix
        )
    )
    return trigger_summary(profile, profiles)


def _resource_summary_from_state(build_prefix: str, attack_id: str) -> str:
    return resource_summary(
        _profile_from_state_for_summary(build_prefix, attack_id),
        _managed_resources_from_state(),
    )


def _profile_from_state_for_summary(build_prefix: str, attack_id: str) -> AttackProfile:
    import streamlit as st

    state = getattr(st, "session_state", {})
    prefix = _state_widget_prefix(build_prefix, attack_id)
    trigger_type = {
        "Another attack succeeds": TriggerType.AFTER_SUCCESS,
        "Another attack fails": TriggerType.AFTER_FAILURE,
        "Another attack critically hits": TriggerType.AFTER_CRITICAL,
        "Sometimes": TriggerType.SOMETIMES,
    }.get(
        str(state.get(profile_widget_key(prefix, "trigger_type"))), TriggerType.ALWAYS
    )
    resource_costs: tuple[ResourceCost, ...] = ()
    if state.get(profile_widget_key(prefix, "resource_enabled"), False):
        resource_costs = (
            ResourceCost(
                str(state.get(profile_widget_key(prefix, "resource_id"), "")),
                int(state.get(profile_widget_key(prefix, "resource_amount"), 1)),
            ),
        )
    return AttackProfile(
        str(state.get(profile_widget_key(prefix, "name"), "Attack")),
        5,
        str(state.get(profile_widget_key(prefix, "damage_formula"), "1d8+3")),
        1,
        attack_id=attack_id,
        trigger_type=trigger_type,
        trigger_source_attack_id=state.get(
            profile_widget_key(prefix, "trigger_source_attack_id")
        ),
        trigger_frequency={
            "Once per round": TriggerFrequency.ONCE_PER_ROUND,
            "Once per combat": TriggerFrequency.ONCE_PER_COMBAT,
        }.get(
            str(state.get(profile_widget_key(prefix, "trigger_frequency"))),
            TriggerFrequency.PER_SUCCESS,
        ),
        trigger_chance_percent=(
            int(state.get(profile_widget_key(prefix, "trigger_chance_percent"), 0))
            if str(
                state.get(profile_widget_key(prefix, "trigger_chance_percent"), "")
            ).isdigit()
            else None
        ),
        resource_costs=resource_costs,
        use_build_attack_bonus=state.get(
            profile_widget_key(prefix, "use_build_attack_bonus"), False
        ),
        use_build_save_dc=state.get(
            profile_widget_key(prefix, "use_build_save_dc"), False
        ),
        use_build_damage_modifier=state.get(
            profile_widget_key(prefix, "use_build_damage_modifier"), False
        ),
    )


def _feature_inputs(
    prefix: str, resolution_type: ResolutionType, affected_targets: int = 1
) -> frozenset[AttackFeature]:
    """Render feats and features controls for one attack profile."""
    import streamlit as st

    selected = set()
    expander = getattr(st, "expander", None)
    checkbox = getattr(st, "checkbox", None)
    if expander is None or checkbox is None:
        return frozenset()
    try:
        feature_context = expander(
            f"{_features_summary_from_state(prefix)}",
            expanded=False,
            key=f"{prefix}-features-expanded",
        )
    except TypeError:
        feature_context = expander(
            f"{_features_summary_from_state(prefix)}", expanded=False
        )
    with feature_context:
        columns = getattr(st, "columns", None)
        feature_columns = columns(min(3, len(FEATURE_ORDER))) if columns else None
        for index, feature in enumerate(FEATURE_ORDER):
            disabled = not is_feature_available(
                feature, resolution_type, affected_targets=affected_targets
            )
            if disabled:
                getattr(st, "session_state", {}).pop(
                    feature_widget_key(prefix, feature), None
                )
            target = (
                feature_columns[index % len(feature_columns)] if feature_columns else st
            )
            target_checkbox = getattr(target, "checkbox", checkbox)
            checked = target_checkbox(
                FEATURE_LABELS[feature],
                value=False,
                key=feature_widget_key(prefix, feature),
                help=FEATURE_HELP[feature],
                disabled=disabled,
            )
            if checked and not disabled:
                selected.add(feature)
    return frozenset(selected)


def _trigger_source_options(
    build_prefix: str, current_attack_id: str | None = None
) -> list[tuple[str, str]]:
    if current_attack_id is None:
        current_attack_id = build_prefix
        build_prefix = current_attack_id.split("-", 1)[0]
    import streamlit as st

    state = getattr(st, "session_state", {})
    if _looks_like_widget_prefix(build_prefix, current_attack_id):
        count = int(state.get(f"{build_prefix}-additional-attack-count", 0))
        attack_ids = [profile_prefix(build_prefix, index) for index in range(count + 1)]
    else:
        attack_ids = _attack_ids_from_state(state, build_prefix)

    def source_of(attack_id: str) -> str | None:
        return state.get(
            profile_widget_key(
                _state_widget_prefix(build_prefix, attack_id),
                "trigger_source_attack_id",
            )
        )

    def would_create_cycle(candidate_id: str) -> bool:
        seen: set[str] = set()
        current: str | None = candidate_id
        while current and current not in seen:
            if current == current_attack_id:
                return True
            seen.add(current)
            current = source_of(current)
        return False

    raw_names: list[tuple[str, str, int]] = []
    for index, source_id in enumerate(attack_ids):
        default_name = _default_attack_name(index)
        source_prefix = _state_widget_prefix(build_prefix, source_id)
        name = (
            str(
                state.get(profile_widget_key(source_prefix, "name"), default_name)
            ).strip()
            or default_name
        )
        raw_names.append((source_id, name, index + 1))
    names = [name for _, name, _ in raw_names]
    duplicate_names = {name for name in names if names.count(name) > 1}
    options: list[tuple[str, str]] = []
    for source_id, name, ordinal in raw_names:
        if source_id == current_attack_id or would_create_cycle(source_id):
            continue
        label = f"{name} - Attack {ordinal}" if name in duplicate_names else name
        options.append((source_id, label))
    return options


def _trigger_frequency_labels(
    source_resolution_type: ResolutionType,
) -> tuple[str, str, str]:
    del source_resolution_type
    return ("Every successful resolution", "Once per round", "Once per combat")


def _trigger_settings_expander(
    prefix: str, build_prefix: str | None = None, attack_id: str | None = None
):
    build_prefix = build_prefix or prefix.split("-", 1)[0]
    attack_id = attack_id or prefix
    """Return the Trigger Settings expander with stable profile-specific state."""
    import streamlit as st

    expander = getattr(st, "expander", None)
    if expander is None:
        return nullcontext()
    try:
        return expander(
            _trigger_summary_from_state(build_prefix, attack_id),
            expanded=False,
            key=trigger_expanded_state_key(prefix),
        )
    except TypeError:
        return expander(
            _trigger_summary_from_state(build_prefix, attack_id), expanded=False
        )


def _render_managed_resources(
    errors_by_key: dict[str, str] | None = None,
) -> tuple[ManagedResource, ...]:
    import streamlit as st

    errors_by_key = errors_by_key or {}
    state = getattr(st, "session_state", {})
    resource_ids = _managed_resource_ids_from_state(state)
    count = len(resource_ids)
    expander = getattr(st, "expander", None)
    with (
        expander(
            "Managed Resources",
            expanded=False,
            key=MANAGED_RESOURCE_EXPANDED_KEY,
        )
        if expander is not None
        else nullcontext()
    ):
        caption = getattr(st, "caption", None)
        if caption is not None:
            caption(
                "Each simulated build receives its own independent copy of these "
                "starting resources."
            )
        resources: list[ManagedResource] = []
        for index, resource_id in enumerate(resource_ids):
            id_key = managed_resource_widget_key(resource_id, "id")
            state[id_key] = resource_id
            cols = st.columns([3, 2, 1])
            name = cols[0].text_input(
                "Resource name",
                key=managed_resource_widget_key(resource_id, "name"),
                value=f"Resource {index + 1}",
            )
            _field_error(
                errors_by_key, managed_resource_widget_key(resource_id, "name")
            )
            starting = cols[1].number_input(
                "Starting value",
                min_value=0,
                step=1,
                key=managed_resource_widget_key(resource_id, "starting-value"),
                value=0,
            )
            _field_error(
                errors_by_key,
                managed_resource_widget_key(resource_id, "starting-value"),
            )
            resource_id = str(state[id_key])
            used_by = _resource_usage_profile_keys(resource_id)
            if cols[2].button(
                ":material/delete:",
                key=managed_resource_widget_key(resource_id, "delete"),
                help=f"Delete {name}. Requires confirmation.",
                type="secondary",
            ):
                state[RESOURCE_DELETE_CONFIRMATION_KEY] = resource_id
            if state.get(RESOURCE_DELETE_CONFIRMATION_KEY) == resource_id:
                getattr(st, "warning", lambda *args, **kwargs: None)(
                    f"Delete resource {name}? Dependent attacks in Build A "
                    + "and Build B: "
                    + (", ".join(used_by) if used_by else "None")
                    + ". Dependent resource requirements will be cleared."
                )
                confirm_cols = st.columns([1, 1, 4])
                if confirm_cols[0].button(
                    "Confirm Delete",
                    key=managed_resource_widget_key(resource_id, "confirm-delete"),
                    type="tertiary",
                ):
                    _clear_resource_from_profiles(resource_id)
                    _delete_managed_resource_state(resource_id)
                    state.pop(RESOURCE_DELETE_CONFIRMATION_KEY, None)
                    rerun = getattr(st, "rerun", None)
                    if rerun is not None:
                        rerun()
                if confirm_cols[1].button(
                    "Cancel",
                    key=managed_resource_widget_key(resource_id, "cancel-delete"),
                ):
                    state.pop(RESOURCE_DELETE_CONFIRMATION_KEY, None)
                    rerun = getattr(st, "rerun", None)
                    if rerun is not None:
                        rerun()
            resources.append(ManagedResource(resource_id, str(name), int(starting)))
        if getattr(st, "button", lambda *args, **kwargs: False)(
            "Add Resource", key="scenario-add-managed-resource"
        ):
            new_id = _new_resource_id(count)
            state[MANAGED_RESOURCE_IDS_KEY] = [*resource_ids, new_id]
            state[MANAGED_RESOURCE_COUNT_KEY] = count + 1
            state[managed_resource_widget_key(new_id, "name")] = f"Resource {count + 1}"
            state[managed_resource_widget_key(new_id, "starting-value")] = 0
            rerun = getattr(st, "rerun", None)
            if rerun is not None:
                rerun()
    return tuple(resources)


def _safe_checkbox(st: Any, label: str, *, key: str, default: bool) -> bool:
    import sys

    streamlit_module = sys.modules.get("streamlit")
    state = getattr(
        st, "session_state", getattr(streamlit_module, "session_state", {})
    )
    if not isinstance(state, Mapping):
        state = getattr(streamlit_module, "session_state", {})
    kwargs: dict[str, object] = {"key": key}
    if key not in state:
        kwargs["value"] = default
    checkbox = getattr(st, "checkbox", None)
    if checkbox is None:
        value = state.get(key, default)
    else:
        value = checkbox(label, **kwargs)
    if type(value) is not bool:
        msg = f"{key} must be a boolean"
        raise ValueError(msg)
    return value


def _attack_profile_inputs(
    prefix: str,
    default_name: str,
    errors_by_key: dict[str, str] | None = None,
    *,
    attack_id: str | None = None,
    math_defaults: BuildMathDefaults | None = None,
) -> AttackProfile:
    """Render and collect one attack profile's input controls."""
    import streamlit as st

    errors_by_key = errors_by_key or {}
    build_prefix = prefix.split("-", 1)[0]
    domain_attack_id = attack_id or prefix
    attack_name_key = profile_widget_key(prefix, "name")
    session_state = getattr(st, "session_state", {})
    resolved_math_defaults = (
        BuildMathDefaults() if math_defaults is None else math_defaults
    )
    if attack_name_key in session_state:
        attack_name = st.text_input("Attack name", key=attack_name_key)
    else:
        attack_name = st.text_input(
            "Attack name", value=default_name, key=attack_name_key
        )
    _field_error(errors_by_key, profile_widget_key(prefix, "name"))
    resolution_type_label = st.selectbox(
        "Resolution Type",
        options=["Attack Roll", "Saving Throw", "Automatic Damage"],
        index=0,
        key=profile_widget_key(prefix, "resolution_type"),
    )
    resolution_type = {
        "Attack Roll": ResolutionType.ATTACK_ROLL,
        "Saving Throw": ResolutionType.SAVING_THROW,
        "Automatic Damage": ResolutionType.AUTOMATIC_DAMAGE,
    }[resolution_type_label]
    _field_error(errors_by_key, profile_widget_key(prefix, "resolution_type"))
    def _row_text(column: Any, text: str) -> None:
        writer = getattr(column, "markdown", None) or getattr(st, "markdown", None)
        if writer is not None:
            writer(text)

    use_build_attack_bonus = bool(
        session_state.get(profile_widget_key(prefix, "use_build_attack_bonus"), True)
    )
    use_build_save_dc = bool(
        session_state.get(profile_widget_key(prefix, "use_build_save_dc"), True)
    )

    if resolution_type is ResolutionType.ATTACK_ROLL:
        attack_bonus_key = profile_widget_key(prefix, "attack_bonus")
        attack_row = st.columns(4)
        _row_text(attack_row[0], "**Attack Bonus**")
        use_build_attack_bonus = _safe_checkbox(
            attack_row[1],
            "Use Build Default",
            key=profile_widget_key(prefix, "use_build_attack_bonus"),
            default=True,
        )
        attack_bonus_custom_key = f"{attack_bonus_key}-custom-value"
        if use_build_attack_bonus:
            attack_bonus = session_state.get(attack_bonus_custom_key, 5)
            if attack_bonus_key in session_state:
                previous_attack_bonus = session_state[attack_bonus_key]
                if previous_attack_bonus != resolved_math_defaults.attack_bonus:
                    attack_bonus = previous_attack_bonus
                    session_state[attack_bonus_custom_key] = previous_attack_bonus
            session_state[attack_bonus_key] = resolved_math_defaults.attack_bonus
            attack_row[2].number_input(
                "Attack Bonus value",
                value=resolved_math_defaults.attack_bonus,
                step=1,
                key=attack_bonus_key,
                disabled=True,
                label_visibility="collapsed",
            )
        elif attack_bonus_custom_key in session_state:
            session_state[attack_bonus_key] = session_state[attack_bonus_custom_key]
            attack_bonus = attack_row[2].number_input(
                "Attack Bonus value",
                step=1,
                key=attack_bonus_key,
                label_visibility="collapsed",
            )
        elif attack_bonus_key in session_state:
            attack_bonus = attack_row[2].number_input(
                "Attack Bonus value",
                step=1,
                key=attack_bonus_key,
                label_visibility="collapsed",
            )
        else:
            attack_bonus = attack_row[2].number_input(
                "Attack Bonus value",
                value=5,
                step=1,
                key=attack_bonus_key,
                label_visibility="collapsed",
            )
        effective_attack_bonus = (
            resolved_math_defaults.attack_bonus
            if use_build_attack_bonus
            else int(attack_bonus)
        )
        _row_text(attack_row[3], f"Effective: {effective_attack_bonus:+d}")
        _field_error(errors_by_key, profile_widget_key(prefix, "attack_bonus"))
        save_dc = None
    elif resolution_type is ResolutionType.SAVING_THROW:
        attack_bonus = None
        save_dc_key = profile_widget_key(prefix, "save_dc")
        save_row = st.columns(4)
        _row_text(save_row[0], "**Save DC**")
        use_build_save_dc = _safe_checkbox(
            save_row[1],
            "Use Build Default",
            key=profile_widget_key(prefix, "use_build_save_dc"),
            default=True,
        )
        save_dc_custom_key = f"{save_dc_key}-custom-value"
        if use_build_save_dc:
            save_dc = session_state.get(save_dc_custom_key, 13)
            if save_dc_key in session_state:
                previous_save_dc = session_state[save_dc_key]
                if previous_save_dc != resolved_math_defaults.save_dc:
                    save_dc = previous_save_dc
                    session_state[save_dc_custom_key] = previous_save_dc
            session_state[save_dc_key] = resolved_math_defaults.save_dc
            save_row[2].number_input(
                "Save DC value",
                min_value=1,
                value=resolved_math_defaults.save_dc,
                step=1,
                key=save_dc_key,
                disabled=True,
                label_visibility="collapsed",
            )
        elif save_dc_custom_key in session_state:
            session_state[save_dc_key] = session_state[save_dc_custom_key]
            save_dc = save_row[2].number_input(
                "Save DC value",
                min_value=1,
                step=1,
                key=save_dc_key,
                label_visibility="collapsed",
            )
        elif save_dc_key in session_state:
            save_dc = save_row[2].number_input(
                "Save DC value",
                min_value=1,
                step=1,
                key=save_dc_key,
                label_visibility="collapsed",
            )
        else:
            save_dc = save_row[2].number_input(
                "Save DC value",
                min_value=1,
                value=13,
                step=1,
                key=save_dc_key,
                label_visibility="collapsed",
            )
        effective_save_dc = (
            resolved_math_defaults.save_dc if use_build_save_dc else int(save_dc)
        )
        _row_text(save_row[3], f"Effective: {effective_save_dc}")
        _field_error(errors_by_key, profile_widget_key(prefix, "save_dc"))
    else:
        attack_bonus = None
        save_dc = None

    damage_key = profile_widget_key(prefix, "damage_formula")
    damage_row = st.columns(5)
    _row_text(damage_row[0], "**Damage**")
    if damage_key in session_state:
        damage_dice = damage_row[1].text_input(
            "Damage Formula",
            placeholder=DAMAGE_FORMULA_PLACEHOLDER,
            help=DAMAGE_FORMULA_HELP,
            key=damage_key,
            label_visibility="collapsed",
        )
    else:
        damage_dice = damage_row[1].text_input(
            "Damage Formula",
            value="1d8",
            placeholder=DAMAGE_FORMULA_PLACEHOLDER,
            help=DAMAGE_FORMULA_HELP,
            key=damage_key,
            label_visibility="collapsed",
        )
    use_build_damage_modifier = _safe_checkbox(
        damage_row[2],
        "Add Build Modifier",
        key=profile_widget_key(prefix, "use_build_damage_modifier"),
        default=True,
    )
    damage_modifier_key = (
        f"{profile_widget_key(prefix, 'use_build_damage_modifier')}-value"
    )
    damage_modifier_value = (
        resolved_math_defaults.damage_modifier if use_build_damage_modifier else 0
    )
    damage_row[3].number_input(
        "Damage modifier value",
        value=damage_modifier_value,
        step=1,
        key=damage_modifier_key,
        disabled=use_build_damage_modifier,
        label_visibility="collapsed",
    )
    preview_profile = AttackProfile(
        name=attack_name or default_name,
        attack_bonus=None if attack_bonus is None else int(attack_bonus),
        damage_dice=damage_dice,
        attacks_per_round=1,
        resolution_type=resolution_type,
        save_dc=None if save_dc is None else int(save_dc),
        use_build_attack_bonus=use_build_attack_bonus,
        use_build_save_dc=use_build_save_dc,
        use_build_damage_modifier=use_build_damage_modifier,
    )
    resolved_values = resolve_attack_profile_values(
        preview_profile, resolved_math_defaults
    )
    _row_text(damage_row[4], f"Effective: {resolved_values.damage_formula}")
    if not _field_error(errors_by_key, profile_widget_key(prefix, "damage_formula")):
        current_damage_errors = _validate_profile_fields(
            AttackProfile(
                name=default_name,
                attack_bonus=0,
                damage_dice=damage_dice,
                attacks_per_round=1,
                use_build_damage_modifier=use_build_damage_modifier,
            ),
            prefix=prefix,
        )
        for error in current_damage_errors:
            if error.key == profile_widget_key(prefix, "damage_formula"):
                _render_error(error.message)
                break

    row_two = st.columns(3)
    attacks_per_round = row_two[0].number_input(
        "Attacks per round",
        min_value=1,
        value=1,
        step=1,
        key=profile_widget_key(prefix, "attacks_per_round"),
    )
    _field_error(errors_by_key, profile_widget_key(prefix, "attacks_per_round"))
    affected_targets = row_two[1].number_input(
        "Target Resolutions",
        min_value=1,
        value=1,
        step=1,
        key=profile_widget_key(prefix, "affected_targets"),
    )
    _field_error(errors_by_key, profile_widget_key(prefix, "affected_targets"))
    if resolution_type is ResolutionType.ATTACK_ROLL:
        attack_roll_mode_label = row_two[2].selectbox(
            "Attack roll mode",
            options=[mode.value.title() for mode in AttackRollMode],
            index=0,
            key=profile_widget_key(prefix, "attack_roll_mode"),
        )
        attack_roll_mode = AttackRollMode(attack_roll_mode_label.lower())
        successful_save_damage = SuccessfulSaveDamage.NO_DAMAGE
    elif resolution_type is ResolutionType.SAVING_THROW:
        successful_save_damage_label = row_two[2].selectbox(
            "Successful Save Damage",
            options=["No damage", "Half damage"],
            index=0,
            key=profile_widget_key(prefix, "successful_save_damage"),
        )
        attack_roll_mode = AttackRollMode.NORMAL
        successful_save_damage = (
            SuccessfulSaveDamage.HALF_DAMAGE
            if successful_save_damage_label == "Half damage"
            else SuccessfulSaveDamage.NO_DAMAGE
        )
    else:
        attack_roll_mode = AttackRollMode.NORMAL
        successful_save_damage = SuccessfulSaveDamage.NO_DAMAGE
    active_rounds = st.text_input(
        "Active Rounds",
        value="",
        help="Leave blank for every round. Examples: 1-5 or 1, 3-5, 8.",
        key=profile_widget_key(prefix, "active_rounds"),
    )
    _field_error(errors_by_key, profile_widget_key(prefix, "active_rounds"))

    state = getattr(st, "session_state", {})
    trigger_type_label = state.get(profile_widget_key(prefix, "trigger_type"), "Always")
    trigger_type = {
        "Another attack succeeds": TriggerType.AFTER_SUCCESS,
        "Another attack fails": TriggerType.AFTER_FAILURE,
        "Another attack critically hits": TriggerType.AFTER_CRITICAL,
        "Sometimes": TriggerType.SOMETIMES,
    }.get(trigger_type_label, TriggerType.ALWAYS)
    trigger_source_attack_id = state.get(
        profile_widget_key(prefix, "trigger_source_attack_id")
    )
    trigger_frequency = {
        "Once per round": TriggerFrequency.ONCE_PER_ROUND,
        "Once per combat": TriggerFrequency.ONCE_PER_COMBAT,
    }.get(
        str(state.get(profile_widget_key(prefix, "trigger_frequency"))),
        TriggerFrequency.PER_SUCCESS,
    )
    trigger_chance_text = state.get(
        profile_widget_key(prefix, "trigger_chance_percent"), "100"
    )
    trigger_chance_percent = (
        int(trigger_chance_text) if str(trigger_chance_text).isdigit() else None
    )
    with _trigger_settings_expander(prefix, build_prefix, domain_attack_id):
        trigger_type_label = st.selectbox(
            "When",
            options=[
                "Always",
                "Another attack succeeds",
                "Another attack fails",
                "Another attack critically hits",
                "Sometimes",
            ],
            index=0,
            key=profile_widget_key(prefix, "trigger_type"),
            help=(
                "Succeeds means an attack roll hits or a target fails "
                "its saving throw. Fails means an attack roll misses "
                "or a target succeeds on its saving throw. "
                "Critically hits only applies to attack-roll attacks."
            ),
        )
        _field_error(errors_by_key, profile_widget_key(prefix, "trigger_type"))
        trigger_type = {
            "Another attack succeeds": TriggerType.AFTER_SUCCESS,
            "Another attack fails": TriggerType.AFTER_FAILURE,
            "Another attack critically hits": TriggerType.AFTER_CRITICAL,
            "Sometimes": TriggerType.SOMETIMES,
        }.get(trigger_type_label, TriggerType.ALWAYS)
        trigger_source_attack_id = None
        trigger_frequency = TriggerFrequency.PER_SUCCESS
        trigger_chance_percent = None
        if trigger_type is TriggerType.SOMETIMES:
            chance_text = st.text_input(
                "Percentage Chance",
                value="100",
                key=profile_widget_key(prefix, "trigger_chance_percent"),
                help="Sometimes [Percentage Chance] % per round",
            )
            if str(chance_text).isdigit():
                trigger_chance_percent = int(chance_text)
            _field_error(
                errors_by_key, profile_widget_key(prefix, "trigger_chance_percent")
            )
            st.caption("Sometimes [Percentage Chance] % per round")
        elif trigger_type is not TriggerType.ALWAYS:
            source_options = _trigger_source_options(build_prefix, domain_attack_id)
            option_ids = [attack_id for attack_id, _ in source_options]
            source_key = profile_widget_key(prefix, "trigger_source_attack_id")
            stored_source = getattr(st, "session_state", {}).get(source_key)
            options_with_placeholder = [None, *option_ids]
            selected_index = (
                options_with_placeholder.index(stored_source)
                if stored_source in option_ids
                else 0
            )
            selected_source = st.selectbox(
                "What",
                options=options_with_placeholder,
                format_func=lambda attack_id: (
                    "Select an attack..."
                    if attack_id is None
                    else dict(source_options).get(attack_id, attack_id)
                ),
                index=selected_index,
                key=source_key,
            )
            trigger_source_attack_id = (
                selected_source if selected_source in option_ids else stored_source
            )
            if not option_ids:
                getattr(st, "warning", lambda *args, **kwargs: None)(
                    NO_ELIGIBLE_TRIGGER_SOURCE_MESSAGE
                )
            _field_error(errors_by_key, source_key)
            source_resolution = ResolutionType.ATTACK_ROLL
            if trigger_source_attack_id in option_ids:
                source_resolution_label = getattr(st, "session_state", {}).get(
                    profile_widget_key(
                        attack_widget_prefix(build_prefix, trigger_source_attack_id),
                        "resolution_type",
                    ),
                    "Attack Roll",
                )
                source_resolution = {
                    "Attack Roll": ResolutionType.ATTACK_ROLL,
                    "Saving Throw": ResolutionType.SAVING_THROW,
                    "Automatic Damage": ResolutionType.AUTOMATIC_DAMAGE,
                }.get(source_resolution_label, ResolutionType.ATTACK_ROLL)
            frequency_labels = _trigger_frequency_labels(source_resolution)
            if trigger_source_attack_id in option_ids:
                frequency_label = st.radio(
                    "Frequency",
                    options=list(frequency_labels),
                    key=profile_widget_key(prefix, "trigger_frequency"),
                    help=(
                        "Every successful resolution triggers once per "
                        "qualifying target. "
                        "Once per round caps the trigger to one use in each round. "
                        "Once per combat caps it to one use in the "
                        "simulated combat."
                    ),
                )
                trigger_frequency = {
                    frequency_labels[1]: TriggerFrequency.ONCE_PER_ROUND,
                    frequency_labels[2]: TriggerFrequency.ONCE_PER_COMBAT,
                }.get(frequency_label, TriggerFrequency.PER_SUCCESS)
    resources = _managed_resources_from_state()
    resource_costs: tuple[ResourceCost, ...] = ()
    if resources:
        resource_expander = getattr(st, "expander", None)
        with (
            resource_expander(
                _resource_summary_from_state(build_prefix, domain_attack_id),
                expanded=False,
                key=f"{prefix}-resource-expanded",
            )
            if resource_expander is not None
            else nullcontext()
        ):
            checkbox = getattr(st, "checkbox", lambda *args, **kwargs: False)
            use_resource = checkbox(
                "Requires managed resource",
                key=profile_widget_key(prefix, "resource_enabled"),
            )
            if use_resource:
                options = [resource.resource_id for resource in resources]
                resource_labels = {
                    resource.resource_id: resource.name for resource in resources
                }
                selected = st.selectbox(
                    "Resource",
                    options=["", *options],
                    format_func=lambda resource_id: (
                        "Select a resource..."
                        if not resource_id
                        else resource_labels.get(resource_id, resource_id)
                    ),
                    key=profile_widget_key(prefix, "resource_id"),
                )
                _field_error(errors_by_key, profile_widget_key(prefix, "resource_id"))
                amount = st.number_input(
                    "Amount consumed",
                    min_value=1,
                    value=1,
                    step=1,
                    key=profile_widget_key(prefix, "resource_amount"),
                )
                _field_error(
                    errors_by_key, profile_widget_key(prefix, "resource_amount")
                )
                resource_costs = (ResourceCost(str(selected), int(amount)),)
    features = _feature_inputs(prefix, resolution_type, int(affected_targets))
    return AttackProfile(
        name=attack_name,
        attack_bonus=None if attack_bonus is None else int(attack_bonus),
        damage_dice=damage_dice,
        attacks_per_round=int(attacks_per_round),
        affected_targets=int(affected_targets),
        attack_roll_mode=attack_roll_mode,
        active_rounds=active_rounds,
        resolution_type=resolution_type,
        save_dc=None if save_dc is None else int(save_dc),
        successful_save_damage=successful_save_damage,
        features=features,
        attack_id=domain_attack_id,
        trigger_type=trigger_type,
        trigger_source_attack_id=trigger_source_attack_id,
        trigger_frequency=trigger_frequency,
        trigger_chance_percent=trigger_chance_percent,
        resource_costs=resource_costs,
        use_build_attack_bonus=use_build_attack_bonus,
        use_build_save_dc=use_build_save_dc,
        use_build_damage_modifier=use_build_damage_modifier,
    )


def _profile_definitions(
    build_prefix: str, additional_attack_count: int
) -> tuple[tuple[str, str, str], ...]:
    """Return stable attack IDs, headings, and default names for visible profiles."""
    import streamlit as st

    state = getattr(st, "session_state", {})
    key = build_attack_ids_key(build_prefix)
    if additional_attack_count and (
        key not in state or len(state.get(key, [])) != additional_attack_count + 1
    ):
        attack_ids = [
            profile_prefix(build_prefix, index)
            for index in range(additional_attack_count + 1)
        ]
        state[key] = attack_ids
    else:
        attack_ids = _attack_ids_from_state(state, build_prefix)
    if len(attack_ids) > MAX_ATTACKS_PER_BUILD:
        msg = "Attack count must be no more than 11."
        raise ValueError(msg)
    return tuple(
        (attack_id, _attack_display_heading(index), _default_attack_name(index))
        for index, attack_id in enumerate(attack_ids)
    )


def _format_signed_modifier(value: int) -> str:
    """Format a build-level modifier with an explicit sign."""
    return f"{value:+d}"


def _build_math_number_input(
    container: Any,
    *,
    label: str,
    key: str,
    default: int,
    help_text: str,
) -> int:
    """Render one session-state-safe integer build-math input."""
    import streamlit as st

    kwargs: dict[str, Any] = {
        "label": label,
        "key": key,
        "step": 1,
        "format": "%d",
        "help": help_text,
    }
    if key not in getattr(st, "session_state", {}):
        kwargs["value"] = default
    value = container.number_input(**kwargs)
    if type(value) is not int:
        msg = f"{label} must be an integer."
        raise ValueError(msg)
    return value


def _build_math_caption(body: str) -> None:
    """Render a compact explanatory caption with fake-Streamlit compatibility."""
    import streamlit as st

    caption = getattr(st, "caption", st.markdown)
    caption(body)


def _build_math_metric(container: Any, label: str, value: str) -> None:
    """Render one calculated build-math value."""
    metric = getattr(container, "metric", None)
    if metric is not None:
        metric(label, value)
        return
    import streamlit as st

    st.markdown(f"**{label}:** {value}")


def _build_math_inputs(build_prefix: str) -> BuildMathDefaults:
    """Render visible build-level math defaults for one build."""
    import streamlit as st

    default_values = BuildMathDefaults()
    with _render_section_container():
        st.markdown("##### Build Setup")
        _build_math_caption(
            "Build defaults are saved with this build. Attacks can use these "
            "Build Setup values or keep their own manual values."
        )
        first_row = st.columns(2)
        ability_modifier = _build_math_number_input(
            first_row[0],
            label="Ability modifier",
            key=build_math_state_key(build_prefix, "ability_modifier"),
            default=default_values.ability_modifier,
            help_text="Base ability modifier used by the calculated build defaults.",
        )
        proficiency_bonus = _build_math_number_input(
            first_row[1],
            label="Proficiency bonus",
            key=build_math_state_key(build_prefix, "proficiency_bonus"),
            default=default_values.proficiency_bonus,
            help_text=(
                "Proficiency bonus used by the calculated Attack Bonus and Save DC."
            ),
        )

        second_row = st.columns(3)
        attack_bonus_adjustment = _build_math_number_input(
            second_row[0],
            label="Other attack bonus",
            key=build_math_state_key(build_prefix, "attack_bonus_adjustment"),
            default=default_values.attack_bonus_adjustment,
            help_text=(
                "Additional bonus included only in the calculated build Attack Bonus."
            ),
        )
        damage_bonus_adjustment = _build_math_number_input(
            second_row[1],
            label="Other damage bonus",
            key=build_math_state_key(build_prefix, "damage_bonus_adjustment"),
            default=default_values.damage_bonus_adjustment,
            help_text=(
                "Additional bonus included only in the calculated build "
                "Damage Modifier."
            ),
        )
        save_dc_adjustment = _build_math_number_input(
            second_row[2],
            label="Other Save DC bonus",
            key=build_math_state_key(build_prefix, "save_dc_adjustment"),
            default=default_values.save_dc_adjustment,
            help_text="Additional bonus included only in the calculated build Save DC.",
        )

        defaults = BuildMathDefaults(
            ability_modifier=ability_modifier,
            proficiency_bonus=proficiency_bonus,
            attack_bonus_adjustment=attack_bonus_adjustment,
            damage_bonus_adjustment=damage_bonus_adjustment,
            save_dc_adjustment=save_dc_adjustment,
        )
        metric_row = st.columns(3)
        _build_math_metric(
            metric_row[0],
            "Attack bonus",
            _format_signed_modifier(defaults.attack_bonus),
        )
        _build_math_metric(
            metric_row[1],
            "Damage modifier",
            _format_signed_modifier(defaults.damage_modifier),
        )
        _build_math_metric(metric_row[2], "Save DC", str(defaults.save_dc))
        _build_math_caption(
            "Attack bonus = ability modifier + proficiency bonus + other attack "
            "bonus. Damage modifier = ability modifier + other damage bonus. "
            "Save DC = 8 + ability modifier + proficiency bonus + other Save DC bonus."
        )
        return defaults


def _build_config_from_profiles(
    name: str,
    profiles: tuple[AttackProfile, ...],
    math_defaults: BuildMathDefaults | None = None,
) -> BuildConfig:
    """Create a build config with every displayed profile attached."""
    primary = profiles[0]
    resolved_defaults = BuildMathDefaults() if math_defaults is None else math_defaults
    return BuildConfig(
        name=name,
        attack_bonus=primary.attack_bonus or 0,
        damage_dice=primary.damage_dice,
        attacks_per_round=primary.attacks_per_round,
        attack_roll_mode=primary.attack_roll_mode,
        attack_profiles=profiles,
        math_defaults=resolved_defaults,
    )


def _build_inputs(
    prefix: str, default_name: str, errors_by_key: dict[str, str] | None = None
) -> BuildConfig:
    """Render and collect one build's input controls."""
    import streamlit as st

    errors_by_key = errors_by_key or {}
    with _render_section_container():
        st.markdown(f"#### {default_name}")
        name = st.text_input(
            "Build name", value=default_name, key=f"{prefix}-build-name"
        )
        _field_error(errors_by_key, f"{prefix}-build-name")
        math_defaults = _build_math_inputs(prefix)
        attack_ids = _attack_ids_from_state(getattr(st, "session_state", {}), prefix)
        if st.button(
            "Add Attack",
            key=f"{prefix}-add-attack",
            disabled=len(attack_ids) >= MAX_ATTACKS_PER_BUILD,
            help=(
                "Maximum of 11 attacks reached."
                if len(attack_ids) >= MAX_ATTACKS_PER_BUILD
                else None
            ),
        ):
            new_id = _new_attack_id(prefix, len(attack_ids))
            getattr(st, "session_state", {})[build_attack_ids_key(prefix)] = [
                *attack_ids,
                new_id,
            ]
            new_widget_prefix = attack_widget_prefix(prefix, new_id)
            existing_names = [
                getattr(st, "session_state", {}).get(
                    profile_widget_key(_state_widget_prefix(prefix, attack_id), "name"),
                    "",
                )
                for attack_id in attack_ids
            ]
            getattr(st, "session_state", {})[
                profile_widget_key(new_widget_prefix, "name")
            ] = next_default_attack_name(existing_names)
            getattr(st, "rerun", lambda: None)()

        profiles = []
        for profile_index, (
            attack_id,
            _heading,
            default_attack_name,
        ) in enumerate(_profile_definitions(prefix, 0)):
            with _render_section_container():
                current_name = (
                    str(
                        getattr(st, "session_state", {}).get(
                            profile_widget_key(
                                _state_widget_prefix(prefix, attack_id), "name"
                            ),
                            default_attack_name,
                        )
                    ).strip()
                    or "Unnamed Attack"
                )
                ids = _attack_ids_from_state(getattr(st, "session_state", {}), prefix)
                container = getattr(st, "container", None)
                toolbar = (
                    container(
                        key=f"{prefix}-{attack_id}-toolbar",
                        border=True,
                        width="content",
                        horizontal=True,
                        vertical_alignment="center",
                        gap="xsmall",
                    )
                    if container is not None
                    else st
                )

                def toolbar_button(*args, _toolbar=toolbar, **kwargs):
                    button = getattr(_toolbar, "button", lambda *args, **kwargs: False)
                    return button(
                        *args,
                        type="tertiary",
                        width="content",
                        **kwargs,
                    )

                at_max = len(ids) >= MAX_ATTACKS_PER_BUILD
                if toolbar_button(
                    ":material/content_copy:",
                    key=f"{prefix}-{attack_id}-duplicate",
                    disabled=at_max,
                    help=(
                        "Maximum of 11 attacks reached."
                        if at_max
                        else f"Duplicate {current_name}."
                    ),
                ):
                    state = getattr(st, "session_state", {})
                    new_id = _new_attack_id(prefix, profile_index)
                    new_widget_prefix = attack_widget_prefix(prefix, new_id)
                    written_keys: list[str] = []
                    try:
                        copied_state = _duplicate_attack_state(
                            state,
                            _state_widget_prefix(prefix, attack_id),
                            new_widget_prefix,
                            source_attack_id=attack_id,
                            dest_attack_id=new_id,
                        )
                        for key, value in copied_state.items():
                            state[key] = value
                            written_keys.append(key)
                        state[build_attack_ids_key(prefix)] = (
                            ids[: profile_index + 1]
                            + [new_id]
                            + ids[profile_index + 1 :]
                        )
                    except Exception as error:  # pragma: no cover - defensive UI guard
                        for key in written_keys:
                            state.pop(key, None)
                        getattr(st, "error", lambda *args, **kwargs: None)(
                            f"Could not duplicate {current_name}: {error}"
                        )
                    else:
                        getattr(st, "rerun", lambda: None)()
                if toolbar_button(
                    ":material/arrow_upward:",
                    key=f"{prefix}-{attack_id}-up",
                    disabled=profile_index == 0,
                    help=(
                        "This attack is already first."
                        if profile_index == 0
                        else f"Move {current_name} up."
                    ),
                ):
                    ids[profile_index - 1], ids[profile_index] = (
                        ids[profile_index],
                        ids[profile_index - 1],
                    )
                    getattr(st, "session_state", {})[build_attack_ids_key(prefix)] = ids
                    getattr(st, "rerun", lambda: None)()
                if toolbar_button(
                    ":material/arrow_downward:",
                    key=f"{prefix}-{attack_id}-down",
                    disabled=profile_index == len(ids) - 1,
                    help=(
                        "This attack is already last."
                        if profile_index == len(ids) - 1
                        else f"Move {current_name} down."
                    ),
                ):
                    ids[profile_index + 1], ids[profile_index] = (
                        ids[profile_index],
                        ids[profile_index + 1],
                    )
                    getattr(st, "session_state", {})[build_attack_ids_key(prefix)] = ids
                    getattr(st, "rerun", lambda: None)()
                dependents = _dependent_attack_names(
                    getattr(st, "session_state", {}), prefix, attack_id
                )
                delete_clicked = toolbar_button(
                    ":material/delete:",
                    key=f"{prefix}-{attack_id}-delete",
                    disabled=len(ids) == 1,
                    help=(
                        "A build must keep at least one attack."
                        if len(ids) == 1
                        else f"Delete {current_name}. Requires confirmation."
                    ),
                )
                state = getattr(st, "session_state", {})
                if delete_clicked:
                    state[ATTACK_DELETE_CONFIRMATION_KEY] = _attack_confirmation_id(
                        prefix, attack_id
                    )
                if state.get(ATTACK_DELETE_CONFIRMATION_KEY) == _attack_confirmation_id(
                    prefix, attack_id
                ):
                    if dependents:
                        getattr(st, "warning", lambda *args, **kwargs: None)(
                            f"Delete {current_name}? Triggers reset on: "
                            + ", ".join(dependents)
                        )
                    else:
                        getattr(st, "warning", lambda *args, **kwargs: None)(
                            f"Delete {current_name}? No dependent attacks will reset."
                        )
                    confirm_cols = st.columns([1, 1, 4])
                    confirm_button = getattr(confirm_cols[0], "button", st.button)
                    cancel_button = getattr(confirm_cols[1], "button", st.button)
                    if confirm_button(
                        "Confirm Delete", key=f"{prefix}-{attack_id}-confirm-delete"
                    ):
                        _reset_triggers_referencing_attack(state, prefix, attack_id)
                        state[build_attack_ids_key(prefix)] = [
                            current_id for current_id in ids if current_id != attack_id
                        ]
                        _delete_attack_state(state, prefix, attack_id)
                        state.pop(ATTACK_DELETE_CONFIRMATION_KEY, None)
                        getattr(st, "rerun", lambda: None)()
                    if cancel_button(
                        "Cancel", key=f"{prefix}-{attack_id}-cancel-delete"
                    ):
                        state.pop(ATTACK_DELETE_CONFIRMATION_KEY, None)
                        getattr(st, "rerun", lambda: None)()
                profiles.append(
                    _attack_profile_inputs(
                        _state_widget_prefix(prefix, attack_id),
                        default_attack_name,
                        errors_by_key,
                        attack_id=attack_id,
                        math_defaults=math_defaults,
                    )
                )

    return _build_config_from_profiles(
        name=name,
        profiles=tuple(profiles),
        math_defaults=math_defaults,
    )


def _render_simulation_settings() -> tuple[int, int]:
    import streamlit as st

    def render_controls(container) -> tuple[int, int]:
        simulations_value = container.number_input(
            "Number of simulations",
            min_value=1,
            value=10_000,
            step=1,
            key=SCENARIO_WIDGET_KEYS["simulations"],
        )
        seed_value = container.number_input(
            "Random seed",
            step=1,
            key=SCENARIO_WIDGET_KEYS["seed"],
        )
        return int(simulations_value), int(seed_value)

    popover = getattr(st, "popover", None)
    if popover is not None:
        with popover(
            "⚙️",
            help="Simulation settings",
            width="content",
            use_container_width=False,
            key="simulation-settings",
        ) as settings_area:
            return render_controls(settings_area)
    expander = getattr(st, "expander", None)
    if expander is not None:
        with expander("⚙️ Simulation settings", expanded=False) as settings_area:
            return render_controls(settings_area or st)
    return render_controls(st)


def _render_configuration_toolbar() -> tuple[int, int]:
    import streamlit as st

    st.markdown(CONFIGURATION_TOOLBAR_CSS, unsafe_allow_html=True)
    container = getattr(st, "container", None)
    if container is None:
        simulations, seed = _render_simulation_settings()
        _render_share_configuration_button()
        return simulations, seed

    toolbar = container(
        key="configuration-toolbar",
        width="content",
        horizontal=True,
        horizontal_alignment="left",
        vertical_alignment="center",
        gap=None,
    )
    with toolbar if hasattr(toolbar, "__enter__") else nullcontext():
        simulations, seed = _render_simulation_settings()
        _render_share_configuration_button()
    return simulations, seed
