from random import Random

from dnd_combat_simulator.combat import ResolutionType, SuccessfulSaveDamage
from dnd_combat_simulator.dice import (
    parse_damage_expression,
    roll_compiled_damage_expression,
    roll_damage_formula,
)
from dnd_combat_simulator.simulation import (
    AttackProfile,
    BuildConfig,
    ScenarioConfig,
    compare_builds,
    run_damage_simulations,
)


class Rng:
    def __init__(self, rolls):
        self.rolls = list(rolls)

    def randint(self, a, b):
        value = self.rolls.pop(0)
        assert a <= value <= b
        return value


def test_mixed_automatic_damage_average_uses_only_automatic_damage_total():
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        damage_dice="1",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                name="Hit", attack_bonus=99, damage_dice="10", attacks_per_round=1
            ),
            AttackProfile(
                name="Aura",
                attack_bonus=None,
                damage_dice="2",
                attacks_per_round=1,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
        ),
        rng=Rng([10]),
    )

    assert result.average_total_damage_per_simulation == 12
    assert result.automatic_damage_applications == 1
    assert result.average_automatic_damage_per_application == 2
    assert (
        result.attack_profile_results[1].average_automatic_damage_per_application == 2
    )


def test_expected_damage_per_target_resolution_includes_zero_damage_outcomes():
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=99,
        damage_dice="10",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                name="Save for none",
                attack_bonus=None,
                save_dc=1,
                damage_dice="10",
                attacks_per_round=1,
                resolution_type=ResolutionType.SAVING_THROW,
                successful_save_damage=SuccessfulSaveDamage.NO_DAMAGE,
            ),
        ),
        rng=Rng([20]),
    )

    assert result.total_target_resolutions == 1
    assert result.total_targets_affected == 0
    assert result.average_damage_per_target_per_round == 0
    assert result.attack_profile_results[0].average_damage_per_target_per_round == 0


def test_comparison_difference_is_build_a_minus_build_b_for_all_metrics():
    comparison = compare_builds(
        first_build=BuildConfig(
            name="A", attack_bonus=0, damage_dice="1", attacks_per_round=1
        ),
        second_build=BuildConfig(
            name="B", attack_bonus=99, damage_dice="1", attacks_per_round=1
        ),
        scenario=ScenarioConfig(target_armor_class=10, rounds=1, simulations=1),
        seed=1,
    )

    assert comparison.higher_average_damage_build_name == "B"
    assert comparison.difference.average_damage_per_round > 0
    assert comparison.difference.hit_rate > 0


def test_compiled_damage_expression_matches_public_formula_for_same_seed():
    expression = parse_damage_expression("4d6r1!kh3+2d8!+1d4-2")
    for seed in range(20):
        assert roll_compiled_damage_expression(
            expression, rng=Random(seed)
        ) == roll_damage_formula("4d6r1!kh3+2d8!+1d4-2", rng=Random(seed))
