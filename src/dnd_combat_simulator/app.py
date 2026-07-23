"""Streamlit application entry point."""

from __future__ import annotations

import logging
import time
from contextlib import nullcontext
from dataclasses import dataclass
from secrets import randbelow
from textwrap import dedent
from uuid import uuid4

from dnd_combat_simulator import APP_TITLE
from dnd_combat_simulator.combat import (
    AttackFeature,
    AttackRollMode,
    ResolutionType,
    SuccessfulSaveDamage,
    available_features,
    is_feature_available,
    validate_feature_resolution_combination,
)
from dnd_combat_simulator.share_store import (
    InvalidShareIdError,
    ShareNotFoundError,
    ShareStore,
    ShareStoreError,
    StoredShareConfigurationError,
    SupabaseShareStore,
)
from dnd_combat_simulator.sharing import (
    SharedBuildConfiguration,
    SharedConfiguration,
    SharedConfigurationError,
    build_share_url,
    build_short_share_url,
    deserialize_shared_configuration,
    migrate_shared_build_attack_ids,
    serialize_shared_configuration,
    shared_configuration_from_configs,
)
from dnd_combat_simulator.simulation import (
    AttackProfile,
    AttackProfileResult,
    BuildComparisonResult,
    BuildConfig,
    ManagedResource,
    ResourceCost,
    ScenarioConfig,
    SimulationResult,
    TriggerFrequency,
    TriggerType,
    compare_builds,
    run_damage_simulations,
    simulate_build,
)

FEATURE_LABELS = {
    AttackFeature.ELVEN_ACCURACY: "Elven Accuracy",
    AttackFeature.GREAT_WEAPON_FIGHTING: "Great Weapon Fighting",
    AttackFeature.TAVERN_BRAWLER: "Tavern Brawler",
    AttackFeature.STOP_ON_MISS: "Stop on Miss",
    AttackFeature.POTENT_CANTRIP: "Potent Cantrip",
}

FEATURE_HELP = {
    AttackFeature.ELVEN_ACCURACY: (
        "When this profile makes an eligible Dexterity, Intelligence, Wisdom, or "
        "Charisma attack with Advantage, reroll one of the two d20s once. The "
        "lower die is rerolled and the highest remaining result is used."
    ),
    AttackFeature.GREAT_WEAPON_FIGHTING: (
        "Whenever this profile rolls a damage die, treat a result of 1 or 2 as a "
        "3. This changes the die's damage contribution but does not change its "
        "natural face for exploding-die checks."
    ),
    AttackFeature.TAVERN_BRAWLER: (
        "Whenever this profile rolls a damage die and the accepted result is 1, "
        "reroll that die once. The replacement result must be used, even if it "
        "is another 1."
    ),
    AttackFeature.STOP_ON_MISS: (
        "Resolve this profile's attacks in order. When one attack misses, skip all "
        "remaining attacks from this profile during that round. The sequence resets "
        "at the beginning of the next active round."
    ),
    AttackFeature.POTENT_CANTRIP: (
        "When an Attack Roll misses or a Saving Throw succeeds, roll normal "
        "noncritical damage and deal half, rounded down. Automatic Damage profiles "
        "cannot use this feature."
    ),
}

FEATURE_ORDER = (
    AttackFeature.ELVEN_ACCURACY,
    AttackFeature.GREAT_WEAPON_FIGHTING,
    AttackFeature.TAVERN_BRAWLER,
    AttackFeature.STOP_ON_MISS,
    AttackFeature.POTENT_CANTRIP,
)

DAMAGE_FORMULA_HELP = dedent("""
    **Basic**

    - `1d8`
    - `2d6+4`
    - `1d10-1`

    **Reroll**

    - `2d8r<2` — reroll 1s and 2s
    - `2d8r8` — reroll 8s
    - `2d8r1r3r5r7` — reroll odd results

    **Exploding**

    - `3d6!` — explode on 6
    - `3d6!>4` — explode on 4, 5, or 6
    - `3d6!3` — explode only on 3

    **Keep or drop**

    - `4d6kh3` — keep highest 3
    - `4d6kl3` — keep lowest 3
    - `8d100dl3` — drop lowest 3
    - `8d100dh3` — drop highest 3

    **Combined**

    - `4d6r1!kh3+2`
    - `1d6+1d4+4d4+3`
    - `4d6kh3+2d8!+1d4-2`

    **Processing order**

    Each dice group is rolled independently. Formula rerolls, Tavern Brawler,
    explosion checks, Great Weapon Fighting damage contribution, and keep/drop
    apply only to the dice group where they are written. Numeric modifiers apply
    once to the complete damage roll.
    """).strip()

NO_ELIGIBLE_TRIGGER_SOURCE_MESSAGE = (
    "Add another attack to this build before configuring an attack trigger."
)

DAMAGE_FORMULA_PLACEHOLDER = "Examples: 1d8+4, 3d6!, 3d6!>4, 4d6kh3+2, 8d100dh3."


SCENARIO_WIDGET_KEYS = {
    "target_armor_class": "scenario-target-ac",
    "enemy_save_bonus": "scenario-enemy-save-bonus",
    "rounds": "scenario-rounds",
    "simulations": "scenario-simulations",
    "seed": "scenario-seed",
}
COMPARE_WIDGET_KEY = "compare-builds-enabled"
LOADED_SHARED_CONFIG_TOKEN_KEY = "_loaded_shared_config_token"
LOADED_SHARE_ID_KEY = "_loaded_share_id"
GENERATED_SHARE_URL_KEY = "_generated_share_url"
GENERATED_SHARE_FINGERPRINT_KEY = "_generated_share_fingerprint"
SHARE_ERROR_MESSAGE_KEY = "_share_error_message"
LOADED_SHARED_CONFIG_MESSAGE_KEY = "_shared_config_loaded_message_pending"
INVALID_SHARED_CONFIG_MESSAGE_KEY = "_invalid_shared_config_message"
SIMULATION_RUNNING_KEY = "_simulation_running"
SIMULATION_PENDING_KEY = "_simulation_pending"
SIMULATION_DURATION_MESSAGE_KEY = "_simulation_duration_message"
TRIGGER_EXPANDED_KEY_SUFFIX = "trigger-expanded"
MANAGED_RESOURCE_COUNT_KEY = "scenario-managed-resource-count"
MANAGED_RESOURCE_EXPANDED_KEY = "scenario-managed-resources-expanded"
ATTACK_DELETE_CONFIRMATION_KEY = "attack-delete-confirmation-id"
RESOURCE_DELETE_CONFIRMATION_KEY = "resource-delete-confirmation-id"
MANAGED_RESOURCE_IDS_KEY = "scenario-managed-resource-ids"

MAX_ATTACKS_PER_BUILD = 11
ATTACK_IDS_KEY_SUFFIX = "attack-ids"


def build_attack_ids_key(build_prefix: str) -> str:
    return f"{build_prefix}-{ATTACK_IDS_KEY_SUFFIX}"


def _new_attack_id(build_prefix: str, position: int = 0) -> str:
    del build_prefix, position
    return f"attack-{uuid4().hex}"


def _legacy_profile_prefixes(build_prefix: str) -> list[str]:
    count = (
        int(
            getattr(__import__("streamlit"), "session_state", {}).get(
                f"{build_prefix}-additional-attack-count", 0
            )
        )
        if False
        else 0
    )
    return [profile_prefix(build_prefix, index) for index in range(count + 1)]


def _copy_attack_widget_state(state, source_prefix: str, dest_prefix: str) -> None:
    for field in (
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
    ):
        source_key = profile_widget_key(source_prefix, field)
        if source_key in state:
            state[profile_widget_key(dest_prefix, field)] = state[source_key]
    for feature in FEATURE_ORDER:
        source_key = feature_widget_key(source_prefix, feature)
        if source_key in state:
            state[feature_widget_key(dest_prefix, feature)] = state[source_key]
    expander_key = trigger_expanded_state_key(source_prefix)
    if expander_key in state:
        state[trigger_expanded_state_key(dest_prefix)] = state[expander_key]
    for suffix in ("features-expanded", "resource-expanded"):
        source_key = f"{source_prefix}-{suffix}"
        if source_key in state:
            state[f"{dest_prefix}-{suffix}"] = state[source_key]


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


def _duplicate_attack_state(state, source_id: str, new_id: str) -> None:
    source_prefix = f"{source_id}-"
    for key, value in list(state.items()):
        key_text = str(key)
        if key_text.startswith(source_prefix):
            state[f"{new_id}-" + key_text[len(source_prefix) :]] = value
    state[profile_widget_key(new_id, "name")] = (
        str(state.get(profile_widget_key(source_id, "name"), "Attack")).strip()
        + " copy"
    )
    if state.get(profile_widget_key(new_id, "trigger_source_attack_id")) == source_id:
        state[profile_widget_key(new_id, "trigger_type")] = "Always"
        state[profile_widget_key(new_id, "trigger_source_attack_id")] = None


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


@dataclass(frozen=True)
class FieldValidationError:
    """A validation message associated with one editable Streamlit field."""

    key: str
    message: str


def _friendly_validation_message(error: ValueError) -> str:
    text = str(error)
    lower_prefix = "invalid damage expression: "
    if text.lower().startswith(lower_prefix):
        text = text[len(lower_prefix) :]
    elif ": invalid damage expression: " in text.lower():
        text = text.split(": ", 1)[1]
    if text.startswith("damage expression "):
        text = "Damage expression " + text[len("damage expression ") :]
    elif text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def _add_error(errors: list[FieldValidationError], key: str, message: str) -> None:
    errors.append(FieldValidationError(key, message))


