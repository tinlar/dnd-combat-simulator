"""Combat resolution logic independent from the Streamlit interface."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from random import Random

from dnd_combat_simulator.dice import (
    DamageExpression,
    RandomNumberGenerator,
    parse_damage_expression,
    roll_compiled_damage_expression,
)


class AttackRollMode(StrEnum):
    """Available d20 rolling modes for weapon attacks."""

    NORMAL = "normal"
    ADVANTAGE = "advantage"
    DISADVANTAGE = "disadvantage"


class AttackFeature(StrEnum):
    """Optional profile-level feats and features."""

    ELVEN_ACCURACY = "elven_accuracy"
    GREAT_WEAPON_FIGHTING = "great_weapon_fighting"
    TAVERN_BRAWLER = "tavern_brawler"
    STOP_ON_MISS = "stop_on_miss"
    POTENT_CANTRIP = "potent_cantrip"


class ResolutionType(StrEnum):
    """Ways an attack profile can resolve its damage."""

    ATTACK_ROLL = "attack_roll"
    SAVING_THROW = "saving_throw"
    AUTOMATIC_DAMAGE = "automatic_damage"


ATTACK_ROLL_ONLY_FEATURES = frozenset(
    {
        AttackFeature.ELVEN_ACCURACY,
        AttackFeature.GREAT_WEAPON_FIGHTING,
        AttackFeature.TAVERN_BRAWLER,
    }
)


def is_feature_available(
    feature: AttackFeature | str,
    resolution_type: ResolutionType | str,
    *,
    affected_targets: int = 1,
) -> bool:
    """Return whether a feature can be used by a profile shape."""
    selected_feature = AttackFeature(feature)
    selected_resolution_type = ResolutionType(resolution_type)
    if (
        selected_feature in ATTACK_ROLL_ONLY_FEATURES
        and selected_resolution_type is not ResolutionType.ATTACK_ROLL
    ):
        return False
    if (
        selected_feature is AttackFeature.POTENT_CANTRIP
        and selected_resolution_type is ResolutionType.AUTOMATIC_DAMAGE
    ):
        return False
    return not (
        selected_feature is AttackFeature.STOP_ON_MISS
        and (
            selected_resolution_type is not ResolutionType.ATTACK_ROLL
            or affected_targets != 1
        )
    )


def available_features(
    features: frozenset[AttackFeature] | tuple[AttackFeature, ...],
    resolution_type: ResolutionType | str,
    *,
    affected_targets: int = 1,
) -> frozenset[AttackFeature]:
    """Filter features to those available for a profile shape."""
    return frozenset(
        AttackFeature(feature)
        for feature in features
        if is_feature_available(
            feature, resolution_type, affected_targets=affected_targets
        )
    )


def validate_feature_resolution_combination(
    features: frozenset[AttackFeature],
    resolution_type: ResolutionType | str,
    *,
    label: str = "Profile",
    affected_targets: int = 1,
) -> None:
    """Raise a readable error for features unavailable for a profile shape."""
    selected_features = frozenset(AttackFeature(feature) for feature in features)
    selected_resolution_type = ResolutionType(resolution_type)
    for feature in ATTACK_ROLL_ONLY_FEATURES:
        if (
            not is_feature_available(
                feature, selected_resolution_type, affected_targets=affected_targets
            )
            and feature in selected_features
        ):
            feature_label = feature.value.replace("_", " ").title()
            msg = f"{label} {feature_label} requires an Attack Roll resolution type."
            raise ValueError(msg)
    if AttackFeature.POTENT_CANTRIP in selected_features and not is_feature_available(
        AttackFeature.POTENT_CANTRIP,
        selected_resolution_type,
        affected_targets=affected_targets,
    ):
        msg = f"{label} Potent Cantrip cannot be used with Automatic Damage."
        raise ValueError(msg)
    if AttackFeature.STOP_ON_MISS in selected_features and not is_feature_available(
        AttackFeature.STOP_ON_MISS,
        selected_resolution_type,
        affected_targets=affected_targets,
    ):
        msg = (
            f"{label} Stop on Miss requires an Attack Roll profile with "
            "exactly 1 Affected Target."
        )
        raise ValueError(msg)


class SuccessfulSaveDamage(StrEnum):
    """Damage behavior when an enemy succeeds on a saving throw."""

    NO_DAMAGE = "no_damage"
    HALF_DAMAGE = "half_damage"


@dataclass(frozen=True)
class AttackRoll:
    """Natural d20 roll details after applying an attack roll mode."""

    mode: AttackRollMode
    d20_rolls: tuple[int, ...]
    selected_d20_roll: int


@dataclass(frozen=True)
class AttackResult:
    """Outcome of resolving a single weapon attack."""

    attack_roll_mode: AttackRollMode
    natural_d20_roll: int
    d20_rolls: tuple[int, ...]
    modified_attack_total: int
    hit: bool
    critical_hit: bool
    damage_dealt: int


@dataclass(frozen=True)
class AutomaticDamageResult:
    """Outcome of resolving damage that requires no d20 roll."""

    critical_hit: bool
    damage_dealt: int


@dataclass(frozen=True)
class SavingThrowResult:
    """Outcome of resolving a damage profile that requires a saving throw."""

    natural_d20_roll: int
    modified_save_total: int
    save_dc: int
    failed_save: bool
    successful_save: bool
    critical_hit: bool
    damage_dealt: int


@dataclass(frozen=True)
class DamageResolutionResult:
    """Common outcome details for an attack-roll or saving-throw profile."""

    resolution_type: ResolutionType
    damage_dealt: int
    full_damage_success: bool
    critical_hit: bool
    failed_save: bool = False
    successful_save: bool = False
    automatic_damage_application: bool = False


def _roll_attack_d20_fast(
    attack_roll_mode: AttackRollMode,
    *,
    rng: RandomNumberGenerator,
    features: frozenset[AttackFeature] = frozenset(),
) -> AttackRoll:
    """Roll a d20 using already-normalized attack-roll inputs."""
    random_number_generator = rng
    if attack_roll_mode is AttackRollMode.NORMAL:
        rolls = (random_number_generator.randint(1, 20),)
        selected_roll = rolls[0]
    elif attack_roll_mode is AttackRollMode.ADVANTAGE:
        rolls = (
            random_number_generator.randint(1, 20),
            random_number_generator.randint(1, 20),
        )
        if AttackFeature.ELVEN_ACCURACY in features:
            replacement = random_number_generator.randint(1, 20)
            first, second = rolls
            selected_roll = (
                max(first, replacement) if first >= second else max(second, replacement)
            )
            rolls = (*rolls, replacement)
        else:
            selected_roll = max(rolls)
    elif attack_roll_mode is AttackRollMode.DISADVANTAGE:
        rolls = (
            random_number_generator.randint(1, 20),
            random_number_generator.randint(1, 20),
        )
        selected_roll = min(rolls)
    else:
        msg = f"Unsupported attack roll mode: {attack_roll_mode!r}."
        raise ValueError(msg)

    return AttackRoll(
        mode=attack_roll_mode, d20_rolls=rolls, selected_d20_roll=selected_roll
    )


def roll_attack_d20(
    mode: AttackRollMode = AttackRollMode.NORMAL,
    *,
    rng: RandomNumberGenerator | None = None,
    features: frozenset[AttackFeature] = frozenset(),
) -> AttackRoll:
    """Roll one or two d20s and select the die required by the roll mode."""
    random_number_generator = rng if rng is not None else Random()
    return _roll_attack_d20_fast(
        AttackRollMode(mode),
        rng=random_number_generator,
        features=frozenset(AttackFeature(feature) for feature in features),
    )


def _damage_feature_values(features: frozenset[AttackFeature]) -> frozenset[str]:
    return frozenset(feature.value for feature in features)


def _roll_compiled_noncritical_damage(
    *, expression: DamageExpression, rng, damage_features: frozenset[str] = frozenset()
) -> int:
    return roll_compiled_damage_expression(
        expression, rng=rng, features=damage_features
    )


def _roll_noncritical_damage(
    *, damage_dice: str, rng, features: frozenset[AttackFeature] = frozenset()
) -> int:
    return _roll_compiled_noncritical_damage(
        expression=parse_damage_expression(damage_dice),
        rng=rng,
        damage_features=_damage_feature_values(features),
    )


def resolve_compiled_weapon_attack(
    *,
    attack_bonus: int,
    target_armor_class: int,
    damage_expression: DamageExpression,
    attack_roll_mode: AttackRollMode = AttackRollMode.NORMAL,
    rng: RandomNumberGenerator | None = None,
    features: frozenset[AttackFeature] = frozenset(),
    damage_features: frozenset[str] | None = None,
) -> AttackResult:
    """Resolve one attack using a precompiled damage expression."""
    random_number_generator = rng if rng is not None else Random()
    if damage_features is None:
        attack_features = frozenset(AttackFeature(feature) for feature in features)
        feature_values = _damage_feature_values(attack_features)
    else:
        attack_features = features
        feature_values = damage_features
    attack_roll = _roll_attack_d20_fast(
        attack_roll_mode, rng=random_number_generator, features=attack_features
    )
    natural_d20_roll = attack_roll.selected_d20_roll
    modified_attack_total = natural_d20_roll + attack_bonus

    critical_hit = natural_d20_roll == 20
    hit = critical_hit or (
        natural_d20_roll != 1 and modified_attack_total >= target_armor_class
    )

    damage_dealt = 0
    if hit:
        damage_dealt = roll_compiled_damage_expression(
            damage_expression,
            critical=critical_hit,
            rng=random_number_generator,
            features=feature_values,
        )
    elif AttackFeature.POTENT_CANTRIP in attack_features:
        damage_dealt = (
            _roll_compiled_noncritical_damage(
                expression=damage_expression,
                rng=random_number_generator,
                damage_features=feature_values,
            )
            // 2
        )

    return AttackResult(
        attack_roll_mode=attack_roll.mode,
        natural_d20_roll=natural_d20_roll,
        d20_rolls=attack_roll.d20_rolls,
        modified_attack_total=modified_attack_total,
        hit=hit,
        critical_hit=critical_hit,
        damage_dealt=damage_dealt,
    )


def resolve_weapon_attack(
    *,
    attack_bonus: int,
    target_armor_class: int,
    damage_dice: str,
    attack_roll_mode: AttackRollMode = AttackRollMode.NORMAL,
    rng: RandomNumberGenerator | None = None,
    features: frozenset[AttackFeature] = frozenset(),
) -> AttackResult:
    """Resolve one DnD weapon attack."""
    return resolve_compiled_weapon_attack(
        attack_bonus=attack_bonus,
        target_armor_class=target_armor_class,
        damage_expression=parse_damage_expression(damage_dice),
        attack_roll_mode=attack_roll_mode,
        rng=rng,
        features=features,
    )


def resolve_compiled_saving_throw_damage(
    *,
    save_dc: int,
    enemy_save_bonus: int,
    damage_expression: DamageExpression,
    successful_save_damage: SuccessfulSaveDamage = SuccessfulSaveDamage.NO_DAMAGE,
    rng: RandomNumberGenerator | None = None,
    features: frozenset[AttackFeature] = frozenset(),
    damage_features: frozenset[str] | None = None,
) -> SavingThrowResult:
    """Resolve one saving throw using a precompiled damage expression."""
    if save_dc < 1:
        msg = "Save DC must be a positive integer."
        raise ValueError(msg)
    random_number_generator = rng if rng is not None else Random()
    natural_d20_roll = random_number_generator.randint(1, 20)
    modified_save_total = natural_d20_roll + enemy_save_bonus
    successful_save = modified_save_total >= save_dc
    failed_save = not successful_save

    damage_dealt = 0
    if damage_features is None:
        saving_throw_features = frozenset(
            AttackFeature(feature) for feature in features
        )
        feature_values = _damage_feature_values(saving_throw_features)
    else:
        saving_throw_features = features
        feature_values = damage_features
    if (
        failed_save
        or successful_save_damage is SuccessfulSaveDamage.HALF_DAMAGE
        or AttackFeature.POTENT_CANTRIP in saving_throw_features
    ):
        full_damage = _roll_compiled_noncritical_damage(
            expression=damage_expression,
            rng=random_number_generator,
            damage_features=feature_values,
        )
        damage_dealt = full_damage if failed_save else full_damage // 2

    return SavingThrowResult(
        natural_d20_roll=natural_d20_roll,
        modified_save_total=modified_save_total,
        save_dc=save_dc,
        failed_save=failed_save,
        successful_save=successful_save,
        critical_hit=False,
        damage_dealt=max(0, damage_dealt),
    )


def resolve_saving_throw_damage(
    *,
    save_dc: int,
    enemy_save_bonus: int,
    damage_dice: str,
    successful_save_damage: SuccessfulSaveDamage = SuccessfulSaveDamage.NO_DAMAGE,
    rng: RandomNumberGenerator | None = None,
    features: frozenset[AttackFeature] = frozenset(),
) -> SavingThrowResult:
    """Resolve one saving throw based damage event."""
    return resolve_compiled_saving_throw_damage(
        save_dc=save_dc,
        enemy_save_bonus=enemy_save_bonus,
        damage_expression=parse_damage_expression(damage_dice),
        successful_save_damage=successful_save_damage,
        rng=rng,
        features=features,
    )


def resolve_automatic_damage(
    *,
    damage_dice: str,
    rng: RandomNumberGenerator | None = None,
    features: frozenset[AttackFeature] = frozenset(),
) -> AutomaticDamageResult:
    """Resolve one automatic damage application without rolling a d20."""
    random_number_generator = rng if rng is not None else Random()
    damage_dealt = _roll_noncritical_damage(
        damage_dice=damage_dice,
        rng=random_number_generator,
        features=frozenset(AttackFeature(feature) for feature in features),
    )
    return AutomaticDamageResult(critical_hit=False, damage_dealt=damage_dealt)


def resolve_damage_profile(
    *,
    resolution_type: ResolutionType,
    attack_bonus: int | None,
    target_armor_class: int,
    save_dc: int | None,
    enemy_save_bonus: int,
    damage_dice: str,
    attack_roll_mode: AttackRollMode = AttackRollMode.NORMAL,
    successful_save_damage: SuccessfulSaveDamage = SuccessfulSaveDamage.NO_DAMAGE,
    rng: RandomNumberGenerator | None = None,
    features: frozenset[AttackFeature] = frozenset(),
) -> DamageResolutionResult:
    """Resolve profile damage without duplicating simulation loops."""
    damage_features = frozenset(AttackFeature(feature) for feature in features)
    selected_resolution_type = ResolutionType(resolution_type)
    validate_feature_resolution_combination(
        damage_features, selected_resolution_type, label="Profile"
    )
    if selected_resolution_type is ResolutionType.ATTACK_ROLL:
        if attack_bonus is None:
            msg = "Attack Bonus is required for attack-roll profiles."
            raise ValueError(msg)
        attack = resolve_weapon_attack(
            attack_bonus=attack_bonus,
            target_armor_class=target_armor_class,
            damage_dice=damage_dice,
            attack_roll_mode=attack_roll_mode,
            rng=rng,
            features=features,
        )
        return DamageResolutionResult(
            resolution_type=ResolutionType.ATTACK_ROLL,
            damage_dealt=attack.damage_dealt,
            full_damage_success=attack.hit,
            critical_hit=attack.critical_hit,
        )
    if selected_resolution_type is ResolutionType.AUTOMATIC_DAMAGE:
        automatic = resolve_automatic_damage(
            damage_dice=damage_dice, rng=rng, features=features
        )
        return DamageResolutionResult(
            resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            damage_dealt=automatic.damage_dealt,
            full_damage_success=True,
            critical_hit=False,
            automatic_damage_application=True,
        )
    if save_dc is None:
        msg = "Save DC is required for saving-throw profiles."
        raise ValueError(msg)
    save = resolve_saving_throw_damage(
        save_dc=save_dc,
        enemy_save_bonus=enemy_save_bonus,
        damage_dice=damage_dice,
        successful_save_damage=successful_save_damage,
        rng=rng,
        features=features,
    )
    return DamageResolutionResult(
        resolution_type=ResolutionType.SAVING_THROW,
        damage_dealt=save.damage_dealt,
        full_damage_success=save.failed_save,
        critical_hit=False,
        failed_save=save.failed_save,
        successful_save=save.successful_save,
    )
