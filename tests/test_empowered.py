from dataclasses import replace
from itertools import combinations, product

from dnd_combat_simulator.dice import (
    parse_damage_expression,
    roll_compiled_damage_breakdown,
)
from dnd_combat_simulator.sharing import SharedAttackProfileConfiguration
from dnd_combat_simulator.simulation import (
    AttackProfile,
    BuildConfig,
    EmpoweredDie,
    ManagedResource,
    ScenarioConfig,
    _cached_empowered_rescue_indexes,
    _cached_match_probability_after_reroll,
    _has_matching_pair,
    _included_empowered_dice,
    _match_probability_after_reroll,
    _select_empowered_damage_dice,
    _select_empowered_rescue_dice,
    run_damage_simulations,
    simulate_build,
)
from dnd_combat_simulator.ui.validation import _validate_profile_fields


class SeqRng:
    def __init__(self, values):
        self.values = list(values)

    def randint(self, a, b):
        value = self.values.pop(0)
        assert a <= value <= b
        return value


def _dice(formula, rolls):
    return _included_empowered_dice(
        roll_compiled_damage_breakdown(
            parse_damage_expression(formula), rng=SeqRng(rolls)
        )
    )


def _exhaustive_probability(dice, indexes):
    retained = [die.face for i, die in enumerate(dice) if i not in indexes]
    sides = [dice[i].sides for i in indexes]
    outcomes = product(*(range(1, side + 1) for side in sides))
    successes = sum(_has_matching_pair(tuple(retained) + rolls) for rolls in outcomes)
    total = 1
    for side in sides:
        total *= side
    return successes / total if total else 0


def _legacy_rescue_indexes(dice, max_dice):
    best = None
    for count in range(1, min(max_dice, len(dice)) + 1):
        for indexes in combinations(range(len(dice)), count):
            probability = _exhaustive_probability(dice, indexes)
            if probability <= 0:
                continue
            low = tuple(sorted(dice[i].face for i in indexes))
            improvement = sum((dice[i].sides + 1) / 2 - dice[i].face for i in indexes)
            key = (probability, tuple(-face for face in low), improvement, -count)
            if best is None or key > best[0]:
                best = (key, indexes)
    return best[1] if best else ()


def _selected_indexes(dice, selected):
    return tuple(
        i for i, die in enumerate(dice) if any(die is item for item in selected)
    )


def test_matching_probability_matches_exhaustive_reference():
    cases = [
        (_dice("4d8", [1, 2, 3, 4]), (0, 1, 2, 3)),
        (_dice("5d8", [1, 2, 3, 4, 5]), (0,)),
        (_dice("5d8", [1, 2, 3, 4, 5]), (0, 1, 2, 3)),
        (_dice("1d6+1d8", [1, 7]), (0, 1)),
        (_dice("3d8", [5, 5, 7]), (2,)),
        (_dice("1d6+1d8", [6, 8]), (0,)),
    ]
    for dice, indexes in cases:
        assert _match_probability_after_reroll(
            dice, indexes
        ) == _exhaustive_probability(dice, indexes)


def test_rescue_selection_matches_exhaustive_reference_and_tie_breaking():
    cases = [
        (_dice("5d8", faces), max_dice)
        for faces in ([1, 2, 3, 4, 5], [1, 3, 5, 7, 8], [2, 4, 6, 7, 8])
        for max_dice in (1, 2, 4, 9)
    ]
    cases.extend(
        [
            (_dice("1d6+1d8+1d8", [2, 3, 7]), 2),
            (_dice("4d8", [1, 2, 3, 4]), 4),
            (_dice("2d6", [1, 2]), 1),
        ]
    )
    for dice, max_dice in cases:
        selected = _select_empowered_rescue_dice(dice, max_dice)
        assert _selected_indexes(dice, selected) == _legacy_rescue_indexes(
            dice, max_dice
        )


def test_rescue_selection_maps_cached_indexes_to_exploding_chain_dice():
    dice = (
        EmpoweredDie(0, 0, 0, 8, 2, 2),
        EmpoweredDie(0, 0, 1, 8, 8, 8),
        EmpoweredDie(0, 1, 0, 8, 3, 3),
        EmpoweredDie(0, 1, 1, 6, 6, 6),
    )
    selected = _select_empowered_rescue_dice(dice, 3)
    assert _selected_indexes(dice, selected) == _legacy_rescue_indexes(dice, 3)
    assert all(any(item is die for die in dice) for item in selected)


