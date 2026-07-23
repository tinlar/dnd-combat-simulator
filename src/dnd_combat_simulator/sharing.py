"""Shareable configuration encoding for the Streamlit simulator."""

from __future__ import annotations

import base64
import binascii
import json
import re
import zlib
from dataclasses import dataclass, field, replace
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import NAMESPACE_URL, uuid5

from dnd_combat_simulator.build_math import BuildMathDefaults
from dnd_combat_simulator.combat import (
    AttackFeature,
    AttackRollMode,
    ResolutionType,
    SuccessfulSaveDamage,
    validate_feature_resolution_combination,
)
from dnd_combat_simulator.dice import roll_damage_formula
from dnd_combat_simulator.simulation import (
    AttackProfile,
    BuildConfig,
    ManagedResource,
    ResourceCost,
    ScenarioConfig,
    TriggerFrequency,
    TriggerType,
    parse_active_rounds,
    validate_trigger_dependencies,
)

SHARED_CONFIGURATION_VERSION = 1
MAX_ENCODED_TOKEN_LENGTH = 50_000
MAX_DECOMPRESSED_JSON_BYTES = 256 * 1024
MAX_ATTACK_PROFILES_PER_BUILD = 11
FEATURE_SERIALIZATION_ORDER = (
    AttackFeature.ELVEN_ACCURACY,
    AttackFeature.GREAT_WEAPON_FIGHTING,
    AttackFeature.TAVERN_BRAWLER,
    AttackFeature.STOP_ON_MISS,
    AttackFeature.POTENT_CANTRIP,
)


class SharedConfigurationError(ValueError):
    """Raised when a shared configuration cannot be decoded or validated."""


@dataclass(frozen=True)
class SharedAttackProfileConfiguration:
    name: str
    resolution_type: ResolutionType
    attack_bonus: int | None
    save_dc: int | None
    successful_save_damage: SuccessfulSaveDamage
    attack_roll_mode: AttackRollMode
    damage_formula: str
    attacks_per_round: int
    affected_targets: int
    active_rounds: str
    features: frozenset[AttackFeature]
    attack_id: str = ""
    trigger_type: TriggerType = TriggerType.ALWAYS
    trigger_source_attack_id: str | None = None
    trigger_frequency: TriggerFrequency = TriggerFrequency.PER_SUCCESS
    trigger_chance_percent: int | None = None
    resource_costs: tuple[ResourceCost, ...] = ()
    use_build_attack_bonus: bool = False
    use_build_save_dc: bool = False
    inherit_triggering_critical: bool = False
    require_matching_damage_dice_to_continue: bool = False

    @classmethod
    def from_attack_profile(
        cls, profile: AttackProfile
    ) -> SharedAttackProfileConfiguration:
        return cls(
            name=profile.name,
            resolution_type=ResolutionType(profile.resolution_type),
            attack_bonus=profile.attack_bonus,
            save_dc=profile.save_dc,
            successful_save_damage=SuccessfulSaveDamage(profile.successful_save_damage),
            attack_roll_mode=AttackRollMode(profile.attack_roll_mode),
            damage_formula=profile.damage_dice,
            attacks_per_round=profile.attacks_per_round,
            affected_targets=profile.affected_targets,
            active_rounds=profile.active_rounds,
            features=frozenset(AttackFeature(feature) for feature in profile.features),
            attack_id=profile.attack_id,
            trigger_type=TriggerType(profile.trigger_type),
            trigger_source_attack_id=profile.trigger_source_attack_id,
            trigger_frequency=TriggerFrequency(profile.trigger_frequency),
            trigger_chance_percent=profile.trigger_chance_percent,
            resource_costs=profile.resource_costs,
            use_build_attack_bonus=profile.use_build_attack_bonus,
            use_build_save_dc=profile.use_build_save_dc,
            inherit_triggering_critical=profile.inherit_triggering_critical,
            require_matching_damage_dice_to_continue=profile.require_matching_damage_dice_to_continue,
        )

    def to_attack_profile(self) -> AttackProfile:
        return AttackProfile(
            name=self.name,
            attack_bonus=self.attack_bonus,
            damage_dice=self.damage_formula,
            attacks_per_round=self.attacks_per_round,
            affected_targets=self.affected_targets,
            attack_roll_mode=self.attack_roll_mode,
            active_rounds=self.active_rounds,
            resolution_type=self.resolution_type,
            save_dc=self.save_dc,
            successful_save_damage=self.successful_save_damage,
            features=self.features,
            attack_id=self.attack_id,
            trigger_type=self.trigger_type,
            trigger_source_attack_id=self.trigger_source_attack_id,
            trigger_frequency=self.trigger_frequency,
            trigger_chance_percent=self.trigger_chance_percent,
            resource_costs=self.resource_costs,
            use_build_attack_bonus=self.use_build_attack_bonus,
            use_build_save_dc=self.use_build_save_dc,
            inherit_triggering_critical=self.inherit_triggering_critical,
            require_matching_damage_dice_to_continue=self.require_matching_damage_dice_to_continue,
        )

    def to_json_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "resolution_type": self.resolution_type.value,
            "attack_bonus": self.attack_bonus,
            "save_dc": self.save_dc,
            "successful_save_damage": self.successful_save_damage.value,
            "attack_roll_mode": self.attack_roll_mode.value,
            "damage_formula": self.damage_formula,
            "attacks_per_round": self.attacks_per_round,
            "affected_targets": self.affected_targets,
            "active_rounds": self.active_rounds,
            "features": [
                f.value for f in FEATURE_SERIALIZATION_ORDER if f in self.features
            ],
            "attack_id": self.attack_id,
            "trigger_type": self.trigger_type.value,
            "trigger_source_attack_id": self.trigger_source_attack_id,
            "trigger_frequency": self.trigger_frequency.value,
            "trigger_chance_percent": self.trigger_chance_percent,
            "resource_costs": [
                {"resource_id": cost.resource_id, "amount": cost.amount}
                for cost in self.resource_costs
            ],
            "use_build_attack_bonus": self.use_build_attack_bonus,
            "use_build_save_dc": self.use_build_save_dc,
            "inherit_triggering_critical": self.inherit_triggering_critical,
            "require_matching_damage_dice_to_continue": (
                self.require_matching_damage_dice_to_continue
            ),
        }


