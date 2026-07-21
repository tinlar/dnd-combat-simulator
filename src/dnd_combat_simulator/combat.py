"""Combat resolution logic independent from the Streamlit interface."""

from __future__ import annotations

from dataclasses import dataclass
from random import Random

from dnd_combat_simulator.dice import (
    RandomNumberGenerator,
    parse_dice_notation,
    roll_dice,
)


@dataclass(frozen=True)
class AttackResult:
    """Outcome of resolving a single weapon attack."""

    natural_d20_roll: int
    modified_attack_total: int
    hit: bool
    critical_hit: bool
    damage_dealt: int


def resolve_weapon_attack(
    *,
    attack_bonus: int,
    target_armor_class: int,
    damage_dice: str,
    damage_modifier: int,
    rng: RandomNumberGenerator | None = None,
) -> AttackResult:
    """Resolve one DnD weapon attack.

    Args:
        attack_bonus: Flat modifier added to the natural d20 attack roll.
        target_armor_class: Armor Class the attack must meet or exceed to hit.
        damage_dice: Dice expression for weapon damage, such as ``"1d8"``.
        damage_modifier: Flat modifier added once to hit damage.
        rng: Optional random number generator for deterministic tests.

    Returns:
        The natural d20 roll, modified attack total, hit state, critical-hit
        state, and final non-negative damage dealt.

    Raises:
        ValueError: If ``damage_dice`` is not valid dice notation or includes an
            embedded modifier. Pass flat damage through ``damage_modifier``.
    """
    dice = parse_dice_notation(damage_dice)
    if dice.modifier != 0:
        msg = "Damage dice must not include a modifier; use damage_modifier instead."
        raise ValueError(msg)

    random_number_generator = rng if rng is not None else Random()
    natural_d20_roll = random_number_generator.randint(1, 20)
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
        natural_d20_roll=natural_d20_roll,
        modified_attack_total=modified_attack_total,
        hit=hit,
        critical_hit=critical_hit,
        damage_dealt=damage_dealt,
    )
