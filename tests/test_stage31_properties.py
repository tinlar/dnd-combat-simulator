from __future__ import annotations

from random import Random

from hypothesis import given, settings
from hypothesis import strategies as st

from dnd_combat_simulator.dice import roll_damage
from dnd_combat_simulator.simulation import AttackProfile, BuildConfig, ScenarioConfig
from dnd_combat_simulator.ui.run_control import (
    SingleBuildInputs,
    canonical_single_build_request,
)
from dnd_combat_simulator.ui.widget_keys import attack_widget_prefix


@settings(max_examples=20, deadline=None)
@given(st.lists(st.text(min_size=1, max_size=8), min_size=1, max_size=5, unique=True))
def test_attack_order_property_preserves_ids(ids: list[str]) -> None:
    profiles = tuple(
        AttackProfile(
            name=i, attack_bonus=5, damage_dice="1d4", attacks_per_round=1, attack_id=i
        )
        for i in ids
    )
    reordered = tuple(reversed(profiles))
    assert {p.attack_id for p in profiles} == {p.attack_id for p in reordered}
    assert attack_widget_prefix("first", ids[0]) != attack_widget_prefix(
        "second", ids[0]
    )


@settings(max_examples=20, deadline=None)
@given(st.integers(min_value=1, max_value=20), st.integers(min_value=1, max_value=6))
def test_dice_seed_property_is_deterministic(sides: int, bonus: int) -> None:
    expression = f"1d{sides}+{bonus}"
    assert (
        roll_damage(expression, Random(123)).total
        == roll_damage(expression, Random(123)).total
    )


def test_sharing_canonical_request_generation_is_deterministic() -> None:
    build = BuildConfig(
        "A",
        5,
        "1d4",
        1,
        attack_profiles=(AttackProfile("A", 5, "1d4", 1, attack_id="a"),),
    )
    scenario = ScenarioConfig(15, 1, 2)
    inputs = SingleBuildInputs(build, scenario, 1)
    assert canonical_single_build_request(inputs) == canonical_single_build_request(
        inputs
    )