@dataclass(frozen=True)
class SharedBuildConfiguration:
    name: str
    attack_profiles: tuple[SharedAttackProfileConfiguration, ...]
    math_defaults: BuildMathDefaults = field(default_factory=BuildMathDefaults)
    managed_resources: tuple[SharedManagedResourceConfiguration, ...] = ()

    @classmethod
    def from_build_config(cls, build: BuildConfig) -> SharedBuildConfiguration:
        return cls(
            name=build.name,
            attack_profiles=tuple(
                replace(
                    SharedAttackProfileConfiguration.from_attack_profile(p),
                    attack_id=p.attack_id or f"profile_{index + 1}",
                )
                for index, p in enumerate(build.resolved_attack_profiles())
            ),
            math_defaults=build.math_defaults,
            managed_resources=tuple(
                SharedManagedResourceConfiguration(
                    r.resource_id, r.name, r.starting_value
                )
                for r in build.managed_resources
            ),
        )

    def to_build_config(self) -> BuildConfig:
        profiles = tuple(
            profile.to_attack_profile() for profile in self.attack_profiles
        )
        primary = profiles[0]
        return BuildConfig(
            name=self.name,
            attack_bonus=primary.attack_bonus or 0,
            damage_dice=primary.damage_dice,
            attacks_per_round=primary.attacks_per_round,
            attack_roll_mode=primary.attack_roll_mode,
            attack_profiles=profiles,
            math_defaults=self.math_defaults,
            managed_resources=tuple(
                resource.to_managed_resource() for resource in self.managed_resources
            ),
        )

    def to_json_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "attack_profiles": [p.to_json_dict() for p in self.attack_profiles],
            "math_defaults": _build_math_defaults_to_json_dict(self.math_defaults),
            "managed_resources": [
                resource.to_json_dict() for resource in self.managed_resources
            ],
        }


@dataclass(frozen=True)
class SharedManagedResourceConfiguration:
    resource_id: str
    name: str
    starting_value: int

    def to_managed_resource(self) -> ManagedResource:
        return ManagedResource(self.resource_id, self.name, self.starting_value)

    def to_json_dict(self) -> dict[str, object]:
        return {
            "resource_id": self.resource_id,
            "name": self.name,
            "starting_value": self.starting_value,
        }