def test_empowered_probability_and_selection_caches_record_hits():
    _cached_match_probability_after_reroll.cache_clear()
    _cached_empowered_rescue_indexes.cache_clear()
    dice = _dice("5d8", [1, 2, 3, 4, 5])

    _match_probability_after_reroll(dice, (0, 1, 2, 3))
    first_probability = _cached_match_probability_after_reroll.cache_info()
    _match_probability_after_reroll(dice, (0, 1, 2, 3))
    assert (
        _cached_match_probability_after_reroll.cache_info().hits
        > first_probability.hits
    )

    _select_empowered_rescue_dice(dice, 4)
    first_selection = _cached_empowered_rescue_indexes.cache_info()
    _select_empowered_rescue_dice(dice, 4)
    assert _cached_empowered_rescue_indexes.cache_info().hits > first_selection.hits


def test_normal_empowered_rerolls_lowest_eligible_identical_dice():
    selected = _select_empowered_damage_dice(_dice("3d6", [3, 1, 2]), 2)
    assert [die.face for die in selected] == [1, 2]


def test_mixed_dice_use_expected_improvement_not_raw_face():
    selected = _select_empowered_damage_dice(_dice("1d4+1d12", [1, 2]), 1)
    assert [(die.sides, die.face) for die in selected] == [(12, 2)]


def test_empowered_new_rolls_replace_original_even_when_worse_and_spend_one():
    profile = AttackProfile(
        "Spell",
        20,
        "1d6",
        1,
        empowered_spell_enabled=True,
        empowered_resource_id="sp",
        empowered_max_dice_rerolled=1,
    )
    result = run_damage_simulations(
        attack_bonus=20,
        target_armor_class=1,
        damage_dice="1",
        rounds=1,
        simulations=1,
        attack_profiles=(profile,),
        managed_resources=(ManagedResource("sp", "Metamagic", 5),),
        rng=SeqRng([10, 1, 1]),
    )
    assert result.average_total_damage == 1
    assert result.resource_usage_results[0].average_consumed_per_combat == 1


def test_empowered_does_not_spend_without_rerolls_or_resources():
    resource = ManagedResource("sp", "Metamagic", 1)
    high = AttackProfile(
        "High", 20, "1d6", 1, empowered_spell_enabled=True, empowered_resource_id="sp"
    )
    result = run_damage_simulations(
        attack_bonus=20,
        target_armor_class=1,
        damage_dice="1",
        rounds=1,
        simulations=1,
        attack_profiles=(high,),
        managed_resources=(resource,),
        rng=SeqRng([10, 6]),
    )
    assert result.resource_usage_results[0].average_consumed_per_combat == 0
    empty = replace(high, empowered_resource_id="empty")
    result = run_damage_simulations(
        attack_bonus=20,
        target_armor_class=1,
        damage_dice="1",
        rounds=1,
        simulations=1,
        attack_profiles=(empty,),
        managed_resources=(ManagedResource("empty", "Empty", 0),),
        rng=SeqRng([10, 1]),
    )
    assert result.resource_usage_results[0].average_consumed_per_combat == 0


def test_matching_rescue_selection_can_match_retained_or_rerolled_dice():
    retained = _select_empowered_rescue_dice(_dice("3d6", [1, 2, 3]), 1)
    assert len(retained) == 1
    assert _has_matching_pair(tuple(d.face for d in _dice("3d6", [1, 2, 3]))) is False
    rerolled_pair = _select_empowered_rescue_dice(_dice("2d6", [1, 2]), 2)
    assert len(rerolled_pair) == 2


def test_matching_rescue_does_nothing_with_existing_match_and_only_before_final():
    profile = AttackProfile(
        "Chain",
        20,
        "2d6",
        2,
        require_matching_damage_dice_to_continue=True,
        empowered_matching_rescue_enabled=True,
        empowered_resource_id="sp",
    )
    result = run_damage_simulations(
        attack_bonus=20,
        target_armor_class=1,
        damage_dice="1",
        rounds=1,
        simulations=1,
        attack_profiles=(profile,),
        managed_resources=(ManagedResource("sp", "Metamagic", 1),),
        rng=SeqRng([10, 2, 2, 10, 1, 2]),
    )
    assert result.total_attacks_made == 2
    assert result.resource_usage_results[0].average_consumed_per_combat == 0


