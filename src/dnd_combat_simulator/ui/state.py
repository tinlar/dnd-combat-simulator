"""Focused Streamlit UI helpers."""

from __future__ import annotations

import logging
from secrets import randbelow
from uuid import uuid4

from dnd_combat_simulator.combat import (
    AttackFeature,
    AttackRollMode,
    ResolutionType,
    SuccessfulSaveDamage,
    available_features,
)
from dnd_combat_simulator.sharing import (
    SharedBuildConfiguration,
    SharedConfiguration,
    migrate_shared_build_attack_ids,
)
from dnd_combat_simulator.simulation import (
    AttackProfile,
    BuildConfig,
    ManagedResource,
    ResourceCost,
    TriggerFrequency,
    TriggerType,
)
from dnd_combat_simulator.ui.constants import (
    ATTACK_DELETE_CONFIRMATION_KEY,
    COMPARE_WIDGET_KEY,
    FEATURE_ORDER,
    MANAGED_RESOURCE_COUNT_KEY,
    MANAGED_RESOURCE_IDS_KEY,
    SCENARIO_WIDGET_KEYS,
)
from dnd_combat_simulator.ui.widget_keys import (
    _state_widget_prefix,
    attack_widget_prefix,
    build_attack_ids_key,
    feature_widget_key,
    managed_resource_widget_key,
    profile_prefix,
    profile_widget_key,
    trigger_expanded_state_key,
)


def _new_attack_id(build_prefix: str, position: int = 0) -> str:
    del build_prefix, position
    return f"attack-{uuid4().hex}"


ATTACK_WIDGET_STATE_FIELDS = (
    "name",
    "resolution_type",
    "attack_bonus",
    "save_dc",
    "successful_save_damage",
    "attack_roll_mode",
    "damage_formula",
    "attacks_per_round",
    "affected_targets",
    "active_rounds",
    "trigger_type",
    "trigger_source_attack_id",
    "trigger_frequency",
    "trigger_chance_percent",
    "resource_enabled",
    "resource_id",
    "resource_amount",
)


def _copied_attack_widget_state(
    state, source_prefix: str, dest_prefix: str
) -> dict[str, object]:
    copied: dict[str, object] = {}
    for field in ATTACK_WIDGET_STATE_FIELDS:
        source_key = profile_widget_key(source_prefix, field)
        if source_key in state:
            copied[profile_widget_key(dest_prefix, field)] = state[source_key]
    for feature in FEATURE_ORDER:
        source_key = feature_widget_key(source_prefix, feature)
        if source_key in state:
            copied[feature_widget_key(dest_prefix, feature)] = state[source_key]
    expander_key = trigger_expanded_state_key(source_prefix)
    if expander_key in state:
        copied[trigger_expanded_state_key(dest_prefix)] = state[expander_key]
    for suffix in ("features-expanded", "resource-expanded"):
        source_key = f"{source_prefix}-{suffix}"
        if source_key in state:
            copied[f"{dest_prefix}-{suffix}"] = state[source_key]
    return copied


def _copy_attack_widget_state(state, source_prefix: str, dest_prefix: str) -> None:
    state.update(_copied_attack_widget_state(state, source_prefix, dest_prefix))


def _looks_like_widget_prefix(build_prefix: str, attack_id: str) -> bool:
    return (
        attack_id.startswith(f"{build_prefix}-primary")
        or attack_id.startswith(f"{build_prefix}-additional-")
        or attack_id.startswith(f"{build_prefix}-attack-")
    )