@dataclass(frozen=True)
class SharedScenarioConfiguration:
    target_armor_class: int
    enemy_save_bonus: int
    rounds: int
    simulations: int
    seed: int

    def to_scenario_config(self) -> ScenarioConfig:
        return ScenarioConfig(
            self.target_armor_class,
            self.rounds,
            self.simulations,
            self.enemy_save_bonus,
        )

    def to_json_dict(self) -> dict[str, int]:
        return {
            "target_armor_class": self.target_armor_class,
            "enemy_save_bonus": self.enemy_save_bonus,
            "rounds": self.rounds,
            "simulations": self.simulations,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class SharedConfiguration:
    version: int
    compare_enabled: bool
    scenario: SharedScenarioConfiguration
    build_a: SharedBuildConfiguration
    build_b: SharedBuildConfiguration

    def to_json_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "compare_enabled": self.compare_enabled,
            "scenario": self.scenario.to_json_dict(),
            "build_a": self.build_a.to_json_dict(),
            "build_b": self.build_b.to_json_dict(),
        }


def shared_configuration_from_configs(
    *,
    compare_enabled: bool,
    scenario: ScenarioConfig,
    seed: int,
    build_a: BuildConfig,
    build_b: BuildConfig,
) -> SharedConfiguration:
    return SharedConfiguration(
        SHARED_CONFIGURATION_VERSION,
        compare_enabled,
        SharedScenarioConfiguration(
            scenario.target_armor_class,
            scenario.enemy_save_bonus,
            scenario.rounds,
            scenario.simulations,
            seed,
        ),
        SharedBuildConfiguration.from_build_config(
            build_a
            if build_a.managed_resources
            else replace(build_a, managed_resources=scenario.managed_resources)
        ),
        SharedBuildConfiguration.from_build_config(
            build_b
            if build_b.managed_resources
            else replace(build_b, managed_resources=scenario.managed_resources)
        ),
    )


def _is_legacy_positional_attack_id(value: str) -> bool:
    return (
        not value.strip()
        or value.startswith("first-primary")
        or value.startswith("first-additional-")
        or value.startswith("second-primary")
        or value.startswith("second-additional-")
        or value.startswith("profile-")
    )


def _migrated_attack_id(
    build_prefix: str, index: int, profile: SharedAttackProfileConfiguration
) -> str:
    seed = (
        f"tinlar/dnd-combat-simulator/{build_prefix}/{index}/"
        f"{profile.name}/{profile.damage_formula}"
    )
    return f"attack-{uuid5(NAMESPACE_URL, seed).hex}"


def migrate_shared_build_attack_ids(
    build_prefix: str, shared_build: SharedBuildConfiguration
) -> SharedBuildConfiguration:
    profiles = shared_build.attack_profiles
    used: set[str] = set()
    migrated_ids: list[str] = []
    legacy_to_stable: dict[str, str] = {}
    for index, profile in enumerate(profiles):
        raw_id = (profile.attack_id or "").strip()
        candidate = raw_id
        if _is_legacy_positional_attack_id(raw_id) or candidate in used:
            candidate = _migrated_attack_id(build_prefix, index, profile)
            suffix = 1
            while candidate in used:
                candidate = (
                    f"{_migrated_attack_id(build_prefix, index, profile)}-{suffix}"
                )
                suffix += 1
        used.add(candidate)
        migrated_ids.append(candidate)
        if raw_id:
            legacy_to_stable[raw_id] = candidate
        legacy_to_stable[str(index)] = candidate
        legacy_to_stable[f"profile-{index + 1}"] = candidate
    names: dict[str, list[str]] = {}
    for profile, stable_id in zip(profiles, migrated_ids, strict=True):
        names.setdefault(profile.name, []).append(stable_id)
    migrated = []
    for index, profile in enumerate(profiles):
        source_id = profile.trigger_source_attack_id
        if source_id in legacy_to_stable:
            source_id = legacy_to_stable[source_id or ""]
        elif source_id in names:
            matches = names[source_id]
            if len(matches) != 1:
                raise SharedConfigurationError(
                    f"{build_prefix} profile {index + 1} trigger source "
                    "name is ambiguous."
                )
            source_id = matches[0]
        elif (
            profile.trigger_type not in (TriggerType.ALWAYS, TriggerType.SOMETIMES)
            and source_id
        ):
            try:
                legacy_index = int(source_id)
            except (TypeError, ValueError):
                pass
            else:
                if legacy_index < 0 or legacy_index >= len(profiles):
                    raise SharedConfigurationError(
                        f"{build_prefix} profile {index + 1} trigger source "
                        "index is invalid."
                    )
        migrated.append(
            replace(
                profile,
                attack_id=migrated_ids[index],
                trigger_source_attack_id=source_id,
            )
        )
    return replace(shared_build, attack_profiles=tuple(migrated))