def _validate_profile_fields(
    profile: AttackProfile, *, prefix: str
) -> list[FieldValidationError]:
    from dnd_combat_simulator.dice import parse_damage_expression
    from dnd_combat_simulator.simulation import parse_active_rounds

    errors: list[FieldValidationError] = []
    if not profile.name.strip():
        _add_error(
            errors, profile_widget_key(prefix, "name"), "Attack name is required."
        )
    if not profile.damage_dice.strip():
        _add_error(
            errors,
            profile_widget_key(prefix, "damage_formula"),
            "Damage expression is required.",
        )
    else:
        try:
            parse_damage_expression(profile.damage_dice)
        except ValueError as error:
            _add_error(
                errors,
                profile_widget_key(prefix, "damage_formula"),
                _friendly_validation_message(error),
            )
    if profile.attacks_per_round < 1:
        _add_error(
            errors,
            profile_widget_key(prefix, "attacks_per_round"),
            "Attacks per round must be at least 1.",
        )
    if profile.affected_targets < 1:
        _add_error(
            errors,
            profile_widget_key(prefix, "affected_targets"),
            "Target Resolutions must be at least 1.",
        )
    if (
        profile.resolution_type is ResolutionType.ATTACK_ROLL
        and profile.attack_bonus is None
    ):
        _add_error(
            errors,
            profile_widget_key(prefix, "attack_bonus"),
            "Attack bonus is required.",
        )
    if profile.resolution_type is ResolutionType.SAVING_THROW:
        if profile.save_dc is None:
            _add_error(
                errors, profile_widget_key(prefix, "save_dc"), "Save DC is required."
            )
        elif profile.save_dc < 1:
            _add_error(
                errors,
                profile_widget_key(prefix, "save_dc"),
                "Save DC must be a positive integer.",
            )
    try:
        parse_active_rounds(profile.active_rounds)
    except ValueError as error:
        _add_error(errors, profile_widget_key(prefix, "active_rounds"), str(error))
    for cost in profile.resource_costs:
        if not cost.resource_id:
            _add_error(
                errors,
                profile_widget_key(prefix, "resource_id"),
                "Select a resource or choose None.",
            )
        if not isinstance(cost.amount, int) or cost.amount < 1:
            _add_error(
                errors,
                profile_widget_key(prefix, "resource_amount"),
                "Resource cost must be a whole number greater than 0.",
            )
    try:
        validate_feature_resolution_combination(
            profile.features,
            profile.resolution_type,
            label=profile.name or "Attack profile",
            affected_targets=profile.affected_targets,
        )
    except ValueError as error:
        _add_error(errors, profile_widget_key(prefix, "resolution_type"), str(error))
    return errors


def validate_build_fields(
    build: BuildConfig, *, prefix: str
) -> list[FieldValidationError]:
    errors: list[FieldValidationError] = []
    if not build.name.strip():
        _add_error(errors, f"{prefix}-build-name", "Build name is required.")
    profiles = build.resolved_attack_profiles()
    for index, profile in enumerate(profiles):
        widget_prefix = (
            _state_widget_prefix(prefix, profile.attack_id)
            if profile.attack_id
            else profile_prefix(prefix, index)
        )
        errors.extend(_validate_profile_fields(profile, prefix=widget_prefix))
    profile_ids = [profile.attack_id for profile in profiles]
    if False and any(not attack_id.strip() for attack_id in profile_ids):
        _add_error(
            errors,
            f"{prefix}-attack-ids",
            f"{build.name or 'Build'} contains an empty attack ID.",
        )
    duplicate_ids = {
        attack_id for attack_id in profile_ids if profile_ids.count(attack_id) > 1
    }
    if duplicate_ids:
        _add_error(
            errors,
            f"{prefix}-attack-ids",
            f"{build.name or 'Build'} contains duplicate attack IDs: "
            + ", ".join(sorted(duplicate_ids)),
        )
        return errors
    trigger_source_error_keys: set[str] = set()

    def has_path_to_current(source_id: str, current_id: str) -> bool:
        dependencies = {
            profile.attack_id: profile.trigger_source_attack_id
            for profile in profiles
            if TriggerType(profile.trigger_type) is not TriggerType.ALWAYS
        }
        seen: set[str] = set()
        cursor = source_id
        while cursor and cursor not in seen:
            if cursor == current_id:
                return True
            seen.add(cursor)
            cursor = dependencies.get(cursor)
        return False

    for index, profile in enumerate(profiles):
        widget_prefix = (
            _state_widget_prefix(prefix, profile.attack_id)
            if profile.attack_id
            else profile_prefix(prefix, index)
        )
        source_key = profile_widget_key(widget_prefix, "trigger_source_attack_id")
        trigger_type = TriggerType(profile.trigger_type)
        if trigger_type is TriggerType.ALWAYS:
            continue
        if trigger_type is TriggerType.SOMETIMES:
            if (
                not isinstance(profile.trigger_chance_percent, int)
                or profile.trigger_chance_percent < 1
                or profile.trigger_chance_percent > 100
            ):
                _add_error(
                    errors,
                    profile_widget_key(widget_prefix, "trigger_chance_percent"),
                    "Enter a whole number from 1 through 100.",
                )
                if profile.attack_id and widget_prefix != profile.attack_id:
                    _add_error(
                        errors,
                        profile_widget_key(profile.attack_id, "trigger_chance_percent"),
                        "Enter a whole number from 1 through 100.",
                    )
            continue
        other_ids = [
            attack_id for attack_id in profile_ids if attack_id != profile.attack_id
        ]
        eligible_ids = [
            attack_id
            for attack_id in other_ids
            if not has_path_to_current(attack_id, profile.attack_id)
        ]
        source_id = profile.trigger_source_attack_id
        if not source_id:
            _add_error(
                errors,
                source_key,
                (
                    NO_ELIGIBLE_TRIGGER_SOURCE_MESSAGE
                    if not eligible_ids
                    else "Select the attack that must succeed first."
                ),
            )
            trigger_source_error_keys.add(source_key)
        elif source_id not in eligible_ids:
            _add_error(
                errors,
                source_key,
                (
                    "The selected trigger source is missing, self-referential, "
                    "or circular."
                ),
            )
            trigger_source_error_keys.add(source_key)
    if not trigger_source_error_keys:
        try:
            from dnd_combat_simulator.simulation import validate_trigger_dependencies

            validate_trigger_dependencies(profiles, label=build.name or "Build")
        except ValueError as error:
            if profiles:
                _add_error(
                    errors,
                    profile_widget_key(
                        (
                            attack_widget_prefix(prefix, profiles[0].attack_id)
                            if profiles[0].attack_id
                            else profile_prefix(prefix, 0)
                        ),
                        "trigger_type",
                    ),
                    str(error),
                )
    return errors


def validate_scenario_fields(scenario: ScenarioConfig) -> list[FieldValidationError]:
    errors: list[FieldValidationError] = []
    if scenario.target_armor_class < 1:
        _add_error(
            errors,
            SCENARIO_WIDGET_KEYS["target_armor_class"],
            "Target Armor Class must be at least 1.",
        )
    if scenario.rounds < 1:
        _add_error(
            errors,
            SCENARIO_WIDGET_KEYS["rounds"],
            "Number of rounds must be at least 1.",
        )
    if scenario.simulations < 1:
        _add_error(
            errors,
            SCENARIO_WIDGET_KEYS["simulations"],
            "Number of simulations must be at least 1.",
        )
    names = [
        resource.name.strip().casefold() for resource in scenario.managed_resources
    ]
    for resource in scenario.managed_resources:
        if not resource.name.strip():
            _add_error(
                errors,
                managed_resource_widget_key(resource.resource_id, "name"),
                "Resource name is required.",
            )
        elif names.count(resource.name.strip().casefold()) > 1:
            _add_error(
                errors,
                managed_resource_widget_key(resource.resource_id, "name"),
                "Resource names must be unique.",
            )
        if not isinstance(resource.starting_value, int) or resource.starting_value < 0:
            _add_error(
                errors,
                managed_resource_widget_key(resource.resource_id, "starting-value"),
                "Starting value must be a whole number of at least 0.",
            )
    return errors


def validation_errors_by_key(errors: list[FieldValidationError]) -> dict[str, str]:
    return {error.key: error.message for error in errors}


def validate_configuration_for_ui(
    configuration: SharedConfiguration,
) -> dict[tuple[str, str | None, str], str]:
    """Return structured editable-field errors for a shared configuration.

    Keys are scoped by build (``build_a``/``build_b``), profile identifier, and
    field name so similarly named fields in different builds or profiles cannot
    be conflated.
    """

    structured: dict[tuple[str, str | None, str], str] = {}
    for error in validate_scenario_fields(configuration.scenario.to_scenario_config()):
        structured[("scenario", None, error.key)] = error.message
    for build_key, prefix, build in (
        ("build_a", "first", configuration.build_a),
        ("build_b", "second", configuration.build_b),
    ):
        attack_ids = [profile.attack_id for profile in build.attack_profiles]
        widget_to_attack = {
            _state_widget_prefix(prefix, attack_id): attack_id
            for attack_id in attack_ids
        }
        for index, attack_id in enumerate(attack_ids):
            widget_to_attack[profile_prefix(prefix, index)] = attack_id
        for error in validate_build_fields(build.to_build_config(), prefix=prefix):
            profile_id: str | None = None
            field = error.key
            if error.key == f"{prefix}-build-name":
                field = "name"
            elif error.key == f"{prefix}-attack-ids":
                field = "attack_ids"
            else:
                for widget_prefix, attack_id in sorted(
                    widget_to_attack.items(),
                    key=lambda item: len(item[0]),
                    reverse=True,
                ):
                    marker = f"{widget_prefix}-"
                    if error.key.startswith(marker):
                        profile_id = attack_id
                        field = error.key.removeprefix(marker).replace("-", "_")
                        break
            structured[(build_key, profile_id, field)] = error.message
    return structured


def _configuration_errors_for_current_state() -> dict[tuple[str, str | None, str], str]:
    import streamlit as st

    session_state = getattr(st, "session_state", {})
    scenario = ScenarioConfig(
        target_armor_class=int(
            session_state.get(SCENARIO_WIDGET_KEYS["target_armor_class"], 15)
        ),
        enemy_save_bonus=int(
            session_state.get(SCENARIO_WIDGET_KEYS["enemy_save_bonus"], 3)
        ),
        rounds=int(session_state.get(SCENARIO_WIDGET_KEYS["rounds"], 4)),
        simulations=int(session_state.get(SCENARIO_WIDGET_KEYS["simulations"], 10_000)),
        managed_resources=_managed_resources_from_state(),
    )
    configuration = shared_configuration_from_configs(
        compare_enabled=bool(session_state.get(COMPARE_WIDGET_KEY, False)),
        scenario=scenario,
        seed=int(session_state.get(SCENARIO_WIDGET_KEYS["seed"], 20240721)),
        build_a=_build_from_state("first", "Build A"),
        build_b=_build_from_state("second", "Build B"),
    )
    return validate_configuration_for_ui(configuration)


