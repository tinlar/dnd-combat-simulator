from __future__ import annotations

from random import Random

from dnd_combat_simulator.dice import roll_damage_formula


def test_dice_seed_property_is_deterministic() -> None:
    expression = "2d8+3"

    first = roll_damage_formula(expression, rng=Random(123))
    second = roll_damage_formula(expression, rng=Random(123))

    assert first == second
    assert isinstance(first, int)
