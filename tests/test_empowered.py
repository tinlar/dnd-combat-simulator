from dataclasses import replace

from dnd_combat_simulator.dice import (
    parse_damage_expression,
    roll_compiled_damage_breakdown,
)
from dnd_combat_simulator.sharing import SharedAttackProfileConfiguration
from dnd_combat_simulator.simulation import (
    AttackProfile,
    BuildConfig,
    ManagedResource,
    ScenarioConfig,
    _has_matching_pair,
    _included_empowered_dice,
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