def _attack_ids_from_state(state, build_prefix: str) -> list[str]:
    key = build_attack_ids_key(build_prefix)
    if not state and key not in state:
        count = int(state.get(f"{build_prefix}-additional-attack-count", 0))
        return [profile_prefix(build_prefix, index) for index in range(count + 1)]
    existing = [str(attack_id) for attack_id in state.get(key, [])]
    if existing and not any(
        _looks_like_widget_prefix(build_prefix, attack_id) for attack_id in existing
    ):
        return existing

    count = int(state.get(f"{build_prefix}-additional-attack-count", 0))
    legacy_ids = existing or [
        profile_prefix(build_prefix, index) for index in range(count + 1)
    ]
    migration_key = f"{key}-legacy-migrated"
    stored_mapping = (
        state.get(migration_key, {})
        if isinstance(state.get(migration_key), dict)
        else {}
    )
    legacy_to_stable: dict[str, str] = {}
    stable_ids: list[str] = []
    for _index, legacy_id in enumerate(legacy_ids):
        stable_id = str(stored_mapping.get(legacy_id) or f"attack-{uuid4().hex}")
        legacy_to_stable[legacy_id] = stable_id
        stable_ids.append(stable_id)
        widget_prefix = attack_widget_prefix(build_prefix, stable_id)
        _copy_attack_widget_state(state, legacy_id, widget_prefix)
        name_key = profile_widget_key(widget_prefix, "name")
        if name_key not in state:
            state[name_key] = next_default_attack_name(
                state.get(
                    profile_widget_key(attack_widget_prefix(build_prefix, aid), "name"),
                    "",
                )
                for aid in stable_ids[:-1]
            )
    for _legacy_id, stable_id in legacy_to_stable.items():
        widget_prefix = attack_widget_prefix(build_prefix, stable_id)
        source_key = profile_widget_key(widget_prefix, "trigger_source_attack_id")
        source = state.get(source_key)
        if source in legacy_to_stable:
            state[source_key] = legacy_to_stable[source]
    state[key] = stable_ids
    state[migration_key] = legacy_to_stable
    return stable_ids


def _default_attack_name(index: int) -> str:
    return f"Attack {index + 1}"


def next_default_attack_name(existing_names) -> str:
    existing = {
        str(name).strip().casefold() for name in existing_names if str(name).strip()
    }
    index = 0
    while True:
        candidate = _default_attack_name(index)
        if candidate.casefold() not in existing:
            return candidate
        index += 1


def _attack_display_heading(index: int) -> str:
    return f"Attack {index + 1}"


def _attack_confirmation_id(build_prefix: str, attack_id: str) -> str:
    return f"{build_prefix}:{attack_id}"


def _duplicate_attack_state(
    state,
    source_widget_prefix: str,
    dest_widget_prefix: str,
    *,
    source_attack_id: str,
    dest_attack_id: str,
) -> dict[str, object]:
    copied = _copied_attack_widget_state(
        state, source_widget_prefix, dest_widget_prefix
    )
    copied[profile_widget_key(dest_widget_prefix, "name")] = (
        str(
            state.get(profile_widget_key(source_widget_prefix, "name"), "Attack")
        ).strip()
        + " copy"
    )
    trigger_source_key = profile_widget_key(
        dest_widget_prefix, "trigger_source_attack_id"
    )
    if copied.get(trigger_source_key) in {source_attack_id, dest_attack_id}:
        copied[profile_widget_key(dest_widget_prefix, "trigger_type")] = "Always"
        copied[trigger_source_key] = None
        copied[profile_widget_key(dest_widget_prefix, "trigger_frequency")] = (
            "Every successful resolution"
        )
    return copied


def _delete_attack_state(state, build_prefix: str, attack_id: str) -> None:
    widget_prefix = _state_widget_prefix(build_prefix, attack_id)
    profile_prefix_text = f"profile-{widget_prefix}-"
    transient_prefix = f"{widget_prefix}-"
    exact_keys = {
        trigger_expanded_state_key(widget_prefix),
        f"{widget_prefix}-features-expanded",
        f"{widget_prefix}-resource-expanded",
        f"{widget_prefix}-toolbar",
    }
    for key in list(state):
        key_text = str(key)
        if (
            key_text.startswith(profile_prefix_text)
            or key_text.startswith(transient_prefix)
            or key_text in exact_keys
        ):
            del state[key]
    if state.get(ATTACK_DELETE_CONFIRMATION_KEY) == _attack_confirmation_id(
        build_prefix, attack_id
    ):
        state.pop(ATTACK_DELETE_CONFIRMATION_KEY, None)


