# ruff: noqa
"""Focused Streamlit UI helpers."""

from __future__ import annotations

from dnd_combat_simulator.ui._shared import *  # noqa: F403
from dnd_combat_simulator.ui.constants import *  # noqa: F403
from dnd_combat_simulator.ui.widget_keys import *  # noqa: F403
from dnd_combat_simulator.ui.state import (
    _attack_ids_from_state,
    _managed_resource_ids_from_state,
)


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
    if any(not attack_id.strip() for attack_id in profile_ids):
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