def _render_error(message: str) -> None:
    import streamlit as st

    error = getattr(st, "error", None)
    if error is not None:
        error(message, icon="⚠️")


def _field_error(errors_by_key: dict[str, str], key: str) -> bool:
    if message := errors_by_key.get(key):
        _render_error(message)
        return True
    return False


SHARE_TOOLBAR_HTML = """
<div class="share-toolbar" role="group" aria-label="Share configuration">
    <button
        class="share-button"
        type="button"
        title="Copy share link"
        aria-label="Copy share link"
    >
        <svg
            class="share-icon"
            viewBox="0 0 24 24"
            aria-hidden="true"
            focusable="false"
        >
            <path
                d="M6 18c.8-4.9 4-7.3 9.1-7.3h1.2"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
            />
            <path
                d="M13.8 6.2 18.6 11l-4.8 4.8"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
            />
        </svg>
        <span class="share-label">Share Configuration</span>
    </button>
    <a class="share-link" href="" target="_blank" rel="noopener noreferrer" hidden></a>
    <input class="share-fallback" type="text" readonly hidden />
    <span class="share-status" aria-live="polite"></span>
</div>
"""

SHARE_TOOLBAR_CSS = """
.share-toolbar {
    min-height: 42px;
    height: 42px;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    width: max-content;
    max-width: 100%;
    color: var(--st-text-color);
    background: var(--st-background-color);
    font-family: var(--st-font);
    overflow: hidden;
}

.share-button {
    height: 42px;
    min-width: 42px;
    box-sizing: border-box;
    padding: 0 0.9rem;
    border-radius: 999px; /* legacy circle control used border-radius: 50% */
    border: 1px solid var(--st-border-color);
    background: var(--st-secondary-background-color);
    color: var(--st-text-color);
    font-family: var(--st-font);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.45rem;
    line-height: 1;
    cursor: pointer;
}

.share-button:hover:not(:disabled) {
    border-color: var(--st-primary-color);
    color: var(--st-primary-color);
}

.share-button:focus-visible {
    outline: 2px solid var(--st-primary-color);
    outline-offset: 2px;
}

.share-button:disabled {
    cursor: not-allowed;
    opacity: 0.6;
}

.share-icon {
    width: 20px;
    height: 20px;
    flex: 0 0 auto;
}

.share-link {
    min-width: 0;
    max-width: min(42rem, 55vw);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--st-primary-color);
    font-family: var(--st-font);
    align-self: center;
}

.share-link[hidden] {
    display: none;
}

.share-status {
    min-width: 12rem;
    color: var(--st-text-color);
    font-family: var(--st-font);
    opacity: 0;
    transition: opacity 180ms ease;
    text-overflow: ellipsis;
}

.share-status.visible {
    opacity: 1;
}

.share-fallback {
    width: min(24rem, 45vw);
    min-width: 12rem;
    font-family: var(--st-font);
}

.share-fallback[hidden] {
    display: none;
}
"""

SHARE_TOOLBAR_JS = """
export default function(component) {
    const { data, parentElement, setTriggerValue } = component;
    const button = parentElement.querySelector('.share-button');
    const label = parentElement.querySelector('.share-label');
    const status = parentElement.querySelector('.share-status');
    const link = parentElement.querySelector('.share-link');
    const fallbackInput = parentElement.querySelector('.share-fallback');
    let latestData = {};
    let statusTimer = null;
    let mode = 'create';

    function setStatus(message, temporary = false) {
        status.textContent = message || '';
        status.classList.toggle('visible', Boolean(message));
        if (statusTimer !== null) {
            window.clearTimeout(statusTimer);
            statusTimer = null;
        }
        if (temporary) {
            statusTimer = window.setTimeout(() => {
                setStatus('');
                if (mode === 'copy') {
                    label.textContent = 'Copy';
                }
            }, 1500);
        }
    }

    function revealFallback(message) {
        fallbackInput.value = latestData.url || '';
        fallbackInput.hidden = false;
        fallbackInput.focus();
        fallbackInput.select();
        label.textContent = 'Copy';
        setStatus(message);
    }

    function showCopied() {
        fallbackInput.hidden = true;
        label.textContent = 'Copied';
        setStatus('', true);
    }

    function render(nextData) {
        latestData = nextData || {};
        button.disabled = Boolean(latestData.disabled || latestData.creating);
        fallbackInput.hidden = true;
        fallbackInput.value = latestData.url || '';
        button.title = latestData.url ? 'Copy share link' : 'Share configuration';
        button.setAttribute('aria-label', button.title);
        link.hidden = !latestData.url || Boolean(latestData.creating);
        link.href = latestData.url || '';
        link.textContent = latestData.url || '';
        link.title = latestData.url || '';

        if (latestData.disabled) {
            label.textContent = latestData.creating
                ? 'Creating...'
                : 'Share Configuration';
            setStatus(latestData.message || '');
            mode = 'disabled';
        } else if (latestData.creating) {
            label.textContent = 'Creating...';
            setStatus('');
            mode = 'creating';
        } else if (latestData.url) {
            label.textContent = 'Copy';
            setStatus('');
            mode = 'copy';
        } else {
            label.textContent = 'Share Configuration';
            setStatus(latestData.message || '');
            mode = 'create';
        }
    }

    async function copyUrl() {
        const targetUrl = latestData.url || '';
        if (!targetUrl) {
            return false;
        }
        if (navigator.clipboard && window.isSecureContext) {
            try {
                await navigator.clipboard.writeText(targetUrl);
                showCopied();
                return true;
            } catch (error) {
                // Fall through to the selectable-input fallback below.
            }
        }

        revealFallback('Copy blocked. Press Ctrl+C.');
        try {
            if (document.execCommand("copy")) {
                showCopied();
                return true;
            }
        } catch (fallbackError) {
            // Keep the selectable fallback visible.
        }
        revealFallback('Copy blocked. Press Ctrl+C.');
        return false;
    }

    render(data || {});

    button.onclick = async () => {
        if (mode === 'create') {
            label.textContent = 'Creating...';
            button.disabled = true;
            setTriggerValue('create_share', `${Date.now()}-${Math.random()}`);
        } else if (mode === 'copy') {
            await copyUrl();
        }
    };

    return () => {
        if (statusTimer !== null) {
            window.clearTimeout(statusTimer);
        }
        button.onclick = null;
    };
}
"""

CONFIGURATION_TOOLBAR_CSS = """
<style>
.st-key-configuration-toolbar {
    display: inline-flex;
    width: max-content;
    max-width: 100%;
    align-items: center;
    gap: 8px;
}

.st-key-configuration-toolbar [data-testid="stHorizontalBlock"] {
    display: inline-flex;
    width: max-content;
    max-width: 100%;
    align-items: center;
    gap: 8px;
}

.st-key-configuration-toolbar [data-testid="stVerticalBlock"],
.st-key-configuration-toolbar [data-testid="stElementContainer"] {
    width: max-content;
    max-width: 100%;
}

.st-key-configuration-toolbar [data-testid="stPopover"] {
    width: max-content;
}

.st-key-configuration-toolbar [data-testid="stPopover"] button,
.st-key-configuration-toolbar button[kind="secondary"] {
    height: 42px;
    min-height: 42px;
    min-width: 42px;
    box-sizing: border-box;
    padding: 0 0.9rem;
    border: 1px solid var(--st-border-color);
    border-radius: 999px;
    background: var(--st-secondary-background-color);
    color: var(--st-text-color);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    line-height: 1;
    margin: 0;
}

.st-key-configuration-toolbar [data-testid="stPopover"] button {
    width: 42px;
    padding: 0;
}

.st-key-configuration-toolbar [data-testid="stPopover"] button:hover:not(:disabled),
.st-key-configuration-toolbar button[kind="secondary"]:hover:not(:disabled) {
    border-color: var(--st-primary-color);
    color: var(--st-primary-color);
}

.st-key-configuration-toolbar [data-testid="stPopover"] button:focus-visible,
.st-key-configuration-toolbar button[kind="secondary"]:focus-visible {
    outline: 2px solid var(--st-primary-color);
    outline-offset: 2px;
}
</style>
"""

_SHARE_TOOLBAR_COMPONENT = None


def _get_share_toolbar_component():
    """Register and return the v2 share toolbar component."""
    global _SHARE_TOOLBAR_COMPONENT
    if _SHARE_TOOLBAR_COMPONENT is None:
        import streamlit as st

        components = getattr(st, "components", None)
        if components is None or not hasattr(components, "v2"):
            return lambda **kwargs: None
        _SHARE_TOOLBAR_COMPONENT = st.components.v2.component(
            "share_toolbar",
            html=SHARE_TOOLBAR_HTML,
            css=SHARE_TOOLBAR_CSS,
            js=SHARE_TOOLBAR_JS,
        )
    return _SHARE_TOOLBAR_COMPONENT


def profile_prefix(build_prefix: str, index: int) -> str:
    return (
        f"{build_prefix}-primary"
        if index == 0
        else f"{build_prefix}-additional-{index}"
    )


def attack_widget_prefix(build_prefix: str, attack_id: str) -> str:
    return f"{build_prefix}-{attack_id}"


def _state_widget_prefix(build_prefix: str, attack_id: str) -> str:
    if _looks_like_widget_prefix(build_prefix, attack_id):
        return attack_id
    return attack_widget_prefix(build_prefix, attack_id)