def _dependent_attack_names(state, build_prefix: str, attack_id: str) -> list[str]:
    names = []
    for index, current_id in enumerate(_attack_ids_from_state(state, build_prefix)):
        if current_id == attack_id:
            continue
        widget_prefix = attack_widget_prefix(build_prefix, current_id)
        source_key = profile_widget_key(widget_prefix, "trigger_source_attack_id")
        if state.get(source_key) == attack_id:
            default_name = _default_attack_name(index)
            name_key = profile_widget_key(widget_prefix, "name")
            names.append(
                str(state.get(name_key, default_name)).strip()
                or _attack_display_heading(index)
            )
    return names


def _reset_triggers_referencing_attack(
    state, build_prefix: str, attack_id: str
) -> None:
    for current_id in _attack_ids_from_state(state, build_prefix):
        widget_prefix = attack_widget_prefix(build_prefix, current_id)
        source_key = profile_widget_key(widget_prefix, "trigger_source_attack_id")
        if state.get(source_key) == attack_id:
            state[profile_widget_key(widget_prefix, "trigger_type")] = "Always"
            state[source_key] = None
            frequency_key = profile_widget_key(widget_prefix, "trigger_frequency")
            state[frequency_key] = "Every successful resolution"


def trigger_summary(profile: AttackProfile, profiles: tuple[AttackProfile, ...]) -> str:
    if profile.trigger_type is TriggerType.ALWAYS:
        return "Trigger: Always"
    if profile.trigger_type is TriggerType.SOMETIMES:
        chance = profile.trigger_chance_percent or 0
        return f"Trigger: {chance}% chance once per round"
    source_name = next(
        (p.name for p in profiles if p.attack_id == profile.trigger_source_attack_id),
        "missing attack",
    )
    outcome = {
        TriggerType.AFTER_SUCCESS: "succeeds",
        TriggerType.AFTER_FAILURE: "fails",
        TriggerType.AFTER_CRITICAL: "critically hits",
    }[profile.trigger_type]
    frequency = {
        TriggerFrequency.PER_SUCCESS: "every time",
        TriggerFrequency.ONCE_PER_ROUND: "once per round",
        TriggerFrequency.ONCE_PER_COMBAT: "once per combat",
        TriggerFrequency.ONCE_IF_ANY: "once per round",
    }.get(profile.trigger_frequency, "every time")
    return f"Trigger: After {source_name} {outcome}, {frequency}"


def resource_summary(
    profile: AttackProfile, resources: tuple[ManagedResource, ...]
) -> str:
    if not profile.resource_costs:
        return "Resource: None"
    names = {resource.resource_id: resource.name for resource in resources}
    cost = profile.resource_costs[0]
    name = names.get(cost.resource_id, f"Invalid resource ({cost.resource_id})")
    return f"Resource: {cost.amount} {name} per execution"


def format_features(features: frozenset[AttackFeature]) -> str:
    selected = [
        feature.value.replace("_", " ").title()
        for feature in FEATURE_ORDER
        if feature in features
    ]
    return ", ".join(selected) if selected else "None"


def features_summary(features: frozenset[AttackFeature]) -> str:
    return f"Features: {format_features(features)}"


logger = logging.getLogger(__name__)


def _generate_default_seed() -> int:
    """Return a random editable seed for a new Streamlit session."""
    return randbelow(2**31 - 1) + 1


def ensure_session_random_seed(session_state) -> int:
    """Generate the scenario seed once and preserve it for normal reruns."""
    seed_key = SCENARIO_WIDGET_KEYS["seed"]
    if seed_key not in session_state:
        session_state[seed_key] = _generate_default_seed()
    return int(session_state[seed_key])


