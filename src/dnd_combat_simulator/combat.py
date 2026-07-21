"""Combat resolution logic independent from the Streamlit interface."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from random import Random

from dnd_combat_simulator.dice import (
    RandomNumberGenerator,
    parse_dice_notation,
    roll_dice,
)


class AttackRollMode(StrEnum):
    """Available d20 rolling modes for weapon attacks."""

    NORMAL = "normal"
    ADVANTAGE = "advantage"
    DISADVANTAGE = "disadvantage"


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


def roll_attack_d20(
    mode: AttackRollMode = AttackRollMode.NORMAL,
    *,
    rng: RandomNumberGenerator | None = None,
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


def resolve_weapon_attack(
    *,
    attack_bonus: int,
    target_armor_class: int,
    damage_dice: str,
    damage_modifier: int,
    attack_roll_mode: AttackRollMode = AttackRollMode.NORMAL,
    rng: RandomNumberGenerator | None = None,
) -> AttackResult:
    """Resolve one DnD weapon attack.

    Args:
        attack_bonus: Flat modifier added to the selected natural d20 attack roll.
        target_armor_class: Armor Class the attack must meet or exceed to hit.
        damage_dice: Dice expression for weapon damage, such as ``"1d8"``.
        damage_modifier: Flat modifier added once to hit damage.
        attack_roll_mode: Whether attacks roll normally, with advantage, or with
            disadvantage. Natural 1 and 20 rules apply to the selected die.
        rng: Optional random number generator for deterministic tests.

    Returns:
        The roll mode, natural d20 rolls, selected natural d20 roll, modified
        attack total, hit state, critical-hit state, and final non-negative
        damage dealt.

    Raises:
        ValueError: If ``damage_dice`` is not valid dice notation or includes an
            embedded modifier. Pass flat damage through ``damage_modifier``.
    """
    dice = parse_dice_notation(damage_dice)
    if dice.modifier != 0:
        msg = "Damage dice must not include a modifier; use damage_modifier instead."
        raise ValueError(msg)

    random_number_generator = rng if rng is not None else Random()
    attack_roll = roll_attack_d20(attack_roll_mode, rng=random_number_generator)
    natural_d20_roll = attack_roll.selected_d20_roll
    modified_attack_total = natural_d20_roll + attack_bonus

    critical_hit = natural_d20_roll == 20
    hit = critical_hit or (
        natural_d20_roll != 1 and modified_attack_total >= target_armor_class
    )

    damage_dealt = 0
    if hit:
        dice_count = dice.count * (2 if critical_hit else 1)
        damage_roll = roll_dice(
            f"{dice_count}d{dice.sides}", rng=random_number_generator
        )
        damage_dealt = max(0, damage_roll + damage_modifier)

    return AttackResult(
        attack_roll_mode=attack_roll.mode,
        natural_d20_roll=natural_d20_roll,
        d20_rolls=attack_roll.d20_rolls,
        modified_attack_total=modified_attack_total,
        hit=hit,
        critical_hit=critical_hit,
        damage_dealt=damage_dealt,
    )