def profile_widget_key(prefix: str, field: str) -> str:
    suffixes = {
        "name": "name",
        "resolution_type": "resolution-type",
        "attack_bonus": "attack-bonus",
        "save_dc": "save-dc",
        "successful_save_damage": "successful-save-damage",
        "attack_roll_mode": "mode",
        "damage_formula": "damage-dice",
        "attacks_per_round": "attacks",
        "affected_targets": "affected-targets",
        "active_rounds": "active-rounds",
        "trigger_type": "trigger-type",
        "trigger_source_attack_id": "trigger-source-attack-id",
        "trigger_frequency": "trigger-frequency",
        "trigger_chance_percent": "trigger-chance-percent",
        "resource_enabled": "resource-enabled",
        "resource_id": "resource-id",
        "resource_amount": "resource-amount",
    }
    return f"{prefix}-{suffixes[field]}"


def feature_widget_key(prefix: str, feature: AttackFeature) -> str:
    return f"{prefix}-feature-{feature.value}"


PAGE_WIDTH_CSS = """
<style>
    .stApp .block-container {
        width: 90vw;
        max-width: 90vw;
        margin-left: auto;
        margin-right: auto;
        padding-left: clamp(1rem, 2vw, 2.5rem);
        padding-right: clamp(1rem, 2vw, 2.5rem);
        box-sizing: border-box;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 14px;
        border-color: rgba(128, 128, 128, 0.28);
        box-shadow: 0 0.25rem 0.8rem rgba(0, 0, 0, 0.06);
    }

    div[data-testid="stVerticalBlockBorderWrapper"] > div {
        padding: clamp(0.75rem, 1.3vw, 1.25rem);
    }

    @media (max-width: 640px) {
        .stApp .block-container {
            width: 100%;
            max-width: 100%;
            padding-left: 1rem;
            padding-right: 1rem;
        }
    }
</style>
"""


def configure_page() -> None:
    """Configure Streamlit to use a wide, centered application layout."""
    import streamlit as st

    st.set_page_config(page_title=APP_TITLE, page_icon="🎲", layout="wide")
    st.markdown(PAGE_WIDTH_CSS, unsafe_allow_html=True)


@dataclass(frozen=True)
class SimulationInputs:
    """Validated user inputs for a damage simulation run."""

    attack_bonus: int
    target_armor_class: int
    damage_dice: str
    rounds: int
    attacks_per_round: int
    simulations: int
    enemy_save_bonus: int = 3
    attack_roll_mode: AttackRollMode = AttackRollMode.NORMAL


@dataclass(frozen=True)
class ComparisonInputs:
    """Validated user inputs for a named build comparison."""

    first_build: BuildConfig
    second_build: BuildConfig
    scenario: ScenarioConfig
    seed: int


@dataclass(frozen=True)
class SingleBuildInputs:
    """Validated user inputs for a single named build simulation."""

    build: BuildConfig
    scenario: ScenarioConfig
    seed: int


def validate_simulation_inputs(inputs: SimulationInputs) -> None:
    """Validate Streamlit form inputs before running a simulation.

    Raises:
        ValueError: If an input cannot produce a usable damage simulation.
    """
    if not inputs.damage_dice.strip():
        msg = "Damage Formula is required. Use notation such as 1d8+4."
        raise ValueError(msg)
    if inputs.target_armor_class < 1:
        msg = "Target Armor Class must be at least 1."
        raise ValueError(msg)
    if inputs.rounds < 1:
        msg = "Number of rounds must be at least 1."
        raise ValueError(msg)
    if inputs.attacks_per_round < 1:
        msg = "Attacks per round must be at least 1."
        raise ValueError(msg)
    if inputs.simulations < 1:
        msg = "Number of simulations must be at least 1."
        raise ValueError(msg)


def format_damage(value: float) -> str:
    """Format a damage value for display."""
    return f"{value:.2f}"


def format_compact_decimal(value: float) -> str:
    """Format a decimal with up to two places and no unnecessary trailing zeros."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def format_rate(value: float) -> str:
    """Format a fractional rate as a percentage for display."""
    return f"{value:.2%}"


def format_signed_damage(value: float) -> str:
    """Format a signed damage delta for display."""
    return f"{value:+.2f}"


def format_signed_compact_decimal(value: float) -> str:
    """Format a signed decimal delta with compact trailing zero handling."""
    return f"{value:+.2f}".rstrip("0").rstrip(".")


def format_signed_rate(value: float) -> str:
    """Format a signed fractional rate as a percentage-point delta."""
    return f"{value:+.2%}"


def format_positive_damage(value: float) -> str:
    """Format a non-negative damage delta for display."""
    return f"{value:.2f}"


def format_positive_compact_decimal(value: float) -> str:
    """Format a non-negative decimal delta with compact trailing zero handling."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def format_positive_rate(value: float) -> str:
    """Format a non-negative fractional rate as a percentage-point delta."""
    return f"{value:.2%}"


def run_simulation_from_inputs(inputs: SimulationInputs) -> SimulationResult:
    """Validate inputs and run the shared simulation engine."""
    validate_simulation_inputs(inputs)
    return run_damage_simulations(
        attack_bonus=inputs.attack_bonus,
        target_armor_class=inputs.target_armor_class,
        enemy_save_bonus=inputs.enemy_save_bonus,
        damage_dice=inputs.damage_dice.strip(),
        rounds=inputs.rounds,
        simulations=inputs.simulations,
        attacks_per_round=inputs.attacks_per_round,
        attack_roll_mode=inputs.attack_roll_mode,
    )


def run_single_build_from_inputs(inputs: SingleBuildInputs) -> SimulationResult:
    """Validate inputs and run the shared single-build simulation engine."""
    return simulate_build(inputs.build, inputs.scenario, inputs.seed)


def run_comparison_from_inputs(inputs: ComparisonInputs) -> BuildComparisonResult:
    """Validate inputs and run the shared comparison engine."""
    return compare_builds(
        first_build=inputs.first_build,
        second_build=inputs.second_build,
        scenario=inputs.scenario,
        seed=inputs.seed,
    )


def _render_section_container():
    """Return a bordered Streamlit container when available."""
    import streamlit as st

    container = getattr(st, "container", None)
    if container is None:
        return nullcontext()
    try:
        return container(border=True)
    except TypeError:
        return container()


def _round_chart_data(
    result: SimulationResult, build_name: str
) -> list[dict[str, int | float | str]]:
    """Build round-level chart data for one simulation result."""
    return [
        {
            "Round": round_result.round_number,
            "Average total damage": round_result.average_damage,
            "Build": build_name,
        }
        for round_result in result.round_results
    ]


def _comparison_round_chart_data(
    comparison: BuildComparisonResult,
) -> list[dict[str, int | float | str]]:
    """Build round-level chart data for both compared builds."""
    return [
        *_round_chart_data(comparison.first_result, comparison.first_build.name),
        *_round_chart_data(comparison.second_result, comparison.second_build.name),
    ]


def _profile_metadata(
    profile_result: AttackProfileResult, index: int, build_name: str
) -> dict[str, int | float | str]:
    profile = profile_result.attack_profile
    return {
        "Profile": profile.name,
        "Order": index,
        "Build": build_name,
        "Resolution type": profile.resolution_type.value.replace("_", " ").title(),
        "Active Rounds": profile.active_rounds or "Every round",
        "Maximum attacks per active round": profile.attacks_per_round,
        "Attacks per active round": profile.attacks_per_round,
        "Target resolutions": profile.affected_targets,
        "Actual profile uses": profile_result.total_profile_uses,
        "Skipped profile uses": profile_result.total_skipped_profile_uses,
        "Average damage per use": profile_result.average_damage_per_use,
    }


def _profile_contribution_chart_data(
    result: SimulationResult, build_name: str
) -> list[dict[str, int | float | str]]:
    """Build profile contribution chart data in configured attack-profile order."""
    total = result.average_damage_per_round
    rows = []
    for index, profile_result in enumerate(result.attack_profile_results, start=1):
        contribution = profile_result.average_damage_per_round
        rows.append(
            {
                **_profile_metadata(profile_result, index, build_name),
                "Damage per Round contribution": contribution,
                "Contribution percentage": contribution / total * 100 if total else 0,
            }
        )
    return rows


def _profile_damage_per_use_chart_data(
    result: SimulationResult, build_name: str
) -> list[dict[str, int | float | str]]:
    """Build average damage per profile use chart data in configured order."""
    return [
        {
            **_profile_metadata(profile_result, index, build_name),
            "Average damage per use": profile_result.average_damage_per_use,
            "Actual profile uses": profile_result.total_profile_uses,
            "Skipped profile uses": profile_result.total_skipped_profile_uses,
        }
        for index, profile_result in enumerate(result.attack_profile_results, start=1)
    ]


def _line_chart(data, *, x: str, y: str, color: str):
    import altair as alt
    import pandas as pd

    return (
        alt.Chart(pd.DataFrame(data))
        .mark_line(point=True)
        .encode(
            x=alt.X(x, title="Round number", axis=alt.Axis(format="d")),
            y=alt.Y(y, title="Average total damage"),
            color=alt.Color(color, title="Build"),
            tooltip=[
                alt.Tooltip(x, title="Round"),
                alt.Tooltip(y, title="Average damage", format=".2f"),
                alt.Tooltip(color, title="Build"),
            ],
        )
    )


def _profile_contribution_bar_chart(data):
    import altair as alt
    import pandas as pd

    return (
        alt.Chart(pd.DataFrame(data))
        .mark_bar()
        .encode(
            x=alt.X("Profile:N", sort=alt.SortField("Order"), title="Attack profile"),
            y=alt.Y(
                "Damage per Round contribution:Q",
                title="Damage per Round contribution",
            ),
            tooltip=[
                alt.Tooltip("Profile:N", title="Attack name"),
                alt.Tooltip("Resolution type:N", title="Resolution type"),
                alt.Tooltip(
                    "Damage per Round contribution:Q",
                    title="Damage per Round contribution",
                    format=".2f",
                ),
                alt.Tooltip(
                    "Contribution percentage:Q",
                    title="Contribution percentage",
                    format=".1f",
                ),
                alt.Tooltip("Active Rounds:N", title="Active Rounds"),
                alt.Tooltip(
                    "Maximum attacks per active round:Q",
                    title="Maximum attacks per active round",
                ),
                alt.Tooltip("Actual profile uses:Q", title="Actual profile uses"),
                alt.Tooltip("Skipped profile uses:Q", title="Skipped profile uses"),
                alt.Tooltip(
                    "Average damage per use:Q",
                    title="Average damage per use",
                    format=".2f",
                ),
                alt.Tooltip("Target resolutions:Q", title="Target Resolutions"),
            ],
        )
    )