def _new_resource_id(position: int = 0) -> str:
    del position
    return f"resource-{uuid4().hex}"


def _managed_resource_ids_from_state(state) -> list[str]:
    if MANAGED_RESOURCE_IDS_KEY in state:
        return [
            str(resource_id) for resource_id in state.get(MANAGED_RESOURCE_IDS_KEY, [])
        ]
    count = int(state.get(MANAGED_RESOURCE_COUNT_KEY, 0))
    ids: list[str] = []
    for index in range(count):
        legacy_id_key = managed_resource_widget_key(index, "id")
        resource_id = str(state.get(legacy_id_key, f"resource-{index + 1}"))
        ids.append(resource_id)
        for legacy_field, stable_field in (
            ("name", "name"),
            ("starting-value", "starting-value"),
        ):
            legacy_key = managed_resource_widget_key(index, legacy_field)
            stable_key = managed_resource_widget_key(resource_id, stable_field)
            if legacy_key in state and stable_key not in state:
                state[stable_key] = state[legacy_key]
    state[MANAGED_RESOURCE_IDS_KEY] = ids
    state[MANAGED_RESOURCE_COUNT_KEY] = len(ids)
    return ids


def _delete_managed_resource_state(resource_id: str) -> None:
    import streamlit as st

    state = getattr(st, "session_state", {})
    state[MANAGED_RESOURCE_IDS_KEY] = [
        current_id
        for current_id in _managed_resource_ids_from_state(state)
        if current_id != resource_id
    ]
    state[MANAGED_RESOURCE_COUNT_KEY] = len(state[MANAGED_RESOURCE_IDS_KEY])
    for key in list(state):
        if str(key).startswith(f"scenario-managed-resource-{resource_id}-"):
            del state[key]


def _managed_resources_from_state() -> tuple[ManagedResource, ...]:
    import streamlit as st

    state = getattr(st, "session_state", {})
    ids = _managed_resource_ids_from_state(state)
    return tuple(
        ManagedResource(
            resource_id=resource_id,
            name=str(
                state.get(
                    managed_resource_widget_key(resource_id, "name"),
                    f"Resource {index + 1}",
                )
            ),
            starting_value=int(
                state.get(managed_resource_widget_key(resource_id, "starting-value"), 0)
            ),
        )
        for index, resource_id in enumerate(ids)
    )


def _resource_usage_profile_keys(resource_id: str) -> list[str]:
    import streamlit as st

    state = getattr(st, "session_state", {})
    used_by: list[str] = []
    for build_prefix in ("first", "second"):
        for index, attack_id in enumerate(_attack_ids_from_state(state, build_prefix)):
            widget_prefix = _state_widget_prefix(build_prefix, attack_id)
            if (
                state.get(profile_widget_key(widget_prefix, "resource_enabled"), False)
                and state.get(profile_widget_key(widget_prefix, "resource_id"))
                == resource_id
            ):
                default_name = _default_attack_name(index)
                used_by.append(
                    str(
                        state.get(
                            profile_widget_key(widget_prefix, "name"), default_name
                        )
                    ).strip()
                    or _attack_display_heading(index)
                )
    return used_by


def _clear_resource_from_profiles(resource_id: str) -> None:
    import streamlit as st

    state = getattr(st, "session_state", {})
    for build_prefix in ("first", "second"):
        for attack_id in _attack_ids_from_state(state, build_prefix):
            widget_prefix = _state_widget_prefix(build_prefix, attack_id)
            if (
                state.get(profile_widget_key(widget_prefix, "resource_id"))
                == resource_id
            ):
                state[profile_widget_key(widget_prefix, "resource_enabled")] = False
                state[profile_widget_key(widget_prefix, "resource_id")] = ""


def _resolution_type_label(resolution_type: ResolutionType) -> str:
    return {
        ResolutionType.ATTACK_ROLL: "Attack Roll",
        ResolutionType.SAVING_THROW: "Saving Throw",
        ResolutionType.AUTOMATIC_DAMAGE: "Automatic Damage",
    }[resolution_type]