def test_successful_and_failed_matching_rescue_control_later_attacks():
    resource = ManagedResource("sp", "Metamagic", 1)
    profile = AttackProfile(
        "Chain",
        20,
        "2d6",
        2,
        require_matching_damage_dice_to_continue=True,
        empowered_matching_rescue_enabled=True,
        empowered_resource_id="sp",
        empowered_max_dice_rerolled=1,
    )
    success = run_damage_simulations(
        attack_bonus=20,
        target_armor_class=1,
        damage_dice="1",
        rounds=1,
        simulations=1,
        attack_profiles=(profile,),
        managed_resources=(resource,),
        rng=SeqRng([10, 1, 2, 2, 10, 6, 6]),
    )
    assert success.total_attacks_made == 2
    assert success.attack_profile_results[0].empowered_matching_rescue_success_rate == 1
    failed = run_damage_simulations(
        attack_bonus=20,
        target_armor_class=1,
        damage_dice="1",
        rounds=1,
        simulations=1,
        attack_profiles=(profile,),
        managed_resources=(resource,),
        rng=SeqRng([10, 1, 2, 3]),
    )
    assert failed.total_attacks_made == 1
    assert failed.total_skipped_profile_uses == 1


def test_both_features_rescue_takes_priority_and_normal_preserves_only_match():
    resource = ManagedResource("sp", "Metamagic", 1)
    profile = AttackProfile(
        "Chain",
        20,
        "2d6",
        2,
        require_matching_damage_dice_to_continue=True,
        empowered_matching_rescue_enabled=True,
        empowered_spell_enabled=True,
        empowered_resource_id="sp",
        empowered_max_dice_rerolled=1,
    )
    result = run_damage_simulations(
        attack_bonus=20,
        target_armor_class=1,
        damage_dice="1",
        rounds=1,
        simulations=1,
        attack_profiles=(profile,),
        managed_resources=(resource,),
        rng=SeqRng([10, 1, 2, 2, 10, 6, 6]),
    )
    stats = result.attack_profile_results[0]
    assert stats.average_empowered_matching_rescue_attempts_per_combat == 1
    assert stats.average_empowered_uses_per_combat == 0
    dice = _dice("2d6", [1, 1])
    assert _select_empowered_damage_dice(dice, 2, protected_match=True) == ()


def test_critical_and_shared_damage_empowered_spending():
    crit = AttackProfile(
        "Crit",
        20,
        "1d6",
        1,
        empowered_spell_enabled=True,
        empowered_resource_id="sp",
        empowered_max_dice_rerolled=2,
    )
    result = run_damage_simulations(
        attack_bonus=20,
        target_armor_class=1,
        damage_dice="1",
        rounds=1,
        simulations=1,
        attack_profiles=(crit,),
        managed_resources=(ManagedResource("sp", "Metamagic", 2),),
        rng=SeqRng([20, 1, 2, 6, 6, 6, 6]),
    )
    assert result.average_total_damage == 12
    shared = AttackProfile(
        "Blast",
        None,
        "2d6",
        1,
        affected_targets=3,
        resolution_type="saving_throw",
        save_dc=99,
        empowered_spell_enabled=True,
        empowered_resource_id="sp",
        empowered_max_dice_rerolled=2,
    )
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=1,
        enemy_save_bonus=0,
        damage_dice="1",
        rounds=1,
        simulations=1,
        attack_profiles=(shared,),
        managed_resources=(ManagedResource("sp", "Metamagic", 5),),
        rng=SeqRng([1, 2, 6, 6, 1, 1, 1]),
    )
    assert result.resource_usage_results[0].average_consumed_per_combat == 1


def test_clone_serialization_and_validation_preserve_empowered_settings():
    profile = AttackProfile(
        "Spell",
        20,
        "1d6",
        2,
        require_matching_damage_dice_to_continue=True,
        empowered_spell_enabled=True,
        empowered_matching_rescue_enabled=True,
        empowered_resource_id="sp",
        empowered_max_dice_rerolled=3,
    )
    shared = SharedAttackProfileConfiguration.from_attack_profile(profile)
    restored = shared.to_attack_profile()
    assert restored == profile
    build_a = BuildConfig(
        "A",
        1,
        "1",
        1,
        attack_profiles=(profile,),
        managed_resources=(ManagedResource("sp", "Metamagic", 3),),
    )
    build_b = replace(
        build_a,
        name="B",
        attack_profiles=tuple(replace(p) for p in build_a.attack_profiles),
    )
    assert build_b.attack_profiles[0] == profile
    assert build_b.attack_profiles is not build_a.attack_profiles
    invalid = replace(
        profile, empowered_resource_id="missing", empowered_max_dice_rerolled=0
    )
    assert _validate_profile_fields(
        invalid, prefix="first", available_resource_ids=frozenset({"sp"})
    )
    valid = replace(invalid, empowered_resource_id="sp", empowered_max_dice_rerolled=1)
    assert (
        _validate_profile_fields(
            valid, prefix="first", available_resource_ids=frozenset({"sp"})
        )
        == []
    )
    simulate_build(build_a, ScenarioConfig(1, 1, 1), seed=1)
