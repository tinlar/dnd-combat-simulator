"""Shareable configuration encoding for the Streamlit simulator."""

from __future__ import annotations

import base64
import binascii
import json
import re
import zlib
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit, urlunsplit

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
    ScenarioConfig,
    parse_active_rounds,
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
        }


@dataclass(frozen=True)
class SharedBuildConfiguration:
    name: str
    attack_profiles: tuple[SharedAttackProfileConfiguration, ...]

    @classmethod
    def from_build_config(cls, build: BuildConfig) -> SharedBuildConfiguration:
        return cls(
            build.name,
            tuple(
                SharedAttackProfileConfiguration.from_attack_profile(p)
                for p in build.resolved_attack_profiles()
            ),
        )

    def to_build_config(self) -> BuildConfig:
        profiles = tuple(
            profile.to_attack_profile() for profile in self.attack_profiles
        )
        primary = profiles[0]
        return BuildConfig(
            self.name,
            primary.attack_bonus or 0,
            primary.damage_dice,
            primary.attacks_per_round,
            primary.attack_roll_mode,
            profiles,
        )

    def to_json_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "attack_profiles": [p.to_json_dict() for p in self.attack_profiles],
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
        SharedBuildConfiguration.from_build_config(build_a),
        SharedBuildConfiguration.from_build_config(build_b),
    )


def serialize_shared_configuration(configuration: SharedConfiguration) -> str:
    _validate_shared_configuration(configuration)
    payload = json.dumps(
        configuration.to_json_dict(), sort_keys=True, separators=(",", ":")
    ).encode()
    return base64.urlsafe_b64encode(zlib.compress(payload)).decode().rstrip("=")


def deserialize_shared_configuration(token: str) -> SharedConfiguration:
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
    _validate_shared_configuration(config)
    return config


def build_share_url(base_url: str, token: str) -> str:
    parts = urlsplit(base_url)
    clean_base = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return f"{clean_base}?{urlencode({'config': token})}"


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
    return SharedConfiguration(
        version,
        _expect(obj, "compare_enabled", bool, "Shared configuration"),
        scenario,
        _build_from_json(obj.get("build_a"), "build_a"),
        _build_from_json(obj.get("build_b"), "build_b"),
    )


def _build_from_json(raw: object, name: str) -> SharedBuildConfiguration:
    obj = _required_dict(raw, name)
    profiles_raw = _expect(obj, "attack_profiles", list, name)
    if len(profiles_raw) > MAX_ATTACK_PROFILES_PER_BUILD:
        raise SharedConfigurationError(f"{name} has too many attack profiles.")
    return SharedBuildConfiguration(
        _expect(obj, "name", str, name),
        tuple(
            _profile_from_json(p, f"{name} profile {i}")
            for i, p in enumerate(profiles_raw, 1)
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
        if not build.name.strip() or not build.attack_profiles:
            raise SharedConfigurationError(
                f"{label} must include a name and at least one profile."
            )
        if len(build.attack_profiles) > MAX_ATTACK_PROFILES_PER_BUILD:
            raise SharedConfigurationError(f"{label} has too many attack profiles.")
        for i, profile in enumerate(build.attack_profiles, 1):
            _validate_profile(profile, f"{label} profile {i}")


def _validate_profile(profile: SharedAttackProfileConfiguration, label: str) -> None:
    if not profile.name.strip() or not profile.damage_formula.strip():
        raise SharedConfigurationError(f"{label} has invalid name or Damage Formula.")
    if not isinstance(profile.attack_bonus, int | None) or not isinstance(
        profile.save_dc, int | None
    ):
        raise SharedConfigurationError(f"{label} has invalid numeric fields.")
    if profile.attacks_per_round < 1 or profile.affected_targets < 1:
        raise SharedConfigurationError(f"{label} has invalid attack counts.")
    try:
        roll_damage_formula(profile.damage_formula)
        parse_active_rounds(profile.active_rounds)
        profile.to_attack_profile()
    except ValueError as error:
        raise SharedConfigurationError(f"{label} has invalid data: {error}") from error
    if (
        profile.resolution_type is ResolutionType.ATTACK_ROLL
        and profile.attack_bonus is None
    ):
        raise SharedConfigurationError(f"{label} requires Attack Bonus.")
    if profile.resolution_type is ResolutionType.SAVING_THROW and (
        profile.save_dc is None or profile.save_dc < 1
    ):
        raise SharedConfigurationError(f"{label} requires a positive Save DC.")
    try:
        validate_feature_resolution_combination(
            profile.features, profile.resolution_type, label=label
        )
    except ValueError as error:
        raise SharedConfigurationError(str(error)) from error
    if AttackFeature.STOP_ON_MISS in profile.features and (
        profile.resolution_type is not ResolutionType.ATTACK_ROLL
        or profile.affected_targets != 1
    ):
        raise SharedConfigurationError(f"{label} has invalid Stop on Miss.")
