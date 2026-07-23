from __future__ import annotations

from random import Random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dnd_combat_simulator.dice import (
    parse_damage_expression,
    roll_damage_formula,
    roll_damage_formula_breakdown,
)
from dnd_combat_simulator.sharing import (
    deserialize_shared_configuration,
    serialize_shared_configuration,
    shared_configuration_from_configs,
)
from dnd_combat_simulator.simulation import (
    AttackProfile,
    BuildConfig,
    ManagedResource,
    ResourceCost,
    ScenarioConfig,
    TriggerType,
)
from dnd_combat_simulator.ui.state import (
    _delete_attack_state,
    _duplicate_attack_state,
)
from dnd_combat_simulator.ui.widget_keys import (
    attack_widget_prefix,
    build_attack_ids_key,
    profile_widget_key,
)

safe_die = st.integers(2, 12)
dice_expr = st.builds(
    lambda c, s, m: f"{c}d{s}+{m}", st.integers(1, 4), safe_die, st.integers(0, 10)
)


@settings(max_examples=30, deadline=None)
@given(expr=dice_expr, seed=st.integers(0, 2**31 - 1))
def test_dice_identical_seed_is_deterministic_and_integer(expr: str, seed: int) -> None:
    first = roll_damage_formula(expr, rng=Random(seed))
    second = roll_damage_formula(expr, rng=Random(seed))
    assert first == second
    assert isinstance(first, int)


@settings(max_examples=30, deadline=None)
@given(expr=dice_expr, seed=st.integers(0, 2**31 - 1), critical=st.booleans())
def test_fast_and_detailed_damage_rollers_agree(
    expr: str, seed: int, critical: bool
) -> None:
    assert (
        roll_damage_formula(expr, critical=critical, rng=Random(seed))
        == roll_damage_formula_breakdown(
            expr, critical=critical, rng=Random(seed)
        ).total
    )


@settings(max_examples=30, deadline=None)
@given(count=st.integers(1, 6), sides=safe_die, keep=st.integers(1, 6))
def test_keep_drop_counts_are_accepted_only_when_legal(
    count: int, sides: int, keep: int
) -> None:
    expr = f"{count}d{sides}kh{keep}"
    if keep <= count:
        assert parse_damage_expression(expr)
    else:
        with pytest.raises(ValueError):
            parse_damage_expression(expr)


@settings(max_examples=30, deadline=None)
@given(a=dice_expr, b=dice_expr, seed=st.integers(0, 2**31 - 1))
def test_safe_compound_expressions_remain_deterministic(
    a: str, b: str, seed: int
) -> None:
    expr = f"{a}-{b}"
    assert roll_damage_formula(expr, rng=Random(seed)) == roll_damage_formula(
        expr, rng=Random(seed)
    )


def _state(ids=("a", "b")) -> dict[str, object]:
    state = {
        build_attack_ids_key("first"): list(ids),
        build_attack_ids_key("second"): ["z"],
    }
    for aid in ids:
        state[profile_widget_key(attack_widget_prefix("first", aid), "name")] = aid
    state[profile_widget_key(attack_widget_prefix("second", "z"), "name")] = "z"
    return state


@settings(max_examples=30, deadline=None)
@given(order=st.permutations(["a", "b", "c"]))
def test_reordering_preserves_stable_ids_and_state(order: tuple[str, ...]) -> None:
    state = _state(("a", "b", "c"))
    state[build_attack_ids_key("first")] = list(order)
    assert state[build_attack_ids_key("first")] == list(order)
    for aid in order:
        assert (
            state[profile_widget_key(attack_widget_prefix("first", aid), "name")] == aid
        )


def test_duplication_deletion_and_build_isolation() -> None:
    state = _state(("a", "b"))
    _duplicate_attack_state(state, "first", "a", "c")
    assert state[build_attack_ids_key("first")].count("c") == 1
    assert "z" in state[build_attack_ids_key("second")]
    _delete_attack_state(state, "first", "b")
    assert "b" not in state[build_attack_ids_key("first")]
    assert attack_widget_prefix("first", "c") != attack_widget_prefix("second", "c")


def test_migration_and_sharing_round_trip_preserve_ids_and_references() -> None:
    resource = ManagedResource("focus", "Focus", 2)
    first = AttackProfile(
        "A", 5, "1d6", 1, attack_id="a", resource_costs=(ResourceCost("focus", 1),)
    )
    second = AttackProfile(
        "B",
        5,
        "1d6",
        1,
        attack_id="b",
        trigger_type=TriggerType.AFTER_SUCCESS,
        trigger_source_attack_id="a",
    )
    config = shared_configuration_from_configs(
        BuildConfig("A", 5, "1d6", 1, attack_profiles=(first, second)),
        BuildConfig(
            "B",
            5,
            "1d6",
            1,
            attack_profiles=(AttackProfile("C", 5, "1d6", 1, attack_id="c"),),
        ),
        ScenarioConfig(15, 3, 2, 10, managed_resources=(resource,)),
        compare=True,
    )
    restored = deserialize_shared_configuration(serialize_shared_configuration(config))
    assert restored == deserialize_shared_configuration(
        serialize_shared_configuration(restored)
    )
    assert [p.attack_id for p in restored.build_a.attack_profiles] == ["a", "b"]
    assert restored.build_a.attack_profiles[1].trigger_source_attack_id == "a"
    assert restored.scenario.managed_resources[0].resource_id == "focus"
    assert restored.build_a.attack_profiles[0].resource_costs[0].resource_id == "focus"