def serialize_shared_configuration(configuration: SharedConfiguration) -> str:
    _validate_shared_configuration(configuration)
    payload = json.dumps(
        configuration.to_json_dict(), sort_keys=True, separators=(",", ":")
    ).encode()
    return base64.urlsafe_b64encode(zlib.compress(payload)).decode().rstrip("=")


def deserialize_shared_configuration(
    token: str, *, validate: bool = True
) -> SharedConfiguration:
    if not isinstance(token, str) or not token:
        raise SharedConfigurationError("Shared configuration token is required.")
    if len(token) > MAX_ENCODED_TOKEN_LENGTH:
        raise SharedConfigurationError("Shared configuration token is too large.")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        raise SharedConfigurationError(
            "Shared configuration is not valid URL-safe Base64."
        )
    try:
        compressed = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    except (binascii.Error, ValueError) as error:
        raise SharedConfigurationError(
            "Shared configuration is not valid URL-safe Base64."
        ) from error
    try:
        decompressor = zlib.decompressobj()
        data = decompressor.decompress(compressed, MAX_DECOMPRESSED_JSON_BYTES + 1)
        remaining = MAX_DECOMPRESSED_JSON_BYTES + 1 - len(data)
        if remaining > 0:
            data += decompressor.flush(remaining)
    except zlib.error as error:
        raise SharedConfigurationError(
            "Shared configuration is not valid compressed data."
        ) from error
    if len(data) > MAX_DECOMPRESSED_JSON_BYTES or (not decompressor.eof and data):
        raise SharedConfigurationError("Shared configuration JSON is too large.")
    try:
        raw = json.loads(data.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise SharedConfigurationError(
            "Shared configuration is not valid UTF-8."
        ) from error
    except json.JSONDecodeError as error:
        raise SharedConfigurationError(
            "Shared configuration is not valid JSON."
        ) from error
    config = _configuration_from_json(raw)
    if validate:
        _validate_shared_configuration(config)
    return config


def build_share_url(base_url: str, token: str) -> str:
    parts = urlsplit(base_url)
    clean_base = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return f"{clean_base}?{urlencode({'config': token})}"


def build_short_share_url(base_url: str, share_id: str) -> str:
    """Build a short share URL, preserving origin/path and dropping old query params."""
    parts = urlsplit(base_url)
    clean_base = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return f"{clean_base}?{urlencode({'share': share_id})}"


def _required_dict(raw: object, name: str) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise SharedConfigurationError(f"{name} must be an object.")
    return raw


def _expect(raw: dict[str, object], key: str, typ: type, ctx: str):
    if key not in raw:
        raise SharedConfigurationError(f"{ctx} is missing required field {key}.")
    value = raw[key]
    if not isinstance(value, typ) or (typ is int and isinstance(value, bool)):
        raise SharedConfigurationError(f"{ctx} field {key} has the wrong type.")
    return value


def _build_math_defaults_to_json_dict(defaults: BuildMathDefaults) -> dict[str, int]:
    return {
        "ability_modifier": defaults.ability_modifier,
        "proficiency_bonus": defaults.proficiency_bonus,
        "attack_bonus_adjustment": defaults.attack_bonus_adjustment,
        "save_dc_adjustment": defaults.save_dc_adjustment,
    }


def _build_math_defaults_from_json(raw: object, ctx: str) -> BuildMathDefaults:
    obj = _required_dict(raw, f"{ctx} math_defaults")
    values = {}
    for field_name in (
        "ability_modifier",
        "proficiency_bonus",
        "attack_bonus_adjustment",
        "save_dc_adjustment",
    ):
        value = _expect(obj, field_name, int, f"{ctx} math_defaults")
        values[field_name] = value
    try:
        return BuildMathDefaults(**values)
    except ValueError as error:
        raise SharedConfigurationError(f"{ctx} math_defaults: {error}") from error


def _append_legacy_damage_modifier(formula: str, modifier: int) -> str:
    formula = formula.strip()
    if modifier > 0:
        return f"{formula}+{modifier}"
    if modifier < 0:
        return f"{formula}{modifier}"
    return formula


def _configuration_from_json(raw: object) -> SharedConfiguration:
    obj = _required_dict(raw, "Shared configuration")
    version = _expect(obj, "version", int, "Shared configuration")
    if version != SHARED_CONFIGURATION_VERSION:
        raise SharedConfigurationError(
            f"Unsupported shared configuration version: {version}."
        )
    scenario_raw = _required_dict(obj.get("scenario"), "scenario")
    scenario = SharedScenarioConfiguration(
        _expect(scenario_raw, "target_armor_class", int, "scenario"),
        _expect(scenario_raw, "enemy_save_bonus", int, "scenario"),
        _expect(scenario_raw, "rounds", int, "scenario"),
        _expect(scenario_raw, "simulations", int, "scenario"),
        _expect(scenario_raw, "seed", int, "scenario"),
    )
    build_a = _build_from_json(obj.get("build_a"), "build_a")
    build_b = _build_from_json(obj.get("build_b"), "build_b")
    legacy_resources = tuple(
        _resource_from_json(resource, f"scenario managed resource {i}")
        for i, resource in enumerate(scenario_raw.get("managed_resources", []), 1)
    )
    if legacy_resources:
        if not build_a.managed_resources:
            build_a = replace(build_a, managed_resources=legacy_resources)
        if not build_b.managed_resources:
            build_b = replace(build_b, managed_resources=legacy_resources)
    return SharedConfiguration(
        version,
        _expect(obj, "compare_enabled", bool, "Shared configuration"),
        scenario,
        build_a,
        build_b,
    )


def _build_from_json(raw: object, name: str) -> SharedBuildConfiguration:
    obj = _required_dict(raw, name)
    profiles_raw = _expect(obj, "attack_profiles", list, name)
    if len(profiles_raw) > MAX_ATTACK_PROFILES_PER_BUILD:
        raise SharedConfigurationError(f"{name} has too many attack profiles.")
    raw_profile_objects = [
        _required_dict(p, f"{name} profile {i}") for i, p in enumerate(profiles_raw, 1)
    ]
    legacy_damage_modifier = 0
    math_defaults = (
        BuildMathDefaults()
        if "math_defaults" not in obj
        else _build_math_defaults_from_json(obj["math_defaults"], name)
    )
    if "math_defaults" in obj and isinstance(obj["math_defaults"], dict):
        md = obj["math_defaults"]
        if isinstance(md.get("damage_bonus_adjustment"), int) and not isinstance(
            md.get("damage_bonus_adjustment"), bool
        ):
            legacy_damage_modifier = (
                math_defaults.ability_modifier + md["damage_bonus_adjustment"]
            )
    profiles = tuple(
        _profile_from_json(p, f"{name} profile {i}")
        for i, p in enumerate(profiles_raw, 1)
    )
    needs_generated_ids = any(
        profile.trigger_type is not TriggerType.ALWAYS for profile in profiles
    ) and any(not profile.attack_id for profile in profiles)
    if needs_generated_ids:
        profiles = tuple(
            replace(profile, attack_id=profile.attack_id or f"profile-{i}")
            for i, profile in enumerate(profiles, 1)
        )
    ids = {profile.attack_id for profile in profiles}
    names = [profile.name for profile in profiles]
    migrated = []
    for index, profile in enumerate(profiles):
        raw_profile = raw_profile_objects[index]
        source_id = profile.trigger_source_attack_id
        if profile.trigger_type is not TriggerType.ALWAYS and (
            not source_id or source_id not in ids
        ):
            legacy_index = raw_profile.get("trigger_source_attack_index")
            legacy_name = raw_profile.get("trigger_source_attack_name")
            if isinstance(legacy_index, int) and 0 <= legacy_index < len(profiles):
                source_id = profiles[legacy_index].attack_id
            elif isinstance(legacy_name, str) and names.count(legacy_name) == 1:
                source_id = profiles[names.index(legacy_name)].attack_id
        if raw_profile.get("use_build_damage_modifier") is True:
            profile = replace(
                profile,
                damage_formula=_append_legacy_damage_modifier(
                    profile.damage_formula, legacy_damage_modifier
                ),
            )
        migrated.append(replace(profile, trigger_source_attack_id=source_id))
    return migrate_shared_build_attack_ids(
        name,
        SharedBuildConfiguration(
            name=_expect(obj, "name", str, name),
            attack_profiles=tuple(migrated),
            math_defaults=math_defaults,
            managed_resources=tuple(
                _resource_from_json(resource, f"{name} managed resource {i}")
                for i, resource in enumerate(obj.get("managed_resources", []), 1)
            ),
        ),
    )


def _enum(enum_type, value: object, ctx: str):
    if not isinstance(value, str):
        raise SharedConfigurationError(f"{ctx} enum value has the wrong type.")
    try:
        return enum_type(value)
    except ValueError as error:
        raise SharedConfigurationError(
            f"{ctx} has an invalid enum value: {value}."
        ) from error


def _optional_bool(obj: dict[str, object], key: str, ctx: str) -> bool:
    if key not in obj:
        return False
    value = obj[key]
    if type(value) is not bool:
        raise SharedConfigurationError(f"{ctx}.{key} must be a boolean.")
    return value


def _profile_from_json(raw: object, ctx: str) -> SharedAttackProfileConfiguration:
    obj = _required_dict(raw, ctx)
    features_raw = _expect(obj, "features", list, ctx)
    features = []
    for feature in features_raw:
        features.append(_enum(AttackFeature, feature, ctx))
    return SharedAttackProfileConfiguration(
        _expect(obj, "name", str, ctx),
        _enum(ResolutionType, obj.get("resolution_type"), ctx),
        obj.get("attack_bonus"),
        obj.get("save_dc"),
        _enum(SuccessfulSaveDamage, obj.get("successful_save_damage"), ctx),
        _enum(AttackRollMode, obj.get("attack_roll_mode"), ctx),
        _expect(obj, "damage_formula", str, ctx),
        _expect(obj, "attacks_per_round", int, ctx),
        _expect(obj, "affected_targets", int, ctx),
        _expect(obj, "active_rounds", str, ctx),
        frozenset(features),
        obj.get("attack_id", ""),
        _enum(TriggerType, obj.get("trigger_type", TriggerType.ALWAYS.value), ctx),
        obj.get("trigger_source_attack_id"),
        _enum(
            TriggerFrequency,
            obj.get("trigger_frequency", TriggerFrequency.PER_SUCCESS.value),
            ctx,
        ),
        obj.get("trigger_chance_percent"),
        tuple(
            _resource_cost_from_json(cost, f"{ctx} resource cost {i}")
            for i, cost in enumerate(obj.get("resource_costs", []), 1)
        ),
        _optional_bool(obj, "use_build_attack_bonus", ctx),
        _optional_bool(obj, "use_build_save_dc", ctx),
        _optional_bool(obj, "inherit_triggering_critical", ctx),
        _optional_bool(obj, "require_matching_damage_dice_to_continue", ctx),
    )


def _resource_from_json(raw: object, ctx: str) -> SharedManagedResourceConfiguration:
    obj = _required_dict(raw, ctx)
    return SharedManagedResourceConfiguration(
        _expect(obj, "resource_id", str, ctx),
        _expect(obj, "name", str, ctx),
        _expect(obj, "starting_value", int, ctx),
    )


def _resource_cost_from_json(raw: object, ctx: str) -> ResourceCost:
    obj = _required_dict(raw, ctx)
    return ResourceCost(
        _expect(obj, "resource_id", str, ctx),
        _expect(obj, "amount", int, ctx),
    )


def _validate_shared_configuration(config: SharedConfiguration) -> None:
    if config.version != SHARED_CONFIGURATION_VERSION:
        raise SharedConfigurationError(
            f"Unsupported shared configuration version: {config.version}."
        )
    scenario = config.scenario
    if (
        scenario.target_armor_class < 1
        or scenario.rounds < 1
        or scenario.simulations < 1
    ):
        raise SharedConfigurationError("Shared scenario contains invalid values.")
    for label, build in (("Build A", config.build_a), ("Build B", config.build_b)):
        resource_ids = {resource.resource_id for resource in build.managed_resources}
        if any(
            not resource.resource_id.strip()
            or not resource.name.strip()
            or resource.starting_value < 0
            for resource in build.managed_resources
        ):
            raise SharedConfigurationError(
                f"{label} contains invalid managed resources."
            )
        if len(resource_ids) != len(build.managed_resources):
            raise SharedConfigurationError(
                f"{label} managed resource IDs must be unique."
            )
        if not build.name.strip() or not build.attack_profiles:
            raise SharedConfigurationError(
                f"{label} must include a name and at least one profile."
            )
        if len(build.attack_profiles) > MAX_ATTACK_PROFILES_PER_BUILD:
            raise SharedConfigurationError(f"{label} has too many attack profiles.")
        attack_ids = [profile.attack_id for profile in build.attack_profiles]
        if any(not attack_id.strip() for attack_id in attack_ids):
            raise SharedConfigurationError(
                f"{label} contains an attack with an empty ID."
            )
        if len(set(attack_ids)) != len(attack_ids):
            raise SharedConfigurationError(f"{label} contains duplicate attack IDs.")
        for i, profile in enumerate(build.attack_profiles, 1):
            _validate_profile(profile, f"{label} profile {i}", resource_ids)
        try:
            validate_trigger_dependencies(
                tuple(profile.to_attack_profile() for profile in build.attack_profiles),
                label=label,
            )
        except ValueError as error:
            raise SharedConfigurationError(str(error)) from error


def _validate_profile(
    profile: SharedAttackProfileConfiguration,
    label: str,
    resource_ids: set[str] | None = None,
) -> None:
    if not profile.name.strip() or not profile.damage_formula.strip():
        raise SharedConfigurationError(f"{label} has invalid name or Damage Formula.")
    if not isinstance(profile.attack_bonus, int | None) or not isinstance(
        profile.save_dc, int | None
    ):
        raise SharedConfigurationError(f"{label} has invalid numeric fields.")
    for field_name in (
        "use_build_attack_bonus",
        "use_build_save_dc",
    ):
        if type(getattr(profile, field_name)) is not bool:
            raise SharedConfigurationError(f"{label} has invalid inheritance fields.")
    if profile.attacks_per_round < 1 or profile.affected_targets < 1:
        raise SharedConfigurationError(f"{label} has invalid attack counts.")
    if profile.trigger_type is TriggerType.SOMETIMES and (
        not isinstance(profile.trigger_chance_percent, int)
        or profile.trigger_chance_percent < 1
        or profile.trigger_chance_percent > 100
    ):
        raise SharedConfigurationError(
            f"{label} Sometimes percentage chance must be a whole number "
            "from 1 through 100."
        )
    resource_ids = resource_ids or set()
    for cost in profile.resource_costs:
        if cost.resource_id not in resource_ids or cost.amount < 1:
            raise SharedConfigurationError(f"{label} has invalid resource costs.")
    try:
        roll_damage_formula(profile.damage_formula)
        parse_active_rounds(profile.active_rounds)
        profile.to_attack_profile()
    except ValueError as error:
        raise SharedConfigurationError(f"{label} has invalid data: {error}") from error
    if (
        profile.resolution_type is ResolutionType.ATTACK_ROLL
        and not profile.use_build_attack_bonus
        and profile.attack_bonus is None
    ):
        raise SharedConfigurationError(f"{label} requires Attack Bonus.")
    if (
        profile.resolution_type is ResolutionType.SAVING_THROW
        and not profile.use_build_save_dc
        and (profile.save_dc is None or profile.save_dc < 1)
    ):
        raise SharedConfigurationError(f"{label} requires a positive Save DC.")
    try:
        validate_feature_resolution_combination(
            profile.features,
            profile.resolution_type,
            label=label,
            affected_targets=profile.affected_targets,
        )
    except ValueError as error:
        raise SharedConfigurationError(str(error)) from error