def _profile_damage_per_use_bar_chart(data):
    import altair as alt
    import pandas as pd

    return (
        alt.Chart(pd.DataFrame(data))
        .mark_bar()
        .encode(
            x=alt.X("Profile:N", sort=alt.SortField("Order"), title="Attack profile"),
            y=alt.Y(
                "Average damage per use:Q",
                title="Average total damage from one use",
            ),
            tooltip=[
                alt.Tooltip("Profile:N", title="Attack name"),
                alt.Tooltip("Resolution type:N", title="Resolution type"),
                alt.Tooltip(
                    "Average damage per use:Q",
                    title="Average damage per use",
                    format=".2f",
                ),
                alt.Tooltip("Actual profile uses:Q", title="Actual profile uses"),
                alt.Tooltip("Skipped profile uses:Q", title="Skipped profile uses"),
                alt.Tooltip(
                    "Maximum attacks per active round:Q",
                    title="Maximum attacks per active round",
                ),
                alt.Tooltip("Target resolutions:Q", title="Target Resolutions"),
                alt.Tooltip("Active Rounds:N", title="Active Rounds"),
            ],
        )
    )


def _render_single_build_charts(build: BuildConfig, result: SimulationResult) -> None:
    """Render focused single-build damage charts above detailed result tables."""
    import streamlit as st

    st.markdown("##### Damage per Round")
    st.caption("Average total damage in each round, including zero-damage rounds.")
    st.altair_chart(
        _line_chart(
            _round_chart_data(result, build.name),
            x="Round:O",
            y="Average total damage:Q",
            color="Build:N",
        ),
        width="stretch",
    )

    contribution_data = _profile_contribution_chart_data(result, build.name)
    damage_per_use_data = _profile_damage_per_use_chart_data(result, build.name)
    first_col, second_col = st.columns(2)
    with first_col:
        st.markdown("##### Attack Contribution to Damage per Round")
        st.caption(
            "How much each attack adds to the build's overall average Damage per Round."
        )
        st.altair_chart(
            _profile_contribution_bar_chart(contribution_data), width="stretch"
        )
    with second_col:
        st.markdown("##### Average Damage per Attack Use")
        st.caption(
            "Expected total damage each time the attack is used, including misses, "
            "saves, and all affected targets."
        )
        st.altair_chart(
            _profile_damage_per_use_bar_chart(damage_per_use_data), width="stretch"
        )


def _render_comparison_charts(comparison: BuildComparisonResult) -> None:
    """Render focused comparison charts while keeping profiles separate."""
    import streamlit as st

    st.markdown("##### Damage per Round")
    st.caption("Round-by-round damage for each build on the same round axis.")
    st.altair_chart(
        _line_chart(
            _comparison_round_chart_data(comparison),
            x="Round:O",
            y="Average total damage:Q",
            color="Build:N",
        ),
        width="stretch",
    )

    for build, result in (
        (comparison.first_build, comparison.first_result),
        (comparison.second_build, comparison.second_result),
    ):
        st.markdown(f"##### {build.name}")
        first_col, second_col = st.columns(2)
        with first_col:
            st.markdown("###### Attack Contribution to Damage per Round")
            st.caption(
                "How much each attack adds to the build's overall average "
                "Damage per Round."
            )
            st.altair_chart(
                _profile_contribution_bar_chart(
                    _profile_contribution_chart_data(result, build.name)
                ),
                width="stretch",
            )
        with second_col:
            st.markdown("###### Average Damage per Attack Use")
            st.caption(
                "Expected total damage each time the attack is used, including misses, "
                "saves, and all affected targets."
            )
            st.altair_chart(
                _profile_damage_per_use_bar_chart(
                    _profile_damage_per_use_chart_data(result, build.name)
                ),
                width="stretch",
            )


def _result_difference_column_label(comparison: BuildComparisonResult) -> str:
    """Describe the higher-DPR baseline comparison direction."""
    first_dpr = comparison.first_result.average_damage_per_round
    second_dpr = comparison.second_result.average_damage_per_round
    if second_dpr > first_dpr:
        return (
            "Difference "
            f"({comparison.second_build.name} − {comparison.first_build.name})"
        )
    return (
        f"Difference ({comparison.first_build.name} − {comparison.second_build.name})"
    )


def _result_rows(comparison: BuildComparisonResult) -> list[dict[str, str]]:
    """Build side-by-side display rows for comparison results."""
    first = comparison.first_result
    second = comparison.second_result
    difference_label = _result_difference_column_label(comparison)

    difference = comparison.difference

    def damage_gap(value: float) -> str:
        return format_positive_damage(value)

    def nondamage_gap(first_value: float, second_value: float) -> str:
        return format_positive_compact_decimal(abs(first_value - second_value))

    return [
        {
            "Metric": "Average damage per round",
            comparison.first_build.name: format_damage(first.average_damage_per_round),
            comparison.second_build.name: format_damage(
                second.average_damage_per_round
            ),
            difference_label: damage_gap(difference.average_damage_per_round),
        },
        {
            "Metric": "Average total damage per combat",
            comparison.first_build.name: format_damage(
                first.average_total_damage_per_simulation
            ),
            comparison.second_build.name: format_damage(
                second.average_total_damage_per_simulation
            ),
            difference_label: damage_gap(difference.average_total_damage),
        },
        {
            "Metric": "Expected damage per target resolution",
            comparison.first_build.name: format_damage(
                first.average_damage_per_target_per_round
            ),
            comparison.second_build.name: format_damage(
                second.average_damage_per_target_per_round
            ),
            difference_label: damage_gap(
                difference.average_damage_per_target_per_round
            ),
        },
        {
            "Metric": "Average attack executions per combat",
            comparison.first_build.name: format_compact_decimal(
                _average_attack_executions_per_combat(first)
            ),
            comparison.second_build.name: format_compact_decimal(
                _average_attack_executions_per_combat(second)
            ),
            difference_label: nondamage_gap(
                _average_attack_executions_per_combat(first),
                _average_attack_executions_per_combat(second),
            ),
        },
        {
            "Metric": "Average attack executions per round",
            comparison.first_build.name: format_compact_decimal(
                _average_attack_executions_per_round(first)
            ),
            comparison.second_build.name: format_compact_decimal(
                _average_attack_executions_per_round(second)
            ),
            difference_label: nondamage_gap(
                _average_attack_executions_per_round(first),
                _average_attack_executions_per_round(second),
            ),
        },
        {
            "Metric": "Average damaging target resolutions per combat",
            comparison.first_build.name: format_compact_decimal(
                _average_targets_damaged_per_combat(first)
            ),
            comparison.second_build.name: format_compact_decimal(
                _average_targets_damaged_per_combat(second)
            ),
            difference_label: nondamage_gap(
                _average_targets_damaged_per_combat(first),
                _average_targets_damaged_per_combat(second),
            ),
        },
        {
            "Metric": "Average damaging target resolutions per round",
            comparison.first_build.name: format_compact_decimal(
                _average_targets_damaged_per_round(first)
            ),
            comparison.second_build.name: format_compact_decimal(
                _average_targets_damaged_per_round(second)
            ),
            difference_label: nondamage_gap(
                _average_targets_damaged_per_round(first),
                _average_targets_damaged_per_round(second),
            ),
        },
        {
            "Metric": "Hit percentage",
            comparison.first_build.name: format_rate(first.hit_rate),
            comparison.second_build.name: format_rate(second.hit_rate),
            difference_label: format_positive_rate(difference.hit_rate),
        },
        {
            "Metric": "Critical hit percentage",
            comparison.first_build.name: format_rate(first.critical_hit_rate),
            comparison.second_build.name: format_rate(second.critical_hit_rate),
            difference_label: format_positive_rate(difference.critical_hit_rate),
        },
        {
            "Metric": "Round 1 burst damage",
            comparison.first_build.name: format_damage(first.first_round_burst_damage),
            comparison.second_build.name: format_damage(
                second.first_round_burst_damage
            ),
            difference_label: format_positive_damage(
                abs(first.first_round_burst_damage - second.first_round_burst_damage)
            ),
        },
        {
            "Metric": "Average damage after round 1",
            comparison.first_build.name: format_damage(
                first.average_damage_after_round_1
            ),
            comparison.second_build.name: format_damage(
                second.average_damage_after_round_1
            ),
            difference_label: format_positive_damage(
                abs(
                    first.average_damage_after_round_1
                    - second.average_damage_after_round_1
                )
            ),
        },
        {
            "Metric": "Highest-damage round",
            comparison.first_build.name: str(first.highest_damage_round),
            comparison.second_build.name: str(second.highest_damage_round),
            difference_label: "—",
        },
    ]


def _winner_label(
    first_name: str, first_value: float, second_name: str, second_value: float
) -> str:
    if first_value > second_value:
        return first_name
    if second_value > first_value:
        return second_name
    return "Tie"


def _round_breakdown_rows(comparison: BuildComparisonResult) -> list[dict[str, str]]:
    """Build side-by-side per-round result rows."""
    rows = []
    for first_round, second_round in zip(
        comparison.first_result.round_results,
        comparison.second_result.round_results,
        strict=True,
    ):
        rows.append(
            {
                "Round": str(first_round.round_number),
                f"{comparison.first_build.name} avg total damage": format_damage(
                    first_round.average_damage
                ),
                f"{comparison.second_build.name} avg total damage": format_damage(
                    second_round.average_damage
                ),
                f"{comparison.first_build.name} avg dmg resolutions": format_damage(
                    first_round.average_targets_affected
                ),
                f"{comparison.first_build.name} exp dmg / resolution": format_damage(
                    first_round.average_damage_per_target_resolution
                ),
                f"{comparison.second_build.name} avg dmg resolutions": format_damage(
                    second_round.average_targets_affected
                ),
                f"{comparison.second_build.name} exp dmg / resolution": format_damage(
                    second_round.average_damage_per_target_resolution
                ),
                f"{comparison.first_build.name} crit %": format_rate(
                    first_round.critical_hit_rate
                ),
                f"{comparison.second_build.name} crit %": format_rate(
                    second_round.critical_hit_rate
                ),
            }
        )
    return rows


