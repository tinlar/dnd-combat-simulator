"""Combat resolution logic independent from the Streamlit interface."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from random import Random

from dnd_combat_simulator.dice import RandomNumberGenerator, roll_damage_formula


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


class ResolutionType(StrEnum):
    """Ways an attack profile can resolve its damage."""

    ATTACK_ROLL = "attack_roll"
    SAVING_THROW = "saving_throw"
    AUTOMATIC_DAMAGE = "automatic_damage"


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


def roll_attack_d20(
    mode: AttackRollMode = AttackRollMode.NORMAL,
    *,
    rng: RandomNumberGenerator | None = None,
    features: frozenset[AttackFeature] = frozenset(),
) -> AttackRoll:
    """Roll one or two d20s and select the die required by the roll mode."""
    random_number_generator = rng if rng is not None else Random()
    attack_roll_mode = AttackRollMode(mode)

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
        msg = f"Unsupported attack roll mode: {mode!r}."
        raise ValueError(msg)

    return AttackRoll(
        mode=attack_roll_mode, d20_rolls=rolls, selected_d20_roll=selected_roll
    )


def _roll_noncritical_damage(
    *, damage_dice: str, rng, features: frozenset[AttackFeature] = frozenset()
) -> int:
    return roll_damage_formula(
        damage_dice, rng=rng, features=frozenset(feature.value for feature in features)
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
    random_number_generator = rng if rng is not None else Random()
    attack_features = frozenset(AttackFeature(feature) for feature in features)
    attack_roll = roll_attack_d20(
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
        damage_dealt = roll_damage_formula(
            damage_dice,
            critical=critical_hit,
            rng=random_number_generator,
            features=frozenset(feature.value for feature in attack_features),
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
    if save_dc < 1:
        msg = "Save DC must be a positive integer."
        raise ValueError(msg)
    random_number_generator = rng if rng is not None else Random()
    natural_d20_roll = random_number_generator.randint(1, 20)
    modified_save_total = natural_d20_roll + enemy_save_bonus
    successful_save = modified_save_total >= save_dc
    failed_save = not successful_save

    damage_dealt = 0
    if failed_save or successful_save_damage is SuccessfulSaveDamage.HALF_DAMAGE:
        full_damage = _roll_noncritical_damage(
            damage_dice=damage_dice,
            rng=random_number_generator,
            features=frozenset(AttackFeature(feature) for feature in features),
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
    if (
        AttackFeature.ELVEN_ACCURACY in damage_features
        and selected_resolution_type is not ResolutionType.ATTACK_ROLL
    ):
        msg = "Elven Accuracy requires an Attack Roll resolution type."
        raise ValueError(msg)
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