def _successful_save_damage_label(successful_save_damage: SuccessfulSaveDamage) -> str:
    return (
        "Half damage"
        if successful_save_damage is SuccessfulSaveDamage.HALF_DAMAGE
        else "No damage"
    )


def _hydrate_build_session_state(
    session_state, prefix: str, build: SharedBuildConfiguration
) -> None:
    session_state[f"{prefix}-build-name"] = build.name
    attack_ids = [
        profile.attack_id or _new_attack_id(prefix, index)
        for index, profile in enumerate(build.attack_profiles)
    ]
    session_state[build_attack_ids_key(prefix)] = attack_ids
    session_state[f"{prefix}-additional-attack-count"] = len(build.attack_profiles) - 1
    for index, profile in enumerate(build.attack_profiles):
        widget_prefix = attack_widget_prefix(prefix, attack_ids[index])
        legacy_prefix = profile_prefix(prefix, index)
        session_state[profile_widget_key(widget_prefix, "name")] = profile.name
        session_state[profile_widget_key(legacy_prefix, "name")] = profile.name
        session_state[profile_widget_key(widget_prefix, "resolution_type")] = (
            _resolution_type_label(profile.resolution_type)
        )
        session_state[profile_widget_key(widget_prefix, "attack_bonus")] = (
            profile.attack_bonus if profile.attack_bonus is not None else 5
        )
        session_state[profile_widget_key(widget_prefix, "save_dc")] = (
            profile.save_dc if profile.save_dc is not None else 13
        )
        session_state[profile_widget_key(widget_prefix, "successful_save_damage")] = (
            _successful_save_damage_label(profile.successful_save_damage)
        )
        session_state[profile_widget_key(widget_prefix, "attack_roll_mode")] = (
            profile.attack_roll_mode.value.title()
        )
        session_state[profile_widget_key(widget_prefix, "damage_formula")] = (
            profile.damage_formula
        )
        session_state[profile_widget_key(widget_prefix, "attacks_per_round")] = (
            profile.attacks_per_round
        )
        session_state[profile_widget_key(widget_prefix, "affected_targets")] = (
            profile.affected_targets
        )
        session_state[profile_widget_key(widget_prefix, "active_rounds")] = (
            profile.active_rounds
        )
        session_state[profile_widget_key(widget_prefix, "trigger_type")] = {
            TriggerType.AFTER_SUCCESS: "Another attack succeeds",
            TriggerType.AFTER_FAILURE: "Another attack fails",
            TriggerType.AFTER_CRITICAL: "Another attack critically hits",
            TriggerType.SOMETIMES: "Sometimes",
        }.get(profile.trigger_type, "Always")
        session_state[profile_widget_key(widget_prefix, "trigger_source_attack_id")] = (
            profile.trigger_source_attack_id
        )
        session_state[profile_widget_key(widget_prefix, "trigger_chance_percent")] = (
            ""
            if profile.trigger_chance_percent is None
            else str(profile.trigger_chance_percent)
        )
        session_state[profile_widget_key(widget_prefix, "trigger_frequency")] = {
            TriggerFrequency.ONCE_PER_ROUND: "Once per round",
            TriggerFrequency.ONCE_PER_COMBAT: "Once per combat",
            TriggerFrequency.ONCE_IF_ANY: "Once per round",
        }.get(profile.trigger_frequency, "Every successful resolution")
        if profile.resource_costs:
            session_state[profile_widget_key(widget_prefix, "resource_enabled")] = True
            session_state[profile_widget_key(widget_prefix, "resource_id")] = (
                profile.resource_costs[0].resource_id
            )
            session_state[profile_widget_key(widget_prefix, "resource_amount")] = (
                profile.resource_costs[0].amount
            )
        else:
            session_state[profile_widget_key(widget_prefix, "resource_enabled")] = False
        for feature in FEATURE_ORDER:
            session_state[feature_widget_key(widget_prefix, feature)] = (
                feature in profile.features
            )
        _copy_attack_widget_state(session_state, widget_prefix, legacy_prefix)