def _total_simulated_rounds(result: SimulationResult) -> int:
    """Return the number of completed combat rounds represented by a result."""
    return result.simulations_run * result.rounds_per_simulation


def _average_attack_executions_per_combat(result: SimulationResult) -> float:
    """Return average attack profile executions in each completed combat."""
    return result.total_attacks_made / result.simulations_run


def _average_attack_executions_per_round(result: SimulationResult) -> float:
    """Return average attack profile executions in each simulated combat round."""
    return result.total_attacks_made / _total_simulated_rounds(result)


def _average_targets_damaged_per_combat(result: SimulationResult) -> float:
    """Return average damaged targets in each completed combat.

    The simulator counts each damage event's affected targets and does not identify
    whether multiple events damaged the same creature.
    """
    return result.total_targets_affected / result.simulations_run


def _average_targets_damaged_per_round(result: SimulationResult) -> float:
    """Return average damaged targets in each simulated combat round."""
    return result.total_targets_affected / _total_simulated_rounds(result)


def _render_results(result: SimulationResult) -> None:
    """Render simulation results in a compact metric grid."""
    import streamlit as st

    st.subheader("Results")

    first_row = st.columns(4)
    first_row[0].metric(
        "Average total damage per round",
        format_damage(result.average_damage_per_round),
    )
    first_row[1].metric(
        "Average total damage across targets",
        format_damage(result.average_total_damage_per_simulation),
    )
    first_row[2].metric("Attack-roll hit percentage", format_rate(result.hit_rate))
    first_row[3].metric(
        "Attack-roll critical hit percentage", format_rate(result.critical_hit_rate)
    )

    second_row = st.columns(4)
    second_row[0].metric(
        "Average attack executions per combat",
        format_compact_decimal(_average_attack_executions_per_combat(result)),
        help="Average number of attack profile executions in each completed combat.",
    )
    second_row[1].metric(
        "Average attack executions per round",
        format_compact_decimal(_average_attack_executions_per_round(result)),
        help=(
            "Average number of attack profile executions in each simulated "
            "combat round."
        ),
    )
    second_row[2].metric(
        "Average damaging target resolutions per combat",
        format_compact_decimal(_average_targets_damaged_per_combat(result)),
        help=(
            "Average number of targets damaged in each completed combat. "
            "A creature damaged more than once can be counted more than once."
        ),
    )
    second_row[3].metric(
        "Average damaging target resolutions per round",
        format_compact_decimal(_average_targets_damaged_per_round(result)),
        help=(
            "Average number of targets damaged in each simulated combat round. "
            "A creature damaged more than once can be counted more than once."
        ),
    )

    st.caption(f"Attack roll mode: {result.attack_roll_mode.value.title()}")


def _profile_breakdown_rows(result: SimulationResult) -> list[dict[str, str]]:
    """Build per-profile damage breakdown rows."""
    rows = []
    for profile_result in result.attack_profile_results:
        profile = profile_result.attack_profile
        row = {
            "Attack profile": profile.name,
            "Resolution type": profile.resolution_type.value.replace("_", " ").title(),
            "Maximum attacks per active round": str(profile.attacks_per_round),
            "Target resolutions": str(profile.affected_targets),
            "Active Rounds": profile.active_rounds or "Every round",
            "Feats and Features": format_features(profile.features),
            "Average damage per use": format_damage(
                profile_result.average_damage_per_use
            ),
            "Damage per Round contribution": format_damage(
                profile_result.average_damage_per_round
            ),
            "Average damage per target per round": format_damage(
                profile_result.average_damage_per_target_per_round
            ),
            "Average total damage across all affected targets": format_damage(
                profile_result.average_total_damage_per_simulation
            ),
            "Average executions per combat": format_compact_decimal(
                profile_result.average_executions_per_combat
            ),
            "Average executions per round": format_compact_decimal(
                profile_result.average_executions_per_round
            ),
        }
        average_triggered = profile_result.average_triggered_profile_uses_per_simulation
        if profile.trigger_type is TriggerType.ALWAYS:
            row["Trigger"] = "Executes normally each round."
        elif profile.trigger_type is TriggerType.SOMETIMES:
            row["Trigger"] = (
                "Triggered "
                f"{format_compact_decimal(average_triggered)} times per combat "
                f"from a {profile.trigger_chance_percent}% once-per-round chance."
            )
        else:
            source = next(
                (
                    item.attack_profile.name
                    for item in result.attack_profile_results
                    if item.attack_profile.attack_id == profile.trigger_source_attack_id
                ),
                "selected attack",
            )
            outcomes = {
                TriggerType.AFTER_SUCCESS: "hits",
                TriggerType.AFTER_FAILURE: "misses",
                TriggerType.AFTER_CRITICAL: "scores a critical hit",
            }
            row["Trigger"] = (
                "Triggered "
                f"{format_compact_decimal(average_triggered)} times per combat "
                f"after {source} {outcomes[profile.trigger_type]}."
            )
        if profile.resolution_type is ResolutionType.SAVING_THROW:
            row["Failed save percentage"] = format_rate(profile_result.failed_save_rate)
            row["Successful save percentage"] = format_rate(
                profile_result.successful_save_rate
            )
        else:
            row["Hit percentage"] = format_rate(profile_result.hit_rate)
            row["Critical hit percentage"] = format_rate(
                profile_result.critical_hit_rate
            )
        rows.append(row)
    return rows


def _single_result_rows(result: SimulationResult) -> list[dict[str, str]]:
    """Build aggregate rows for a single-build result table."""
    return [
        {
            "Metric": "Average total damage per combat",
            "Value": format_damage(result.average_total_damage_per_simulation),
        },
        {
            "Metric": "Average damage per round",
            "Value": format_damage(result.average_damage_per_round),
        },
        {
            "Metric": "Expected damage per target resolution",
            "Value": format_damage(result.average_damage_per_target_per_round),
            "Details": (
                "A creature damaged by multiple attacks can contribute multiple times."
            ),
        },
        {
            "Metric": "Average attack executions per combat",
            "Value": format_compact_decimal(
                _average_attack_executions_per_combat(result)
            ),
        },
        {
            "Metric": "Average attack executions per round",
            "Value": format_compact_decimal(
                _average_attack_executions_per_round(result)
            ),
        },
        {
            "Metric": "Average damaging target resolutions per combat",
            "Value": format_compact_decimal(
                _average_targets_damaged_per_combat(result)
            ),
            "Details": (
                "A creature damaged by multiple attacks can contribute multiple times."
            ),
        },
        {
            "Metric": "Average damaging target resolutions per round",
            "Value": format_compact_decimal(_average_targets_damaged_per_round(result)),
            "Details": (
                "A creature damaged by multiple attacks can contribute multiple times."
            ),
        },
        {
            "Metric": "Round 1 burst damage",
            "Value": format_damage(result.first_round_burst_damage),
        },
        {
            "Metric": "Average damage after round 1",
            "Value": format_damage(result.average_damage_after_round_1),
        },
        {
            "Metric": "Highest-damage round",
            "Value": (
                f"{result.highest_damage_round} "
                f"({format_damage(result.highest_round_average_damage)})"
            ),
        },
    ]


def _single_round_breakdown_rows(result: SimulationResult) -> list[dict[str, str]]:
    """Build per-round rows for a single-build result."""
    return [
        {
            "Round": str(round_result.round_number),
            "Avg Total Damage": format_damage(round_result.average_damage),
            "Avg Damaging Resolutions": format_damage(
                round_result.average_targets_affected
            ),
            "Expected Damage / Resolution": format_damage(
                round_result.average_damage_per_target_resolution
            ),
            "Hit percentage": format_rate(round_result.hit_rate),
            "Critical hit percentage": format_rate(round_result.critical_hit_rate),
            "Failed save percentage": format_rate(round_result.failed_save_rate),
            "Successful save percentage": format_rate(
                round_result.successful_save_rate
            ),
        }
        for round_result in result.round_results
    ]


def _resource_usage_rows(result: SimulationResult) -> list[dict[str, str]]:
    return [
        {
            "Resource": usage.resource.name,
            "Starting amount": str(usage.resource.starting_value),
            "Avg consumed / combat": format_compact_decimal(
                usage.average_consumed_per_combat
            ),
            "Avg remaining / combat": format_compact_decimal(
                usage.average_remaining_per_combat
            ),
            "Combats Ending at 0": format_rate(usage.ended_at_zero_combat_rate),
            "Average Blocked Executions": format_compact_decimal(
                usage.average_blocked_executions_per_combat
            ),
            "Combats with Blocked Executions": format_rate(
                usage.blocked_execution_combat_rate
            ),
        }
        for usage in result.resource_usage_results
    ]


def _render_resource_usage(result: SimulationResult) -> None:
    import streamlit as st

    rows = _resource_usage_rows(result)
    if rows:
        st.markdown("##### Resource Usage")
        st.table(rows)


def _resource_limited_metric(result: SimulationResult) -> tuple[str, str]:
    return (
        "Blocked executions per combat",
        format_compact_decimal(result.average_resource_blocked_executions_per_combat),
    )