def hydrate_session_state_from_shared_configuration(
    session_state, configuration: SharedConfiguration
) -> None:
    """Populate Streamlit widget state from a fully validated shared config."""
    scenario = configuration.scenario
    session_state[SCENARIO_WIDGET_KEYS["target_armor_class"]] = (
        scenario.target_armor_class
    )
    session_state[SCENARIO_WIDGET_KEYS["enemy_save_bonus"]] = scenario.enemy_save_bonus
    session_state[SCENARIO_WIDGET_KEYS["rounds"]] = scenario.rounds
    session_state[SCENARIO_WIDGET_KEYS["simulations"]] = scenario.simulations
    session_state[SCENARIO_WIDGET_KEYS["seed"]] = scenario.seed
    session_state[COMPARE_WIDGET_KEY] = configuration.compare_enabled
    session_state[MANAGED_RESOURCE_IDS_KEY] = [
        resource.resource_id for resource in configuration.scenario.managed_resources
    ]
    session_state[MANAGED_RESOURCE_COUNT_KEY] = len(
        configuration.scenario.managed_resources
    )
    for resource in configuration.scenario.managed_resources:
        session_state[managed_resource_widget_key(resource.resource_id, "name")] = (
            resource.name
        )
        session_state[
            managed_resource_widget_key(resource.resource_id, "starting-value")
        ] = resource.starting_value
    _hydrate_build_session_state(
        session_state,
        "first",
        migrate_shared_build_attack_ids("first", configuration.build_a),
    )
    _hydrate_build_session_state(
        session_state,
        "second",
        migrate_shared_build_attack_ids("second", configuration.build_b),
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
    if len(attack_ids) > 11:
        msg = "Attack count must be no more than 11."
        raise ValueError(msg)
    return tuple(
        (attack_id, _attack_display_heading(index), _default_attack_name(index))
        for index, attack_id in enumerate(attack_ids)
    )


def _build_config_from_profiles(
    name: str,
    profiles: tuple[AttackProfile, ...],
) -> BuildConfig:
    """Create a build config with every displayed profile attached."""
    primary = profiles[0]
    return BuildConfig(
        name=name,
        attack_bonus=primary.attack_bonus or 0,
        damage_dice=primary.damage_dice,
        attacks_per_round=primary.attacks_per_round,
        attack_roll_mode=primary.attack_roll_mode,
        attack_profiles=profiles,
    )


def _build_from_state(prefix: str, default_build_name: str) -> BuildConfig:
    """Build a configuration from existing session-state values or widget defaults."""
    import streamlit as st

    session_state = getattr(st, "session_state", {})
    if f"{prefix}-build-name" not in session_state:
        attack_id = _attack_ids_from_state(session_state, prefix)[0]
        return _build_config_from_profiles(
            default_build_name,
            (AttackProfile("Attack 1", 5, "1d8+3", 1, attack_id=attack_id),),
        )
    profiles = []
    for _index, (attack_id, _, default_name) in enumerate(
        _profile_definitions(prefix, 0)
    ):
        widget_prefix = _state_widget_prefix(prefix, attack_id)
        resolution = {
            "Attack Roll": ResolutionType.ATTACK_ROLL,
            "Saving Throw": ResolutionType.SAVING_THROW,
            "Automatic Damage": ResolutionType.AUTOMATIC_DAMAGE,
        }.get(
            session_state.get(
                profile_widget_key(widget_prefix, "resolution_type"), "Attack Roll"
            ),
            ResolutionType.ATTACK_ROLL,
        )
        affected_targets = int(
            session_state.get(profile_widget_key(widget_prefix, "affected_targets"), 1)
        )
        features = available_features(
            frozenset(
                feature
                for feature in FEATURE_ORDER
                if session_state.get(feature_widget_key(widget_prefix, feature), False)
            ),
            resolution,
            affected_targets=affected_targets,
        )
        profiles.append(
            AttackProfile(
                session_state.get(
                    profile_widget_key(widget_prefix, "name"), default_name
                ),
                (
                    int(
                        session_state.get(
                            profile_widget_key(widget_prefix, "attack_bonus"), 5
                        )
                    )
                    if resolution is ResolutionType.ATTACK_ROLL
                    else None
                ),
                session_state.get(
                    profile_widget_key(widget_prefix, "damage_formula"), "1d8+3"
                ),
                int(
                    session_state.get(
                        profile_widget_key(widget_prefix, "attacks_per_round"), 1
                    )
                ),
                affected_targets,
                AttackRollMode(
                    str(
                        session_state.get(
                            profile_widget_key(widget_prefix, "attack_roll_mode"),
                            "Normal",
                        )
                    ).lower()
                ),
                session_state.get(
                    profile_widget_key(widget_prefix, "active_rounds"), ""
                ),
                resolution,
                (
                    int(
                        session_state.get(
                            profile_widget_key(widget_prefix, "save_dc"), 13
                        )
                    )
                    if resolution is ResolutionType.SAVING_THROW
                    else None
                ),
                (
                    SuccessfulSaveDamage.HALF_DAMAGE
                    if session_state.get(
                        profile_widget_key(widget_prefix, "successful_save_damage"),
                        "No damage",
                    )
                    == "Half damage"
                    else SuccessfulSaveDamage.NO_DAMAGE
                ),
                features,
                attack_id,
                (
                    {
                        "Another attack succeeds": TriggerType.AFTER_SUCCESS,
                        "After another attack succeeds": TriggerType.AFTER_SUCCESS,
                        "Another attack fails": TriggerType.AFTER_FAILURE,
                        "Another attack critically hits": TriggerType.AFTER_CRITICAL,
                        "Sometimes": TriggerType.SOMETIMES,
                    }.get(
                        session_state.get(
                            profile_widget_key(widget_prefix, "trigger_type"),
                            "Always",
                        ),
                        TriggerType.ALWAYS,
                    )
                ),
                session_state.get(
                    profile_widget_key(widget_prefix, "trigger_source_attack_id")
                ),
                (
                    {
                        "Once per round": TriggerFrequency.ONCE_PER_ROUND,
                        "Once per combat": TriggerFrequency.ONCE_PER_COMBAT,
                        "Once if any resolution succeeds": (
                            TriggerFrequency.ONCE_PER_ROUND
                        ),
                    }.get(
                        str(
                            session_state.get(
                                profile_widget_key(widget_prefix, "trigger_frequency"),
                                "",
                            )
                        ),
                        TriggerFrequency.PER_SUCCESS,
                    )
                ),
                (
                    int(
                        str(
                            session_state.get(
                                profile_widget_key(
                                    widget_prefix, "trigger_chance_percent"
                                ),
                                "",
                            )
                        )
                    )
                    if str(
                        session_state.get(
                            profile_widget_key(widget_prefix, "trigger_chance_percent"),
                            "",
                        )
                    ).isdigit()
                    else None
                ),
                (
                    (
                        ResourceCost(
                            str(
                                session_state.get(
                                    profile_widget_key(widget_prefix, "resource_id"), ""
                                )
                            ),
                            int(
                                session_state.get(
                                    profile_widget_key(
                                        widget_prefix, "resource_amount"
                                    ),
                                    1,
                                )
                            ),
                        ),
                    )
                    if session_state.get(
                        profile_widget_key(widget_prefix, "resource_enabled"), False
                    )
                    else ()
                ),
            )
        )
    return _build_config_from_profiles(
        session_state.get(f"{prefix}-build-name", default_build_name),
        tuple(profiles),
    )


def _default_second_build_from_state() -> BuildConfig:
    """Build hidden Build B from existing session-state values or widget defaults."""
    return _build_from_state("second", "Build B")