def _render_single_build_results(build: BuildConfig, result: SimulationResult) -> None:
    """Render complete results for one build without comparison labels or deltas."""
    import streamlit as st

    heading = build.name.strip() or "Simulation"
    with _render_section_container():
        st.subheader(f"{heading} results")
        metric_rows = st.columns(5)
        metric_rows[0].metric(
            "Average damage per round", format_damage(result.average_damage_per_round)
        )
        metric_rows[1].metric(
            "Average total damage",
            format_damage(result.average_total_damage_per_simulation),
        )
        metric_rows[2].metric(
            "Round 1 burst", format_damage(result.first_round_burst_damage)
        )
        metric_rows[3].metric(
            "Sustained after round 1",
            format_damage(result.average_damage_after_round_1),
        )
        if result.resource_usage_results:
            label, value = _resource_limited_metric(result)
            metric_rows[4].metric(label, value)
        else:
            metric_rows[4].metric(
                "Highest-damage round",
                (
                    f"{result.highest_damage_round} "
                    f"({format_damage(result.highest_round_average_damage)})"
                ),
            )
        _render_single_build_charts(build, result)
        _render_resource_usage(result)
        with st.expander("Detailed Results", expanded=False):
            st.table(_single_result_rows(result))
            st.markdown("##### Per-round breakdown")
            st.table(_single_round_breakdown_rows(result))
            st.markdown("##### Per-attack-profile breakdown")
            st.table(_profile_breakdown_rows(result))


def _render_comparison_results(comparison: BuildComparisonResult) -> None:
    """Render two build results side by side with deltas."""
    import streamlit as st

    with _render_section_container():
        st.subheader("Build comparison")
        if comparison.higher_average_damage_build_name is None:
            st.success("Both builds have the same average damage per round.")
        else:
            st.success(
                f"{comparison.higher_average_damage_build_name} has higher "
                "average damage."
            )
        first_cols = st.columns(5)
        for cols, build, result in (
            (first_cols, comparison.first_build, comparison.first_result),
            (st.columns(5), comparison.second_build, comparison.second_result),
        ):
            cols[0].metric(
                f"{build.name} avg/round",
                format_damage(result.average_damage_per_round),
            )
            cols[1].metric(
                f"{build.name} total",
                format_damage(result.average_total_damage_per_simulation),
            )
            cols[2].metric(
                f"{build.name} round 1", format_damage(result.first_round_burst_damage)
            )
            cols[3].metric(
                f"{build.name} sustained",
                format_damage(result.average_damage_after_round_1),
            )
            if result.resource_usage_results:
                label, value = _resource_limited_metric(result)
                cols[4].metric(f"{build.name} {label}", value)
            else:
                cols[4].metric(
                    f"{build.name} highest round",
                    (
                        f"{result.highest_damage_round} "
                        f"({format_damage(result.highest_round_average_damage)})"
                    ),
                )
        st.markdown("##### Winners")
        st.write(
            "Round 1 burst: "
            + _winner_label(
                comparison.first_build.name,
                comparison.first_result.first_round_burst_damage,
                comparison.second_build.name,
                comparison.second_result.first_round_burst_damage,
            )
        )
        st.write(
            "Sustained damage after round 1: "
            + _winner_label(
                comparison.first_build.name,
                comparison.first_result.average_damage_after_round_1,
                comparison.second_build.name,
                comparison.second_result.average_damage_after_round_1,
            )
        )
        st.write(
            "Total average damage: "
            + _winner_label(
                comparison.first_build.name,
                comparison.first_result.average_total_damage_per_simulation,
                comparison.second_build.name,
                comparison.second_result.average_total_damage_per_simulation,
            )
        )
        _render_comparison_charts(comparison)
        with st.expander("Detailed Results", expanded=False):
            st.table(_result_rows(comparison))
            st.markdown("##### Per-round damage")
            st.table(_round_breakdown_rows(comparison))
            st.markdown(f"##### {comparison.first_build.name} attack breakdown")
            st.table(_profile_breakdown_rows(comparison.first_result))
            _render_resource_usage(comparison.first_result)
            st.markdown(f"##### {comparison.second_build.name} attack breakdown")
            st.table(_profile_breakdown_rows(comparison.second_result))
            _render_resource_usage(comparison.second_result)
            st.caption(
                f"Difference uses {_result_difference_column_label(comparison)} for "
                "every metric row. Both builds used separate random-number-generator "
                "instances initialized with the same seed."
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
    }.get(state.get(profile_widget_key(prefix, "trigger_type")), TriggerType.ALWAYS)
    resource_costs = ()
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
            state.get(profile_widget_key(prefix, "trigger_frequency")),
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


def trigger_expanded_state_key(profile_id: str) -> str:
    """Return the persistent session key for one trigger editor expansion state."""
    return f"{profile_id}-{TRIGGER_EXPANDED_KEY_SUFFIX}"


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


def managed_resource_widget_key(resource_id: int | str, field: str) -> str:
    return f"scenario-managed-resource-{resource_id}-{field}"


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


def _attack_profile_inputs(
    prefix: str,
    default_name: str,
    errors_by_key: dict[str, str] | None = None,
    *,
    attack_id: str | None = None,
) -> AttackProfile:
    """Render and collect one attack profile's input controls."""
    import streamlit as st

    errors_by_key = errors_by_key or {}
    build_prefix = prefix.split("-", 1)[0]
    domain_attack_id = attack_id or prefix
    attack_name = st.text_input(
        "Attack name", value=default_name, key=profile_widget_key(prefix, "name")
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
    row_one = st.columns(2)
    if resolution_type is ResolutionType.ATTACK_ROLL:
        attack_bonus = row_one[0].number_input(
            "Attack bonus",
            value=5,
            step=1,
            key=profile_widget_key(prefix, "attack_bonus"),
        )
        _field_error(errors_by_key, profile_widget_key(prefix, "attack_bonus"))
        save_dc = None
    elif resolution_type is ResolutionType.SAVING_THROW:
        attack_bonus = None
        save_dc = row_one[0].number_input(
            "Save DC",
            min_value=1,
            value=13,
            step=1,
            key=profile_widget_key(prefix, "save_dc"),
        )
        _field_error(errors_by_key, profile_widget_key(prefix, "save_dc"))
    else:
        attack_bonus = None
        save_dc = None
    damage_dice = row_one[1].text_input(
        "Damage Formula",
        value="1d8+3",
        placeholder=DAMAGE_FORMULA_PLACEHOLDER,
        help=DAMAGE_FORMULA_HELP,
        key=profile_widget_key(prefix, "damage_formula"),
    )
    if not _field_error(errors_by_key, profile_widget_key(prefix, "damage_formula")):
        current_damage_errors = _validate_profile_fields(
            AttackProfile(default_name, 0, damage_dice, 1), prefix=prefix
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
        state.get(profile_widget_key(prefix, "trigger_frequency")),
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
                st.markdown(f"##### {current_name}")
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
                    new_id = _new_attack_id(prefix, profile_index)
                    state = getattr(st, "session_state", {})
                    new_widget_prefix = attack_widget_prefix(prefix, new_id)
                    _duplicate_attack_state(
                        state,
                        _state_widget_prefix(prefix, attack_id),
                        new_widget_prefix,
                    )
                    if (
                        state.get(
                            profile_widget_key(
                                new_widget_prefix, "trigger_source_attack_id"
                            )
                        )
                        == attack_id
                    ):
                        state[profile_widget_key(new_widget_prefix, "trigger_type")] = (
                            "Always"
                        )
                        state[
                            profile_widget_key(
                                new_widget_prefix, "trigger_source_attack_id"
                            )
                        ] = None
                    getattr(st, "session_state", {})[build_attack_ids_key(prefix)] = (
                        ids[: profile_index + 1] + [new_id] + ids[profile_index + 1 :]
                    )
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
                    )
                )

    return _build_config_from_profiles(name, tuple(profiles))


def _resolution_type_label(resolution_type: ResolutionType) -> str:
    return {
        ResolutionType.ATTACK_ROLL: "Attack Roll",
        ResolutionType.SAVING_THROW: "Saving Throw",
        ResolutionType.AUTOMATIC_DAMAGE: "Automatic Damage",
    }[resolution_type]


def _successful_save_damage_label(value: SuccessfulSaveDamage) -> str:
    return "Half damage" if value is SuccessfulSaveDamage.HALF_DAMAGE else "No damage"


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


def share_store_ui_message(error: Exception) -> str:
    """Map share storage exceptions to safe end-user messages."""
    if isinstance(error, ShareNotFoundError):
        return "This shared configuration could not be found."
    if isinstance(error, InvalidShareIdError):
        return "Invalid shared configuration link."
    if isinstance(
        error,
        (ShareStoreError, StoredShareConfigurationError, SharedConfigurationError),
    ):
        return "Shared configurations are temporarily unavailable. Try again later."
    return "Shared configurations are temporarily unavailable. Try again later."


def resolve_shared_query_params(query_params) -> tuple[str, str | None] | None:
    """Return the active share query parameter.

    Short ``?share=`` links take precedence over legacy ``?config=`` links when
    both are present.
    """

    def first_value(name: str) -> str | None:
        value = query_params.get(name) if hasattr(query_params, "get") else None
        if isinstance(value, list):
            value = value[0] if value else None
        return value if isinstance(value, str) and value else None

    share_id = first_value("share")
    if share_id:
        return ("share", share_id)
    token = first_value("config")
    if token:
        return ("config", token)
    return None


def get_supabase_share_store_from_secrets(secrets) -> ShareStore | None:
    """Construct a Supabase share store from Streamlit secrets if configured."""
    supabase_url = secrets.get("SUPABASE_URL") if hasattr(secrets, "get") else None
    supabase_key = secrets.get("SUPABASE_KEY") if hasattr(secrets, "get") else None
    if not supabase_url or not supabase_key:
        return None
    return SupabaseShareStore.from_url_and_key(str(supabase_url), str(supabase_key))


def get_streamlit_share_store() -> ShareStore | None:
    """Return the cached production share store, or ``None`` if unconfigured."""
    import streamlit as st

    cache_resource = getattr(st, "cache_resource", lambda **_: lambda func: func)

    @cache_resource(show_spinner=False)
    def cached_store(supabase_url: str, supabase_key: str) -> ShareStore:
        return SupabaseShareStore.from_url_and_key(supabase_url, supabase_key)

    secrets = getattr(st, "secrets", {})
    supabase_url = secrets.get("SUPABASE_URL") if hasattr(secrets, "get") else None
    supabase_key = secrets.get("SUPABASE_KEY") if hasattr(secrets, "get") else None
    if not supabase_url or not supabase_key:
        return None
    try:
        return cached_store(str(supabase_url), str(supabase_key))
    except Exception:
        return None


def load_configuration_from_share_store(
    share_store: ShareStore, share_id: str
) -> SharedConfiguration:
    return share_store.load(share_id)


def _validation_errors_for_configuration(
    configuration: SharedConfiguration,
) -> list[FieldValidationError]:
    return [
        *validate_scenario_fields(configuration.scenario.to_scenario_config()),
        *validate_build_fields(configuration.build_a.to_build_config(), prefix="first"),
        *validate_build_fields(
            configuration.build_b.to_build_config(), prefix="second"
        ),
    ]


def load_shared_configuration_from_query() -> None:
    """Apply a shared configuration query token once before widgets are created."""
    import streamlit as st

    query_params = getattr(st, "query_params", {})
    resolved = resolve_shared_query_params(query_params)
    if not resolved:
        return
    kind, value = resolved
    if kind == "share":
        if getattr(st, "session_state", {}).get(LOADED_SHARE_ID_KEY) == value:
            return
        share_store = get_streamlit_share_store()
        if share_store is None:
            st.error(
                "Shared configurations are temporarily unavailable. Try again later."
            )
            return
        try:
            configuration = load_configuration_from_share_store(share_store, value)
        except Exception as error:
            st.error(share_store_ui_message(error))
            return
        loaded_key = LOADED_SHARE_ID_KEY
    else:
        if (
            getattr(st, "session_state", {}).get(LOADED_SHARED_CONFIG_TOKEN_KEY)
            == value
        ):
            return
        try:
            configuration = deserialize_shared_configuration(value, validate=False)
        except SharedConfigurationError as error:
            st.error(f"Invalid shared configuration link: {error}")
            return
        loaded_key = LOADED_SHARED_CONFIG_TOKEN_KEY

    hydrate_session_state_from_shared_configuration(st.session_state, configuration)
    validation_errors = _validation_errors_for_configuration(configuration)
    if validation_errors:
        st.session_state[INVALID_SHARED_CONFIG_MESSAGE_KEY] = (
            "Shared configuration loaded with invalid fields. Fix the highlighted "
            "fields before running calculations."
        )
    st.session_state[loaded_key] = value
    st.session_state[LOADED_SHARED_CONFIG_MESSAGE_KEY] = True


def save_shared_configuration(
    share_store: ShareStore, configuration: SharedConfiguration
) -> str:
    return share_store.save(configuration)


def _current_shared_configuration() -> SharedConfiguration:
    import streamlit as st

    session_state = getattr(st, "session_state", {})
    scenario = ScenarioConfig(
        target_armor_class=int(
            session_state.get(SCENARIO_WIDGET_KEYS["target_armor_class"], 15)
        ),
        enemy_save_bonus=int(
            session_state.get(SCENARIO_WIDGET_KEYS["enemy_save_bonus"], 3)
        ),
        rounds=int(session_state.get(SCENARIO_WIDGET_KEYS["rounds"], 4)),
        simulations=int(session_state.get(SCENARIO_WIDGET_KEYS["simulations"], 10_000)),
        managed_resources=_managed_resources_from_state(),
    )
    return shared_configuration_from_configs(
        compare_enabled=bool(session_state.get(COMPARE_WIDGET_KEY, False)),
        scenario=scenario,
        seed=int(session_state.get(SCENARIO_WIDGET_KEYS["seed"], 20240721)),
        build_a=_build_from_state("first", "Build A"),
        build_b=_build_from_state("second", "Build B"),
    )


def _current_short_shared_configuration_url(share_store: ShareStore) -> str:
    import streamlit as st

    share_id = save_shared_configuration(share_store, _current_shared_configuration())
    return build_short_share_url(
        getattr(getattr(st, "context", None), "url", ""), share_id
    )


def _legacy_current_shared_configuration_url() -> str:
    import streamlit as st

    token = serialize_shared_configuration(_current_shared_configuration())
    return build_share_url(getattr(getattr(st, "context", None), "url", ""), token)


def _current_shared_configuration_url() -> str:
    """Build the legacy long configuration URL for backwards-compatible tests."""
    return _legacy_current_shared_configuration_url()


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


def _share_configuration_fingerprint(configuration: SharedConfiguration) -> str:
    return serialize_shared_configuration(configuration)


def _mount_unified_share_component(
    data: dict[str, object], on_create_share_change
) -> object:
    share_toolbar = _get_share_toolbar_component()
    return share_toolbar(
        data=data,
        key="unified-share-configuration",
        on_create_share_change=on_create_share_change,
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


def _render_share_configuration_button() -> None:
    import streamlit as st

    state = getattr(st, "session_state", {})
    base_data: dict[str, object] = {
        "url": "",
        "creating": False,
        "disabled": False,
        "message": state.pop(SHARE_ERROR_MESSAGE_KEY, ""),
    }

    if _configuration_errors_for_current_state():
        state.pop(GENERATED_SHARE_URL_KEY, None)
        state.pop(GENERATED_SHARE_FINGERPRINT_KEY, None)
        base_data.update(
            {"disabled": True, "message": "Fix field errors before sharing."}
        )
        _mount_unified_share_component(base_data, lambda: None)
        return

    share_store = get_streamlit_share_store()
    if share_store is None:
        state.pop(GENERATED_SHARE_URL_KEY, None)
        state.pop(GENERATED_SHARE_FINGERPRINT_KEY, None)
        base_data.update(
            {
                "disabled": True,
                "message": "Share links are not configured for this deployment.",
            }
        )
        _mount_unified_share_component(base_data, lambda: None)
        caption = getattr(st, "caption", None)
        if caption is not None:
            caption("Share links are not configured for this deployment.")
        return

    try:
        configuration = _current_shared_configuration()
        fingerprint = _share_configuration_fingerprint(configuration)
    except SharedConfigurationError:
        state.pop(GENERATED_SHARE_URL_KEY, None)
        state.pop(GENERATED_SHARE_FINGERPRINT_KEY, None)
        base_data.update(
            {"disabled": True, "message": "Fix field errors before sharing."}
        )
        _mount_unified_share_component(base_data, lambda: None)
        return

    stored_fingerprint = state.get(GENERATED_SHARE_FINGERPRINT_KEY)
    if stored_fingerprint is None and state.get(GENERATED_SHARE_URL_KEY):
        state[GENERATED_SHARE_FINGERPRINT_KEY] = fingerprint
    elif stored_fingerprint != fingerprint:
        state.pop(GENERATED_SHARE_URL_KEY, None)
        state[GENERATED_SHARE_FINGERPRINT_KEY] = fingerprint

    share_url = state.get(GENERATED_SHARE_URL_KEY, "")
    base_data["url"] = share_url

    def create_share() -> None:
        try:
            share_id = save_shared_configuration(share_store, configuration)
            state[GENERATED_SHARE_URL_KEY] = build_short_share_url(
                getattr(getattr(st, "context", None), "url", ""), share_id
            )
            state[GENERATED_SHARE_FINGERPRINT_KEY] = fingerprint
            state.pop(SHARE_ERROR_MESSAGE_KEY, None)
        except (SharedConfigurationError, ShareStoreError):
            logger.exception("Failed to create share link from current configuration.")
            state.pop(GENERATED_SHARE_URL_KEY, None)
            state[SHARE_ERROR_MESSAGE_KEY] = (
                "Unable to create a share link right now. Try again later."
            )

    _mount_unified_share_component(base_data, create_share)


def _mark_simulation_pending() -> None:
    """Request one simulation run unless another run is already active."""
    import streamlit as st

    state = getattr(st, "session_state", {})
    if state.get(SIMULATION_RUNNING_KEY):
        return
    state[SIMULATION_PENDING_KEY] = True


def _run_single_build_with_feedback(inputs: SingleBuildInputs) -> SimulationResult:
    """Run a single-build simulation with Streamlit-visible loading feedback."""
    import streamlit as st

    state = getattr(st, "session_state", {})
    state[SIMULATION_RUNNING_KEY] = True
    start = time.perf_counter()
    try:
        with st.spinner("Calculating..."):
            result = run_single_build_from_inputs(inputs)
    except (ValueError, SharedConfigurationError):
        state.pop(SIMULATION_DURATION_MESSAGE_KEY, None)
        raise
    else:
        elapsed = time.perf_counter() - start
        state[SIMULATION_DURATION_MESSAGE_KEY] = (
            f"Simulation complete in {elapsed:.1f} seconds."
        )
        return result
    finally:
        state[SIMULATION_RUNNING_KEY] = False
        state[SIMULATION_PENDING_KEY] = False


def _run_comparison_with_feedback(inputs: ComparisonInputs) -> BuildComparisonResult:
    """Run a build comparison with Streamlit-visible loading feedback."""
    import streamlit as st

    state = getattr(st, "session_state", {})
    state[SIMULATION_RUNNING_KEY] = True
    start = time.perf_counter()
    try:
        with st.spinner("Calculating..."):
            result = run_comparison_from_inputs(inputs)
    except (ValueError, SharedConfigurationError):
        state.pop(SIMULATION_DURATION_MESSAGE_KEY, None)
        raise
    else:
        elapsed = time.perf_counter() - start
        state[SIMULATION_DURATION_MESSAGE_KEY] = (
            f"Simulation complete in {elapsed:.1f} seconds."
        )
        return result
    finally:
        state[SIMULATION_RUNNING_KEY] = False
        state[SIMULATION_PENDING_KEY] = False


def _render_run_simulation_button(disabled: bool) -> bool:
    """Render the shared simulation button for single and comparison workflows."""
    import streamlit as st

    state = getattr(st, "session_state", {})
    simulation_running = bool(state.get(SIMULATION_RUNNING_KEY))
    clicked = st.button(
        "Run Simulation",
        disabled=disabled or simulation_running,
        on_click=_mark_simulation_pending,
    )
    if clicked and not simulation_running and not disabled:
        state[SIMULATION_PENDING_KEY] = True
    return bool(state.get(SIMULATION_PENDING_KEY)) and not disabled


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
