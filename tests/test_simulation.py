from random import Random

import pytest

from dnd_combat_simulator.build_math import BuildMathDefaults
from dnd_combat_simulator.combat import (
    AttackFeature,
    AttackRollMode,
    ResolutionType,
    SuccessfulSaveDamage,
)
from dnd_combat_simulator.simulation import (
    AttackProfile,
    BuildConfig,
    ComparisonDifference,
    ManagedResource,
    ResourceCost,
    RoundResult,
    ScenarioConfig,
    SimulationResult,
    TriggerFrequency,
    TriggerType,
    compare_builds,
    parse_active_rounds,
    run_damage_simulations,
    simulate_build,
)


class PredictableRng:
    def __init__(self, rolls: list[int]) -> None:
        self.rolls = rolls
        self.calls: list[tuple[int, int]] = []

    def randint(self, a: int, b: int) -> int:
        self.calls.append((a, b))
        return self.rolls.pop(0)


def test_run_damage_simulations_returns_summary_statistics() -> None:
    rng = PredictableRng(
        [
            10,
            4,  # simulation 1, round 1: hit for 6
            3,  # simulation 1, round 2: miss
            20,
            1,
            2,  # simulation 1, round 3: critical hit for 5
            1,  # simulation 2, round 1: natural 1 miss
            15,
            6,  # simulation 2, round 2: hit for 8
            8,  # simulation 2, round 3: miss
        ]
    )

    result = run_damage_simulations(
        attack_bonus=5,
        target_armor_class=15,
        damage_dice="1d6+2",
        rounds=3,
        simulations=2,
        rng=rng,
    )

    assert result == SimulationResult(
        simulations_run=2,
        rounds_per_simulation=3,
        attacks_per_round=1,
        attack_roll_mode=AttackRollMode.NORMAL,
        total_attacks_made=6,
        average_total_damage_per_simulation=9.5,
        average_damage_per_round=19 / 6,
        hit_rate=0.5,
        critical_hit_rate=1 / 6,
        minimum_total_damage_in_simulation=8,
        maximum_total_damage_in_simulation=11,
    )
    assert rng.calls == [
        (1, 20),
        (1, 6),
        (1, 20),
        (1, 20),
        (1, 6),
        (1, 6),
        (1, 20),
        (1, 20),
        (1, 6),
        (1, 20),
    ]


def test_simulation_does_not_roll_damage_for_misses() -> None:
    rng = PredictableRng([2, 3])

    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=20,
        damage_dice="2d8",
        rounds=2,
        simulations=1,
        rng=rng,
    )

    assert result.total_attacks_made == 2
    assert result.average_total_damage_per_simulation == 0
    assert result.hit_rate == 0
    assert result.minimum_total_damage_in_simulation == 0
    assert result.maximum_total_damage_in_simulation == 0
    assert rng.calls == [(1, 20), (1, 20)]


@pytest.mark.parametrize("rounds", [0, -1])
def test_rounds_must_be_at_least_one(rounds: int) -> None:
    with pytest.raises(ValueError, match="Number of rounds must be at least 1"):
        run_damage_simulations(
            attack_bonus=5,
            target_armor_class=15,
            damage_dice="1d8",
            rounds=rounds,
            simulations=1,
            rng=PredictableRng([]),
        )


@pytest.mark.parametrize("simulations", [0, -1])
def test_simulations_must_be_at_least_one(simulations: int) -> None:
    with pytest.raises(ValueError, match="Number of simulations must be at least 1"):
        run_damage_simulations(
            attack_bonus=5,
            target_armor_class=15,
            damage_dice="1d8",
            rounds=1,
            simulations=simulations,
            rng=PredictableRng([]),
        )


@pytest.mark.parametrize("attacks_per_round", [0, -1])
def test_attacks_per_round_must_be_at_least_one(attacks_per_round: int) -> None:
    with pytest.raises(ValueError, match="Attacks per round must be at least 1"):
        run_damage_simulations(
            attack_bonus=5,
            target_armor_class=15,
            damage_dice="1d8",
            rounds=1,
            simulations=1,
            attacks_per_round=attacks_per_round,
            rng=PredictableRng([]),
        )


@pytest.mark.parametrize("attacks_per_round", [1, 2, 3])
def test_multiple_attacks_per_round_are_deterministic(
    attacks_per_round: int,
) -> None:
    rng = PredictableRng([10, 4] * attacks_per_round)

    result = run_damage_simulations(
        attack_bonus=5,
        target_armor_class=15,
        damage_dice="1d6+2",
        rounds=1,
        simulations=1,
        attacks_per_round=attacks_per_round,
        rng=rng,
    )

    assert result == SimulationResult(
        simulations_run=1,
        rounds_per_simulation=1,
        attacks_per_round=attacks_per_round,
        attack_roll_mode=AttackRollMode.NORMAL,
        total_attacks_made=attacks_per_round,
        average_total_damage_per_simulation=6 * attacks_per_round,
        average_damage_per_round=6 * attacks_per_round,
        hit_rate=1,
        critical_hit_rate=0,
        minimum_total_damage_in_simulation=6 * attacks_per_round,
        maximum_total_damage_in_simulation=6 * attacks_per_round,
    )
    assert rng.calls == [(1, 20), (1, 6)] * attacks_per_round


def test_invalid_damage_dice_errors_are_reused_from_attack_resolution() -> None:
    result = run_damage_simulations(
        attack_bonus=20,
        target_armor_class=15,
        damage_dice="1d8+3",
        rounds=1,
        simulations=1,
        rng=PredictableRng([10, 4]),
    )
    assert result.average_total_damage_per_simulation == 7


def test_attack_roll_mode_applies_to_every_attack_in_simulation() -> None:
    rng = PredictableRng([1, 12, 4, 18, 7, 5])

    result = run_damage_simulations(
        attack_bonus=3,
        target_armor_class=15,
        damage_dice="1d6+2",
        rounds=1,
        simulations=1,
        attacks_per_round=2,
        attack_roll_mode=AttackRollMode.ADVANTAGE,
        rng=rng,
    )

    assert result.attack_roll_mode is AttackRollMode.ADVANTAGE
    assert result.total_attacks_made == 2
    assert result.hit_rate == 1
    assert result.average_total_damage_per_simulation == 13
    assert rng.calls == [
        (1, 20),
        (1, 20),
        (1, 6),
        (1, 20),
        (1, 20),
        (1, 6),
    ]


def test_compare_builds_uses_same_seed_with_separate_rng_instances() -> None:
    comparison = compare_builds(
        first_build=BuildConfig(
            name="Accurate",
            attack_bonus=20,
            damage_dice="1d4",
            attacks_per_round=1,
        ),
        second_build=BuildConfig(
            name="Heavy",
            attack_bonus=20,
            damage_dice="1d4",
            attacks_per_round=1,
        ),
        scenario=ScenarioConfig(target_armor_class=1, rounds=3, simulations=2),
        seed=1234,
    )

    assert comparison.first_result == comparison.second_result
    assert comparison.difference == ComparisonDifference(0, 0, 0, 0)
    assert comparison.higher_average_damage_build_name is None


def test_compare_builds_reports_differences_and_higher_damage_build() -> None:
    comparison = compare_builds(
        first_build=BuildConfig(
            name="Rapier",
            attack_bonus=5,
            damage_dice="1d8",
            attacks_per_round=1,
        ),
        second_build=BuildConfig(
            name="Greatsword",
            attack_bonus=5,
            damage_dice="1d8+1",
            attacks_per_round=1,
        ),
        scenario=ScenarioConfig(target_armor_class=14, rounds=2, simulations=5),
        seed=99,
    )

    assert comparison.higher_average_damage_build_name == "Greatsword"
    assert comparison.difference.average_damage_per_round == pytest.approx(0.6)
    assert comparison.difference.average_total_damage == pytest.approx(1.2)
    assert comparison.difference.hit_rate == 0
    assert comparison.difference.critical_hit_rate == 0


def test_build_with_two_attack_profiles_combines_damage_and_preserves_rates() -> None:
    rng = PredictableRng(
        [
            10,
            4,  # slash hits for 7
            20,
            1,
            2,  # smite crits for 6
        ]
    )

    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        damage_dice="1d4",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile("Slash", 0, "1d6+3", 1),
            AttackProfile("Smite", 0, "1d4+3", 1),
        ),
        rng=rng,
    )

    assert result.total_attacks_made == 2
    assert result.attacks_per_round == 2
    assert result.average_total_damage_per_simulation == 13
    assert result.average_damage_per_round == 13
    assert result.hit_rate == 1
    assert result.critical_hit_rate == 0.5
    assert [
        profile.attack_profile.name for profile in result.attack_profile_results
    ] == [
        "Slash",
        "Smite",
    ]
    assert [
        profile.average_damage_per_round for profile in result.attack_profile_results
    ] == [
        7,
        6,
    ]


def test_compare_builds_accepts_explicit_two_profile_build_config() -> None:
    comparison = compare_builds(
        first_build=BuildConfig(
            name="Sword and Bow",
            attack_bonus=0,
            damage_dice="1d4",
            attacks_per_round=1,
            attack_profiles=(
                AttackProfile("Sword", 20, "1d4+1", 1),
                AttackProfile("Bow", 20, "1d6+2", 1),
            ),
        ),
        second_build=BuildConfig("Single", 20, "1d4+1", 1),
        scenario=ScenarioConfig(target_armor_class=1, rounds=1, simulations=1),
        seed=1,
    )

    assert len(comparison.first_result.attack_profile_results) == 2
    assert comparison.first_result.total_attacks_made == 2
    assert comparison.second_result.total_attacks_made == 1
    assert comparison.higher_average_damage_build_name == "Sword and Bow"


def test_simulation_accepts_more_than_two_attack_profiles() -> None:
    profiles = tuple(
        AttackProfile(f"Attack {index}", 20, "1d4", 1) for index in range(1, 5)
    )

    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=1,
        damage_dice="1d4",
        rounds=1,
        simulations=1,
        attack_profiles=profiles,
        rng=PredictableRng([10, 1, 10, 1, 10, 1, 10, 1]),
    )

    assert len(result.attack_profile_results) == 4
    assert result.total_attacks_made == 4
    assert result.attacks_per_round == 4


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", None),
        ("1", frozenset({1})),
        ("1-5", frozenset({1, 2, 3, 4, 5})),
        ("1,3,8", frozenset({1, 3, 8})),
        ("1, 3-5, 8", frozenset({1, 3, 4, 5, 8})),
        (" 1 , 3 - 5 , 8 ", frozenset({1, 3, 4, 5, 8})),
        ("1-3, 2-4", frozenset({1, 2, 3, 4})),
    ],
)
def test_parse_active_rounds_valid_inputs(
    text: str, expected: frozenset[int] | None
) -> None:
    assert parse_active_rounds(text) == expected


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("0", "positive integers"),
        ("-1", "positive integers or ranges"),
        ("5-3", "must not be reversed"),
        ("1,,3", "empty comma group"),
        ("first round", "positive integers or ranges"),
    ],
)
def test_parse_active_rounds_invalid_inputs(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_active_rounds(text)


def test_active_rounds_use_different_attack_profile_each_round() -> None:
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=1,
        damage_dice="1d4",
        rounds=2,
        simulations=1,
        attack_profiles=(
            AttackProfile("A", 20, "1d4", 1, active_rounds="1"),
            AttackProfile("B", 20, "1d6", 1, active_rounds="2"),
        ),
        rng=PredictableRng([10, 2, 10, 6]),
    )
    assert [r.average_damage for r in result.round_results] == [2, 6]
    assert [p.total_attacks_made for p in result.attack_profile_results] == [1, 1]


def test_active_rounds_allow_round_with_no_attacks_and_preserve_metrics() -> None:
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=1,
        damage_dice="1d4",
        rounds=2,
        simulations=1,
        attack_profiles=(
            AttackProfile("A", 20, "1d4", 1, active_rounds="1"),
            AttackProfile("B", 20, "1d6", 1, active_rounds="1"),
        ),
        rng=PredictableRng([10, 2, 10, 6]),
    )
    assert result.round_results[0].average_damage == 8
    assert result.round_results[0].average_attacks == 2
    assert result.round_results[1].average_damage == 0
    assert result.round_results[1].average_attacks == 0
    assert result.first_round_burst_damage == 8
    assert result.average_damage_after_round_1 == 0
    assert result.highest_damage_round == 1
    assert result.highest_round_average_damage == 8


def test_active_rounds_beyond_scenario_length_are_ignored() -> None:
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=1,
        damage_dice="1d4",
        rounds=1,
        simulations=1,
        attack_profiles=(AttackProfile("A", 20, "1d4", 1, active_rounds="2"),),
        rng=PredictableRng([]),
    )
    assert result.total_attacks_made == 0
    assert result.round_results[0].average_attacks == 0


def test_existing_profile_without_active_rounds_repeats_attacks_per_round() -> None:
    result = run_damage_simulations(
        attack_bonus=20,
        target_armor_class=1,
        damage_dice="1d4",
        rounds=2,
        simulations=1,
        attacks_per_round=2,
        rng=PredictableRng([10, 1, 10, 2, 10, 3, 10, 4]),
    )
    assert result.total_attacks_made == 4
    assert [r.average_attacks for r in result.round_results] == [2, 2]


def test_mixed_attack_roll_and_saving_throw_profiles_in_one_build() -> None:
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        enemy_save_bonus=3,
        damage_dice="1d4",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile("Slash", 5, "1d6+3", 1),
            AttackProfile(
                "Burn",
                None,
                "1d8+2",
                1,
                resolution_type=ResolutionType.SAVING_THROW,
                save_dc=15,
            ),
        ),
        rng=PredictableRng([10, 4, 11, 5]),
    )

    assert result.average_total_damage_per_simulation == 14
    assert result.hit_rate == 1
    assert result.critical_hit_rate == 0
    assert result.failed_save_rate == 1
    assert result.successful_save_rate == 0


def test_active_rounds_with_saving_throw_profiles() -> None:
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        enemy_save_bonus=3,
        damage_dice="1d4",
        rounds=2,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                "Burn",
                None,
                "1d8+2",
                attacks_per_round=1,
                active_rounds="2",
                resolution_type=ResolutionType.SAVING_THROW,
                save_dc=15,
            ),
        ),
        rng=PredictableRng([11, 5]),
    )

    assert [round_result.average_damage for round_result in result.round_results] == [
        0,
        7,
    ]
    assert [round_result.average_attacks for round_result in result.round_results] == [
        0,
        1,
    ]


def test_build_comparison_can_use_different_resolution_types() -> None:
    comparison = compare_builds(
        first_build=BuildConfig("Attack", 20, "1d4", 1),
        second_build=BuildConfig(
            name="Save",
            attack_bonus=0,
            damage_dice="1d4",
            attacks_per_round=1,
            attack_profiles=(
                AttackProfile(
                    "Save damage",
                    None,
                    "1d4",
                    1,
                    resolution_type=ResolutionType.SAVING_THROW,
                    save_dc=30,
                ),
            ),
        ),
        scenario=ScenarioConfig(
            target_armor_class=1, enemy_save_bonus=3, rounds=1, simulations=1
        ),
        seed=1,
    )

    assert comparison.first_result.critical_hit_rate >= 0
    assert comparison.second_result.critical_hit_rate == 0
    assert comparison.second_result.failed_save_rate == 1


def test_existing_attack_roll_profiles_default_correctly() -> None:
    profile = AttackProfile("Slash", 5, "1d6+3", 1)

    assert profile.resolution_type is ResolutionType.ATTACK_ROLL
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        damage_dice="1d4",
        rounds=1,
        simulations=1,
        attack_profiles=(profile,),
        rng=PredictableRng([10, 4]),
    )
    assert result.hit_rate == 1


def test_attack_profile_defaults_to_one_affected_target() -> None:
    assert AttackProfile("Strike", 5, "1d6+2", 1).affected_targets == 1


def test_attack_roll_profile_resolves_each_target_independently() -> None:
    rng = PredictableRng([10, 1, 20, 2, 3, 1])

    result = run_damage_simulations(
        attack_bonus=5,
        target_armor_class=15,
        damage_dice="1d4",
        rounds=1,
        simulations=1,
        attack_profiles=(AttackProfile("Cleave", 5, "1d4", 1, affected_targets=3),),
        rng=rng,
    )

    assert result.total_attacks_made == 1
    assert result.total_target_resolutions == 3
    assert result.average_total_damage_per_simulation == 6
    assert result.average_damage_per_target_per_round == 2
    assert result.hit_rate == 2 / 3
    assert result.critical_hit_rate == 1 / 3
    assert rng.calls == [(1, 20), (1, 4), (1, 20), (1, 4), (1, 4), (1, 20)]


@pytest.mark.parametrize(
    ("mode", "rolls", "expected_damage", "expected_calls"),
    [
        (
            AttackRollMode.ADVANTAGE,
            [1, 12, 1, 7, 8],
            1,
            [(1, 20), (1, 20), (1, 4), (1, 20), (1, 20)],
        ),
        (
            AttackRollMode.DISADVANTAGE,
            [20, 12, 1, 20, 8],
            1,
            [(1, 20), (1, 20), (1, 4), (1, 20), (1, 20)],
        ),
    ],
)
def test_advantage_and_disadvantage_are_independent_per_target(
    mode: AttackRollMode,
    rolls: list[int],
    expected_damage: int,
    expected_calls: list[tuple[int, int]],
) -> None:
    rng = PredictableRng(rolls)

    result = run_damage_simulations(
        attack_bonus=3,
        target_armor_class=15,
        damage_dice="1d4",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                "Swing", 3, "1d4", 1, affected_targets=2, attack_roll_mode=mode
            ),
        ),
        rng=rng,
    )

    assert result.average_total_damage_per_simulation == expected_damage
    assert result.total_target_resolutions == 2
    assert rng.calls == expected_calls


def test_saving_throw_profile_uses_one_shared_damage_roll_and_independent_saves() -> (
    None
):
    rng = PredictableRng([5, 7, 10, 12, 20])

    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        enemy_save_bonus=0,
        damage_dice="1d8",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                "Blast",
                None,
                "1d8+2",
                attacks_per_round=1,
                affected_targets=4,
                resolution_type=ResolutionType.SAVING_THROW,
                save_dc=12,
            ),
        ),
        rng=rng,
    )

    assert result.average_total_damage_per_simulation == 14
    assert result.failed_save_rate == 0.5
    assert result.successful_save_rate == 0.5
    assert result.total_target_resolutions == 4
    assert rng.calls == [(1, 8), (1, 20), (1, 20), (1, 20), (1, 20)]


def test_saving_throw_half_damage_rounds_down_for_every_successful_target() -> None:
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        enemy_save_bonus=0,
        damage_dice="1d8",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                "Half Blast",
                None,
                "1d8+2",
                attacks_per_round=1,
                affected_targets=3,
                resolution_type=ResolutionType.SAVING_THROW,
                save_dc=12,
                successful_save_damage=SuccessfulSaveDamage.HALF_DAMAGE,
            ),
        ),
        rng=PredictableRng([5, 7, 12, 20]),
    )

    assert result.average_total_damage_per_simulation == 13
    assert result.average_damage_per_target_per_round == 13 / 3


def test_multiple_uses_active_rounds_and_multi_target_totals() -> None:
    result = run_damage_simulations(
        attack_bonus=5,
        target_armor_class=15,
        damage_dice="1d4",
        rounds=2,
        simulations=1,
        attack_profiles=(
            AttackProfile("Volley", 5, "1d4", 2, affected_targets=2, active_rounds="2"),
        ),
        rng=PredictableRng([10, 1, 10, 2, 10, 3, 10, 4]),
    )

    assert [round_result.average_damage for round_result in result.round_results] == [
        0,
        10,
    ]
    assert result.total_attacks_made == 2
    assert result.total_target_resolutions == 4
    assert result.average_damage_per_target_per_round == 2.5


def test_affected_targets_must_be_positive_integer() -> None:
    with pytest.raises(ValueError, match="affected targets must be an integer"):
        run_damage_simulations(
            attack_bonus=5,
            target_armor_class=15,
            damage_dice="1d4",
            rounds=1,
            simulations=1,
            attack_profiles=(AttackProfile("Bad", 5, "1d4", 1, affected_targets=0),),
            rng=PredictableRng([]),
        )


def test_comparison_reports_total_and_per_target_damage_for_multi_target_builds() -> (
    None
):
    comparison = compare_builds(
        first_build=BuildConfig("Single", 20, "1d4", 1),
        second_build=BuildConfig(
            "Multi",
            20,
            "1d4",
            0,
            1,
            attack_profiles=(AttackProfile("Multi", 20, "1d4", 1, affected_targets=2),),
        ),
        scenario=ScenarioConfig(target_armor_class=1, rounds=1, simulations=1),
        seed=1,
    )

    assert (
        comparison.second_result.average_damage_per_round
        > comparison.first_result.average_damage_per_round
    )
    assert comparison.difference.average_damage_per_target_per_round == 0


def test_automatic_damage_always_applies_without_d20_or_critical_hits() -> None:
    rng = PredictableRng([3])

    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=99,
        damage_dice="1d4",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                "Magic Missile",
                None,
                "1d4+2",
                1,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
        ),
        rng=rng,
    )

    assert result.average_total_damage_per_simulation == 5
    assert result.hit_rate == 0
    assert result.critical_hit_rate == 0
    assert result.automatic_damage_applications == 1
    assert result.average_automatic_damage_per_application == 5
    assert result.attack_profile_results[0].automatic_damage_applications == 1
    assert rng.calls == [(1, 4)]


def test_automatic_damage_multiple_uses_targets_and_separate_rolls() -> None:
    rng = PredictableRng([1, 2, 3, 4, 5, 6])

    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        damage_dice="1d6",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                "Darts",
                None,
                "1d6+1",
                3,
                affected_targets=2,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
        ),
        rng=rng,
    )

    assert result.total_attacks_made == 3
    assert result.total_target_resolutions == 6
    assert result.automatic_damage_applications == 6
    assert result.average_total_damage_per_simulation == 27
    assert result.average_damage_per_target_per_round == 4.5
    assert rng.calls == [(1, 6)] * 6


def test_automatic_damage_respects_active_rounds() -> None:
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        damage_dice="1d4",
        rounds=3,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                "Acid",
                None,
                "1d4",
                1,
                active_rounds="2-3",
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
        ),
        rng=PredictableRng([2, 4]),
    )

    assert [round_result.average_damage for round_result in result.round_results] == [
        0,
        2,
        4,
    ]
    assert result.automatic_damage_applications == 2


def test_mixed_profiles_exclude_automatic_damage_from_rate_denominators() -> None:
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        enemy_save_bonus=0,
        damage_dice="1d4",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile("Slash", 5, "1d4", 1),
            AttackProfile(
                "Burn",
                None,
                "1d4",
                1,
                resolution_type=ResolutionType.SAVING_THROW,
                save_dc=10,
            ),
            AttackProfile(
                "Missile",
                None,
                "1d4",
                1,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
        ),
        rng=PredictableRng([10, 1, 9, 2, 4]),
    )

    assert result.average_total_damage_per_simulation == 7
    assert result.hit_rate == 1
    assert result.failed_save_rate == 1
    assert result.successful_save_rate == 0
    assert result.automatic_damage_applications == 1


def test_simulate_build_matches_same_build_inside_compare_builds() -> None:
    from dnd_combat_simulator.simulation import simulate_build

    build = BuildConfig("Solo", 7, "1d8+4", 2)
    other = BuildConfig("Other", 5, "1d6+2", 1)
    scenario = ScenarioConfig(target_armor_class=15, rounds=3, simulations=20)

    result = simulate_build(build, scenario, seed=42)
    comparison = compare_builds(
        first_build=build,
        second_build=other,
        scenario=scenario,
        seed=42,
    )

    assert result == comparison.first_result


def test_simulate_build_does_not_validate_unrelated_second_build() -> None:
    from dnd_combat_simulator.simulation import simulate_build

    result = simulate_build(
        BuildConfig("Solo", 20, "1d4", 1),
        ScenarioConfig(target_armor_class=1, rounds=1, simulations=1),
        seed=1,
    )

    assert result.simulations_run == 1


def test_elven_accuracy_rejected_for_non_attack_profiles() -> None:

    from dnd_combat_simulator.combat import AttackFeature, ResolutionType
    from dnd_combat_simulator.simulation import AttackProfile, run_damage_simulations

    with pytest.raises(ValueError, match="Elven Accuracy requires an Attack Roll"):
        run_damage_simulations(
            attack_bonus=0,
            target_armor_class=10,
            damage_dice="1d6",
            rounds=1,
            simulations=1,
            attack_profiles=(
                AttackProfile(
                    "Save",
                    None,
                    "1d6",
                    1,
                    resolution_type=ResolutionType.SAVING_THROW,
                    save_dc=10,
                    features=frozenset({AttackFeature.ELVEN_ACCURACY}),
                ),
            ),
        )


def test_saving_throw_rejects_attack_roll_only_damage_features() -> None:
    from dnd_combat_simulator.combat import AttackFeature, ResolutionType
    from dnd_combat_simulator.simulation import AttackProfile, run_damage_simulations

    with pytest.raises(ValueError, match="requires an Attack Roll"):
        run_damage_simulations(
            attack_bonus=0,
            target_armor_class=10,
            damage_dice="1d6",
            rounds=1,
            simulations=1,
            enemy_save_bonus=0,
            attack_profiles=(
                AttackProfile(
                    "Shared save",
                    None,
                    "1d6",
                    1,
                    affected_targets=2,
                    resolution_type=ResolutionType.SAVING_THROW,
                    save_dc=10,
                    features=frozenset(
                        {
                            AttackFeature.TAVERN_BRAWLER,
                            AttackFeature.GREAT_WEAPON_FIGHTING,
                        }
                    ),
                ),
            ),
        )


def test_average_damage_per_use_for_successful_attack_and_misses() -> None:
    rng = PredictableRng([15, 4, 1])

    result = run_damage_simulations(
        attack_bonus=5,
        target_armor_class=10,
        damage_dice="1d4",
        rounds=2,
        simulations=1,
        rng=rng,
    )

    profile = result.attack_profile_results[0]
    assert profile.total_attacks_made == 2
    assert profile.total_profile_uses == 2
    assert profile.total_target_resolutions == 2
    assert profile.average_damage_per_use == pytest.approx(2)


def test_average_damage_per_use_for_saving_throw_with_half_damage() -> None:
    rng = PredictableRng([1, 4, 20, 4])

    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        damage_dice="1d4",
        rounds=2,
        simulations=1,
        rng=rng,
        attack_profiles=(
            AttackProfile(
                "Save",
                None,
                "1d4",
                1,
                resolution_type=ResolutionType.SAVING_THROW,
                save_dc=10,
                successful_save_damage=SuccessfulSaveDamage.HALF_DAMAGE,
            ),
        ),
    )

    profile = result.attack_profile_results[0]
    assert profile.total_profile_uses == 2
    assert profile.total_target_resolutions == 2
    assert profile.average_damage_per_use == pytest.approx(3)


def test_average_damage_per_use_for_automatic_multiple_targets_and_attacks() -> None:
    rng = PredictableRng([4, 4, 4, 4])

    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        damage_dice="1d4",
        rounds=1,
        simulations=1,
        rng=rng,
        attack_profiles=(
            AttackProfile(
                "Aura",
                None,
                "1d4",
                2,
                affected_targets=2,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
        ),
    )

    profile = result.attack_profile_results[0]
    assert profile.total_profile_uses == 2
    assert profile.total_target_resolutions == 4
    assert profile.average_damage_per_use == pytest.approx(8)


def test_average_damage_per_use_with_restricted_and_no_active_rounds() -> None:
    rng = PredictableRng([4])

    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        damage_dice="1d4",
        rounds=2,
        simulations=1,
        rng=rng,
        attack_profiles=(
            AttackProfile(
                "Round two only",
                None,
                "1d4",
                1,
                active_rounds="2",
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
            AttackProfile(
                "Never",
                None,
                "1d4",
                1,
                active_rounds="3",
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
        ),
    )

    active, never = result.attack_profile_results
    assert active.total_profile_uses == 1
    assert active.average_damage_per_use == pytest.approx(4)
    assert never.total_profile_uses == 0
    assert never.average_damage_per_use == 0


@pytest.mark.parametrize(
    ("d20s", "expected_uses", "expected_skips", "expected_calls"),
    [
        (
            [10, 10, 10, 10],
            4,
            0,
            [(1, 20), (1, 1), (1, 20), (1, 1), (1, 20), (1, 1), (1, 20), (1, 1)],
        ),
        ([2], 1, 3, [(1, 20)]),
        ([10, 2], 2, 2, [(1, 20), (1, 1), (1, 20)]),
        ([10, 10, 2], 3, 1, [(1, 20), (1, 1), (1, 20), (1, 1), (1, 20)]),
        (
            [10, 10, 10, 2],
            4,
            0,
            [(1, 20), (1, 1), (1, 20), (1, 1), (1, 20), (1, 1), (1, 20)],
        ),
    ],
)
def test_stop_on_miss_basic_sequences(
    d20s, expected_uses, expected_skips, expected_calls
) -> None:
    from dnd_combat_simulator.combat import AttackFeature

    rolls = []
    for d20 in d20s:
        rolls.append(d20)
        if d20 + 5 >= 15 and d20 != 1:
            rolls.append(1)
    rng = PredictableRng(rolls)

    result = run_damage_simulations(
        attack_bonus=5,
        target_armor_class=15,
        damage_dice="1d1",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                name="Chain",
                attack_bonus=5,
                damage_dice="1d1",
                attacks_per_round=4,
                features=frozenset({AttackFeature.STOP_ON_MISS}),
            ),
        ),
        rng=rng,
    )
    profile = result.attack_profile_results[0]

    assert profile.total_profile_uses == expected_uses
    assert profile.total_target_resolutions == expected_uses
    assert profile.total_skipped_profile_uses == expected_skips
    assert profile.average_skipped_profile_uses_per_simulation == expected_skips
    assert result.total_attacks_made == expected_uses
    assert result.total_skipped_profile_uses == expected_skips
    assert rng.calls == expected_calls


def test_stop_on_miss_resets_by_round_and_honors_active_rounds() -> None:
    from dnd_combat_simulator.combat import AttackFeature

    rng = PredictableRng([2, 10, 1, 2])
    result = run_damage_simulations(
        attack_bonus=5,
        target_armor_class=15,
        damage_dice="1d1",
        rounds=3,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                name="Chain",
                attack_bonus=5,
                damage_dice="1d1",
                attacks_per_round=3,
                active_rounds="1,3",
                features=frozenset({AttackFeature.STOP_ON_MISS}),
            ),
        ),
        rng=rng,
    )

    profile = result.attack_profile_results[0]
    assert profile.total_profile_uses == 3
    assert profile.total_skipped_profile_uses == 3
    assert tuple(
        round_result.average_attacks for round_result in result.round_results
    ) == (1, 0, 2)


def test_stop_on_miss_is_profile_independent() -> None:
    from dnd_combat_simulator.combat import AttackFeature

    rng = PredictableRng([2, 10, 1, 2])
    result = run_damage_simulations(
        attack_bonus=5,
        target_armor_class=15,
        damage_dice="1d1",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                "First", 5, "1d1", 3, features=frozenset({AttackFeature.STOP_ON_MISS})
            ),
            AttackProfile(
                "Second", 5, "1d1", 2, features=frozenset({AttackFeature.STOP_ON_MISS})
            ),
        ),
        rng=rng,
    )

    first, second = result.attack_profile_results
    assert first.total_profile_uses == 1
    assert first.total_skipped_profile_uses == 2
    assert second.total_profile_uses == 2
    assert second.total_skipped_profile_uses == 0


@pytest.mark.parametrize(
    ("mode", "rolls", "expected_uses"),
    [
        (AttackRollMode.NORMAL, [20, 1, 1, 2], 2),
        (AttackRollMode.NORMAL, [10, 1, 2], 2),
        (AttackRollMode.NORMAL, [1], 1),
        (AttackRollMode.ADVANTAGE, [2, 10, 1, 2, 3], 2),
        (AttackRollMode.DISADVANTAGE, [10, 2], 1),
        (AttackRollMode.ADVANTAGE, [2, 10, 15, 1, 2, 3, 4], 2),
    ],
)
def test_stop_on_miss_waits_for_attack_mechanics(mode, rolls, expected_uses) -> None:
    from dnd_combat_simulator.combat import AttackFeature

    features = {AttackFeature.STOP_ON_MISS}
    if mode is AttackRollMode.ADVANTAGE and len(rolls) == 7:
        features.add(AttackFeature.ELVEN_ACCURACY)
    result = run_damage_simulations(
        attack_bonus=5,
        target_armor_class=15,
        damage_dice="1d1-1",
        rounds=1,
        simulations=1,
        attack_roll_mode=mode,
        attack_profiles=(
            AttackProfile(
                "Chain",
                5,
                "1d1-1",
                2,
                attack_roll_mode=mode,
                features=frozenset(features),
            ),
        ),
        rng=PredictableRng(rolls),
    )
    assert result.attack_profile_results[0].total_profile_uses == expected_uses


@pytest.mark.parametrize(
    "profile",
    [
        AttackProfile(
            "Save",
            None,
            "1d1",
            1,
            resolution_type=ResolutionType.SAVING_THROW,
            save_dc=10,
            features=frozenset({"stop_on_miss"}),
        ),
        AttackProfile(
            "Auto",
            None,
            "1d1",
            1,
            resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            features=frozenset({"stop_on_miss"}),
        ),
        AttackProfile(
            "Multi",
            5,
            "1d1",
            1,
            affected_targets=2,
            features=frozenset({"stop_on_miss"}),
        ),
    ],
)
def test_stop_on_miss_validation(profile) -> None:
    with pytest.raises(
        ValueError,
        match=(
            "Stop on Miss requires an Attack Roll profile with "
            "exactly 1 Affected Target"
        ),
    ):
        run_damage_simulations(
            attack_bonus=5,
            target_armor_class=15,
            damage_dice="1d1",
            rounds=1,
            simulations=1,
            attack_profiles=(profile,),
            rng=PredictableRng([]),
        )


def test_potent_cantrip_multi_target_saving_throw_shares_damage_roll() -> None:
    from dnd_combat_simulator.combat import AttackFeature

    rng = PredictableRng([5, 2, 15, 3])

    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        damage_dice="1d8+1",
        enemy_save_bonus=0,
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                name="Cantrip",
                attack_bonus=None,
                resolution_type=ResolutionType.SAVING_THROW,
                save_dc=10,
                damage_dice="1d8+1",
                attacks_per_round=1,
                affected_targets=3,
                features=frozenset({AttackFeature.POTENT_CANTRIP}),
            ),
        ),
        rng=rng,
    )

    assert result.average_total_damage == 15
    assert rng.calls == [(1, 8), (1, 20), (1, 20), (1, 20)]


def test_automatic_damage_rejects_potent_cantrip() -> None:
    from dnd_combat_simulator.combat import AttackFeature

    with pytest.raises(ValueError, match="Potent Cantrip cannot be used"):
        run_damage_simulations(
            attack_bonus=0,
            target_armor_class=10,
            damage_dice="1d8",
            rounds=1,
            simulations=1,
            attack_profiles=(
                AttackProfile(
                    name="Auto",
                    attack_bonus=None,
                    resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                    damage_dice="1d8",
                    attacks_per_round=1,
                    features=frozenset({AttackFeature.POTENT_CANTRIP}),
                ),
            ),
        )


@pytest.mark.parametrize(
    "feature",
    [
        "ELVEN_ACCURACY",
        "GREAT_WEAPON_FIGHTING",
        "TAVERN_BRAWLER",
    ],
)
def test_attack_roll_only_features_rejected_for_saving_throw(feature: str) -> None:
    from dnd_combat_simulator.combat import AttackFeature

    with pytest.raises(ValueError, match="requires an Attack Roll"):
        run_damage_simulations(
            attack_bonus=0,
            target_armor_class=10,
            damage_dice="1d8",
            rounds=1,
            simulations=1,
            attack_profiles=(
                AttackProfile(
                    name="Save",
                    attack_bonus=None,
                    resolution_type=ResolutionType.SAVING_THROW,
                    save_dc=10,
                    damage_dice="1d8",
                    attacks_per_round=1,
                    features=frozenset({getattr(AttackFeature, feature)}),
                ),
            ),
        )


def test_multiple_attacks_against_one_target_counted_per_resolution() -> None:
    result = run_damage_simulations(
        attack_bonus=20,
        target_armor_class=1,
        damage_dice="1d1",
        rounds=1,
        simulations=1,
        attack_profiles=(AttackProfile("Focused", 20, "1d1", 3),),
        rng=PredictableRng([10, 1, 10, 1, 10, 1]),
    )

    assert result.average_damage_per_round == 3
    assert result.round_results[0].average_damage == 3
    assert result.round_results[0].average_targets_affected == 3
    assert result.round_results[0].average_individual_damage == 1
    assert result.average_damage_per_target_per_round == 1


def test_multiple_attacks_split_across_several_targets_count_each_resolution() -> None:
    result = run_damage_simulations(
        attack_bonus=20,
        target_armor_class=1,
        damage_dice="1d1",
        rounds=1,
        simulations=1,
        attack_profiles=(AttackProfile("Split", 20, "1d1", 3, affected_targets=2),),
        rng=PredictableRng([10, 1, 10, 1, 10, 1, 10, 1, 10, 1, 10, 1]),
    )

    assert result.average_damage_per_round == 6
    assert result.round_results[0].average_targets_affected == 6
    assert result.round_results[0].average_individual_damage == 1
    assert result.average_damage_per_target_per_round == 1


def test_area_attack_targets_individual_damage_and_target_count() -> None:
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        enemy_save_bonus=0,
        damage_dice="1d8",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                "Blast",
                None,
                "1d8+2",
                1,
                affected_targets=4,
                resolution_type=ResolutionType.SAVING_THROW,
                save_dc=12,
            ),
        ),
        rng=PredictableRng([5, 7, 10, 12, 20]),
    )

    assert result.average_damage_per_round == 14
    assert result.round_results[0].average_targets_affected == 2
    assert result.round_results[0].average_damage_per_target_resolution == 3.5
    assert result.average_damage_per_target_per_round == 3.5


def test_rounds_with_no_affected_targets_contribute_zero_individual_damage() -> None:
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=99,
        damage_dice="1d1",
        rounds=2,
        simulations=1,
        attack_profiles=(AttackProfile("Misses", 0, "1d1", 1),),
        rng=PredictableRng([2, 2]),
    )

    assert [round.average_damage for round in result.round_results] == [0, 0]
    assert [round.average_targets_affected for round in result.round_results] == [0, 0]
    assert [round.average_individual_damage for round in result.round_results] == [0, 0]
    assert result.average_damage_per_target_per_round == 0


def test_total_damage_damage_per_target_and_target_count_are_distinct() -> None:
    result = run_damage_simulations(
        attack_bonus=20,
        target_armor_class=1,
        damage_dice="1d1",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                "Target A 10",
                None,
                "1d1+9",
                1,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
            AttackProfile(
                "Target A 15",
                None,
                "1d1+14",
                1,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
            AttackProfile(
                "Targets A and B",
                None,
                "1d1+3",
                1,
                affected_targets=2,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
        ),
        rng=PredictableRng([1, 1, 1, 1]),
    )

    assert result.average_damage_per_round == 33
    assert result.round_results[0].average_damage == 33
    assert result.round_results[0].average_targets_affected == 4
    assert result.round_results[
        0
    ].average_damage_per_target_resolution == pytest.approx(8.25)
    assert result.average_damage_per_target_per_round == 8.25


def _single_round_result_for_profiles(
    profiles: tuple[AttackProfile, ...],
    rng: PredictableRng | None = None,
    target_armor_class: int = 99,
):
    return run_damage_simulations(
        attack_bonus=0,
        target_armor_class=target_armor_class,
        damage_dice="1",
        rounds=1,
        simulations=1,
        attack_profiles=profiles,
        rng=rng or PredictableRng([]),
    ).round_results[0]


def test_round_damage_counts_multiple_attacks_affecting_one_target_each() -> None:
    round_result = _single_round_result_for_profiles(
        (
            AttackProfile(
                "Five strikes",
                None,
                "10",
                5,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
        )
    )

    assert round_result.average_targets_affected == 5
    assert round_result.average_damage == 50
    assert round_result.average_individual_damage == 10


def test_round_damage_counts_one_attack_affecting_multiple_targets() -> None:
    round_result = _single_round_result_for_profiles(
        (
            AttackProfile(
                "Burst",
                None,
                "7",
                1,
                affected_targets=3,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
        )
    )

    assert round_result.average_targets_affected == 3
    assert round_result.average_damage == 21
    assert round_result.average_damage_per_target_resolution == 7


def test_round_damage_counts_multiple_attacks_affecting_multiple_targets() -> None:
    round_result = _single_round_result_for_profiles(
        (
            AttackProfile(
                "Twin bursts",
                None,
                "4",
                2,
                affected_targets=3,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
        )
    )

    assert round_result.average_targets_affected == 6
    assert round_result.average_damage == 24
    assert round_result.average_individual_damage == 4


def test_round_damage_excludes_misses_and_zero_damage_resolutions() -> None:
    round_result = _single_round_result_for_profiles(
        (
            AttackProfile(
                "Miss then zero then hit",
                0,
                "5",
                1,
                resolution_type=ResolutionType.ATTACK_ROLL,
            ),
            AttackProfile(
                "Zero",
                None,
                "0",
                1,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
            AttackProfile(
                "Hit",
                None,
                "8",
                1,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
        ),
        rng=PredictableRng([2]),
    )

    assert round_result.average_targets_affected == 1
    assert round_result.average_damage == 8
    assert round_result.average_damage_per_target_resolution == pytest.approx(8 / 3)


def test_round_damage_counts_successful_saves_that_still_receive_damage() -> None:
    round_result = _single_round_result_for_profiles(
        (
            AttackProfile(
                "Half save",
                None,
                "5",
                1,
                resolution_type=ResolutionType.SAVING_THROW,
                save_dc=10,
                successful_save_damage=SuccessfulSaveDamage.HALF_DAMAGE,
            ),
        ),
        rng=PredictableRng([20]),
    )

    assert round_result.average_targets_affected == 1
    assert round_result.average_damage == 2
    assert round_result.average_individual_damage == 2


def test_round_damage_does_not_deduplicate_repeated_attacks_against_same_target() -> (
    None
):
    round_result = _single_round_result_for_profiles(
        (
            AttackProfile(
                "Repeated target",
                20,
                "6",
                3,
                resolution_type=ResolutionType.ATTACK_ROLL,
            ),
        ),
        rng=PredictableRng([10, 10, 10]),
        target_armor_class=1,
    )

    assert round_result.average_targets_affected == 3
    assert round_result.average_damage == 18
    assert round_result.average_individual_damage == 6


def test_attack_roll_trigger_miss_executes_zero_times() -> None:
    rng = PredictableRng([1])
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=20,
        damage_dice="1d4",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile("Greatsword", 0, "1d4", 1, attack_id="a"),
            AttackProfile(
                "Smite",
                20,
                "1d4",
                1,
                attack_id="b",
                trigger_type="after_success",
                trigger_source_attack_id="a",
            ),
        ),
        rng=rng,
    )
    assert result.attack_profile_results[1].total_profile_uses == 0
    assert result.average_total_damage_per_simulation == 0


def test_attack_roll_trigger_per_success_executes_twice() -> None:
    rng = PredictableRng([10, 1, 10, 1, 10, 1, 10, 1])
    result = run_damage_simulations(
        attack_bonus=20,
        target_armor_class=15,
        damage_dice="1d4",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile("Greatsword", 20, "1d4", 2, attack_id="a"),
            AttackProfile(
                "Smite",
                20,
                "1d4",
                1,
                attack_id="b",
                trigger_type="after_success",
                trigger_source_attack_id="a",
            ),
        ),
        rng=rng,
    )
    assert result.attack_profile_results[1].total_profile_uses == 2
    assert result.attack_profile_results[1].triggered_profile_uses == 2
    assert result.average_total_damage_per_simulation == 4


def test_attack_roll_trigger_once_if_any_executes_once() -> None:
    rng = PredictableRng([10, 1, 10, 1, 10, 1])
    result = run_damage_simulations(
        attack_bonus=20,
        target_armor_class=15,
        damage_dice="1d4",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile("Greatsword", 20, "1d4", 2, attack_id="a"),
            AttackProfile(
                "Smite",
                20,
                "1d4",
                1,
                attack_id="b",
                trigger_type="after_success",
                trigger_source_attack_id="a",
                trigger_frequency="once_if_any",
            ),
        ),
        rng=rng,
    )
    assert result.attack_profile_results[1].total_profile_uses == 1
    assert result.average_total_damage_per_simulation == 3


def test_saving_throw_trigger_per_failed_save_executes_three_times() -> None:
    rng = PredictableRng([1, 1, 1, 1, 20, 20, 10, 1, 10, 1, 10, 1])
    result = run_damage_simulations(
        attack_bonus=20,
        target_armor_class=15,
        damage_dice="1d4",
        enemy_save_bonus=0,
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                "Fireball",
                None,
                "1d4",
                1,
                affected_targets=5,
                resolution_type=ResolutionType.SAVING_THROW,
                save_dc=10,
                attack_id="a",
            ),
            AttackProfile(
                "Burst",
                20,
                "1d4",
                1,
                attack_id="b",
                trigger_type="after_success",
                trigger_source_attack_id="a",
            ),
        ),
        rng=rng,
    )
    assert result.attack_profile_results[1].total_profile_uses == 3
    assert result.attack_profile_results[0].failed_save_rate == pytest.approx(3 / 5)


def test_trigger_validation_rejects_deleted_reordered_self_and_cycles() -> None:
    with pytest.raises(ValueError, match="no longer exists"):
        run_damage_simulations(
            attack_bonus=1,
            target_armor_class=10,
            damage_dice="1d4",
            rounds=1,
            simulations=1,
            attack_profiles=(
                AttackProfile(
                    "B",
                    1,
                    "1d4",
                    1,
                    attack_id="b",
                    trigger_type="after_success",
                    trigger_source_attack_id="missing",
                ),
            ),
        )
    run_damage_simulations(
        attack_bonus=1,
        target_armor_class=10,
        damage_dice="1d4",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                "B",
                1,
                "1d4",
                1,
                attack_id="b",
                trigger_type="after_success",
                trigger_source_attack_id="a",
            ),
            AttackProfile("A", 1, "1d4", 1, attack_id="a"),
        ),
    )
    with pytest.raises(ValueError, match="cannot trigger itself"):
        run_damage_simulations(
            attack_bonus=1,
            target_armor_class=10,
            damage_dice="1d4",
            rounds=1,
            simulations=1,
            attack_profiles=(
                AttackProfile(
                    "A",
                    1,
                    "1d4",
                    1,
                    attack_id="a",
                    trigger_type="after_success",
                    trigger_source_attack_id="a",
                ),
            ),
        )
    with pytest.raises(ValueError, match="cycle|earlier"):
        run_damage_simulations(
            attack_bonus=1,
            target_armor_class=10,
            damage_dice="1d4",
            rounds=1,
            simulations=1,
            attack_profiles=(
                AttackProfile(
                    "A",
                    1,
                    "1d4",
                    1,
                    attack_id="a",
                    trigger_type="after_success",
                    trigger_source_attack_id="b",
                ),
                AttackProfile(
                    "B",
                    1,
                    "1d4",
                    1,
                    attack_id="b",
                    trigger_type="after_success",
                    trigger_source_attack_id="a",
                ),
            ),
        )


def test_triggered_attack_can_trigger_later_attack_without_double_counting() -> None:
    rng = PredictableRng([10, 1, 10, 1, 10, 1])
    result = run_damage_simulations(
        attack_bonus=20,
        target_armor_class=15,
        damage_dice="1d4",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile("A", 20, "1d4", 1, attack_id="a"),
            AttackProfile(
                "B",
                20,
                "1d4",
                1,
                attack_id="b",
                trigger_type="after_success",
                trigger_source_attack_id="a",
            ),
            AttackProfile(
                "C",
                20,
                "1d4",
                1,
                attack_id="c",
                trigger_type="after_success",
                trigger_source_attack_id="b",
            ),
        ),
        rng=rng,
    )
    assert [r.total_profile_uses for r in result.attack_profile_results] == [1, 1, 1]
    assert result.total_attacks_made == 3


def test_new_trigger_frequencies_success_failure_and_critical_validation() -> None:
    from dnd_combat_simulator.combat import ResolutionType
    from dnd_combat_simulator.simulation import (
        AttackProfile,
        BuildConfig,
        ScenarioConfig,
        TriggerFrequency,
        TriggerType,
        run_damage_simulations,
        simulate_build,
    )

    profiles = (
        AttackProfile("Source", 99, "1", 3, attack_id="src"),
        AttackProfile(
            "Every",
            None,
            "1",
            1,
            attack_id="every",
            resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            trigger_type=TriggerType.AFTER_SUCCESS,
            trigger_source_attack_id="src",
            trigger_frequency=TriggerFrequency.PER_SUCCESS,
        ),
        AttackProfile(
            "Round",
            None,
            "1",
            1,
            attack_id="round",
            resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            trigger_type=TriggerType.AFTER_SUCCESS,
            trigger_source_attack_id="src",
            trigger_frequency=TriggerFrequency.ONCE_PER_ROUND,
        ),
        AttackProfile(
            "Combat",
            None,
            "1",
            1,
            attack_id="combat",
            resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            trigger_type=TriggerType.AFTER_SUCCESS,
            trigger_source_attack_id="src",
            trigger_frequency=TriggerFrequency.ONCE_PER_COMBAT,
        ),
    )
    result = run_damage_simulations(
        attack_bonus=1,
        target_armor_class=-100,
        damage_dice="1",
        rounds=2,
        simulations=1,
        attack_profiles=profiles,
        rng=PredictableRng([10, 10, 10, 10, 10, 10]),
    )
    by_id = {
        r.attack_profile.attack_id: r.triggered_profile_uses
        for r in result.attack_profile_results
    }
    assert by_id == {"src": 0, "every": 6, "round": 2, "combat": 1}

    with pytest.raises(
        ValueError, match="critical-hit trigger source must use attack rolls"
    ):
        simulate_build(
            BuildConfig(
                "Bad crit",
                1,
                "1d1",
                1,
                attack_profiles=(
                    AttackProfile(
                        "Save source",
                        None,
                        "1d1",
                        1,
                        attack_id="save",
                        resolution_type=ResolutionType.SAVING_THROW,
                        save_dc=99,
                    ),
                    AttackProfile(
                        "Crit dep",
                        1,
                        "1d1",
                        1,
                        attack_id="crit",
                        trigger_type=TriggerType.AFTER_CRITICAL,
                        trigger_source_attack_id="save",
                    ),
                ),
            ),
            ScenarioConfig(1, 1, 1),
            seed=1,
        )


def test_chromatic_orb_five_attacks_round_one_reports_individual_damage() -> None:
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=1,
        damage_dice="1",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                "Chromatic Orb",
                None,
                "6",
                5,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
        ),
    )

    round_one = result.round_results[0]
    assert round_one.average_targets_affected == pytest.approx(5)
    assert round_one.average_damage == 30
    assert round_one.average_individual_damage == pytest.approx(6)
    assert result.average_damage_per_target_per_round == pytest.approx(6)


def test_profile_average_executions_include_triggered_and_normal_uses() -> None:
    result = run_damage_simulations(
        attack_bonus=20,
        target_armor_class=1,
        damage_dice="1",
        rounds=2,
        simulations=1,
        attack_profiles=(
            AttackProfile("Strike", 20, "1", 1, attack_id="a"),
            AttackProfile(
                "Rider",
                None,
                "1",
                1,
                attack_id="b",
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                trigger_type="after_success",
                trigger_source_attack_id="a",
                trigger_frequency="per_success",
            ),
        ),
        rng=PredictableRng([10, 10]),
    )

    strike, rider = result.attack_profile_results
    assert strike.average_executions_per_combat == 2
    assert strike.average_executions_per_round == 1
    assert rider.average_executions_per_combat == 2
    assert rider.average_executions_per_round == 1


def test_configured_profile_that_never_executes_has_zero_execution_averages() -> None:
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=1,
        damage_dice="1",
        rounds=2,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                "Inactive",
                None,
                "1",
                1,
                active_rounds="3",
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
        ),
    )

    profile_result = result.attack_profile_results[0]
    assert profile_result.total_profile_uses == 0
    assert profile_result.average_executions_per_combat == 0
    assert profile_result.average_executions_per_round == 0
    assert result.average_damage_per_target_per_round == 0


def test_build_comparison_keeps_target_damage_averages_independent() -> None:
    comparison = compare_builds(
        first_build=BuildConfig(
            "Build A",
            0,
            "1",
            1,
            attack_profiles=(
                AttackProfile(
                    "Wide",
                    None,
                    "4",
                    1,
                    affected_targets=2,
                    resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                ),
            ),
        ),
        second_build=BuildConfig(
            "Build B",
            0,
            "1",
            1,
            attack_profiles=(
                AttackProfile(
                    "Focused",
                    None,
                    "9",
                    1,
                    resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                ),
            ),
        ),
        scenario=ScenarioConfig(target_armor_class=1, rounds=1, simulations=1),
        seed=1,
    )

    assert comparison.first_result.average_damage_per_target_per_round == 4
    assert comparison.first_result.round_results[0].average_targets_affected == 2
    assert comparison.second_result.average_damage_per_target_per_round == 9
    assert comparison.second_result.round_results[0].average_targets_affected == 1


def test_comparison_difference_uses_absolute_target_resolution_gap() -> None:
    comparison = compare_builds(
        first_build=BuildConfig(
            "Build A",
            0,
            "1",
            1,
            attack_profiles=(
                AttackProfile(
                    "Wide",
                    None,
                    "4",
                    1,
                    affected_targets=2,
                    resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                ),
            ),
        ),
        second_build=BuildConfig(
            "Build B",
            0,
            "1",
            1,
            attack_profiles=(
                AttackProfile(
                    "Focused",
                    None,
                    "7",
                    1,
                    resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                ),
            ),
        ),
        scenario=ScenarioConfig(target_armor_class=1, rounds=1, simulations=1),
        seed=1,
    )

    assert comparison.higher_average_damage_build_name == "Build A"
    assert comparison.difference.average_damage_per_round == 1
    assert comparison.difference.average_damage_per_target_per_round == 3
    assert comparison.difference.average_damage_per_target_per_round > 0


def test_comparison_difference_uses_absolute_target_gap_when_build_b_higher() -> None:
    comparison = compare_builds(
        first_build=BuildConfig(
            "Build A",
            0,
            "1",
            1,
            attack_profiles=(
                AttackProfile(
                    "Focused",
                    None,
                    "7",
                    1,
                    resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                ),
            ),
        ),
        second_build=BuildConfig(
            "Build B",
            0,
            "1",
            1,
            attack_profiles=(
                AttackProfile(
                    "Wide",
                    None,
                    "4",
                    1,
                    affected_targets=2,
                    resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                ),
            ),
        ),
        scenario=ScenarioConfig(target_armor_class=1, rounds=1, simulations=1),
        seed=1,
    )

    assert comparison.higher_average_damage_build_name == "Build B"
    assert comparison.difference.average_damage_per_round == 1
    assert comparison.difference.average_damage_per_target_per_round == 3
    assert comparison.difference.average_damage_per_target_per_round > 0


def test_comparison_tied_dpr_uses_build_a_as_difference_baseline() -> None:
    comparison = compare_builds(
        first_build=BuildConfig(
            "Build A",
            0,
            "1",
            1,
            attack_profiles=(
                AttackProfile(
                    "Wide",
                    None,
                    "4",
                    1,
                    affected_targets=2,
                    resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                ),
            ),
        ),
        second_build=BuildConfig(
            "Build B",
            0,
            "1",
            1,
            attack_profiles=(
                AttackProfile(
                    "Focused",
                    None,
                    "8",
                    1,
                    resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                ),
            ),
        ),
        scenario=ScenarioConfig(target_armor_class=1, rounds=1, simulations=1),
        seed=1,
    )

    assert comparison.higher_average_damage_build_name is None
    assert comparison.difference.average_damage_per_round == 0
    assert comparison.difference.average_damage_per_target_per_round == 4


def test_round_result_average_individual_damage_is_compatibility_alias() -> None:
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=1,
        damage_dice="3",
        rounds=1,
        simulations=1,
        attack_profiles=(
            AttackProfile(
                "Damage",
                None,
                "3",
                1,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
        ),
        rng=Random(1),
    )

    round_result = result.round_results[0]
    assert round_result.average_damage_per_target_resolution == 3
    assert round_result.average_individual_damage == 3


def test_round_result_rejects_conflicting_compatibility_alias_values() -> None:
    with pytest.raises(ValueError, match="cannot conflict"):
        RoundResult(
            1,
            1,
            1,
            0,
            0,
            average_damage_per_target_resolution=1,
            average_individual_damage=2,
        )


def _sometimes_profile(percent: int | None = 100) -> AttackProfile:
    return AttackProfile(
        name="sometimes",
        attack_bonus=None,
        damage_dice="1",
        attacks_per_round=99,
        resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
        attack_id="sometimes",
        trigger_type=TriggerType.SOMETIMES,
        trigger_chance_percent=percent,
    )


def test_sometimes_successful_check_executes_once_per_round_and_can_repeat() -> None:
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        damage_dice="1",
        rounds=2,
        simulations=1,
        attack_profiles=(_sometimes_profile(100),),
        rng=Random(1),
    )

    assert result.total_attacks_made == 2
    assert [round_result.average_attacks for round_result in result.round_results] == [
        1,
        1,
    ]
    assert result.attack_profile_results[0].triggered_profile_uses == 2


def test_sometimes_failed_check_does_not_execute_or_count_as_miss() -> None:
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        damage_dice="1",
        rounds=1,
        simulations=1,
        attack_profiles=(_sometimes_profile(1),),
        rng=Random(0),
    )

    assert result.total_attacks_made == 0
    assert result.attack_profile_results[0].triggered_profile_uses == 0
    assert result.hit_rate == 0
    assert result.failed_save_rate == 0


def test_sometimes_checks_are_independent_across_combats_and_seed_reproducible() -> (
    None
):
    kwargs = dict(
        attack_bonus=0,
        target_armor_class=10,
        damage_dice="1",
        rounds=1,
        simulations=4,
        attack_profiles=(_sometimes_profile(50),),
    )

    first = run_damage_simulations(**kwargs, rng=Random(1))
    second = run_damage_simulations(**kwargs, rng=Random(1))

    assert first.total_attacks_made == 2
    assert [r.total_attacks_made for r in first.attack_profile_results] == [2]
    assert second.total_attacks_made == first.total_attacks_made
    assert second.average_total_damage == first.average_total_damage


@pytest.mark.parametrize("percent", [None, 0, -1, 101])
def test_sometimes_invalid_percentages_prevent_simulation(percent: int | None) -> None:
    with pytest.raises(ValueError, match="Sometimes percentage chance"):
        run_damage_simulations(
            attack_bonus=0,
            target_armor_class=10,
            damage_dice="1",
            rounds=1,
            simulations=1,
            attack_profiles=(_sometimes_profile(percent),),
            rng=Random(1),
        )


def _optimized_regression_cases():
    return [
        pytest.param(
            [AttackProfile("normal", 10, "1d4", 2)],
            [10, 2, 20, 1, 2],
            {},
            {"damage": 5, "executions": 2, "resolutions": 2, "calls": []},
            id="normal-attack-and-critical-hit",
        ),
        pytest.param(
            [
                AttackProfile(
                    "elven",
                    5,
                    "1d4",
                    1,
                    attack_roll_mode=AttackRollMode.ADVANTAGE,
                    features=frozenset({AttackFeature.ELVEN_ACCURACY}),
                )
            ],
            [2, 3, 18, 4],
            {},
            {"damage": 4, "executions": 1, "resolutions": 1, "calls": []},
            id="advantage-elven-accuracy",
        ),
        pytest.param(
            [
                AttackProfile(
                    "reroll-damage",
                    20,
                    "1d6",
                    1,
                    features=frozenset(
                        {
                            AttackFeature.GREAT_WEAPON_FIGHTING,
                            AttackFeature.TAVERN_BRAWLER,
                        }
                    ),
                )
            ],
            [10, 1, 2],
            {},
            {"damage": 3, "executions": 1, "resolutions": 1, "calls": []},
            id="great-weapon-fighting-tavern-brawler",
        ),
        pytest.param(
            [
                AttackProfile(
                    "cantrip",
                    None,
                    "1d8",
                    1,
                    resolution_type=ResolutionType.SAVING_THROW,
                    save_dc=10,
                    features=frozenset({AttackFeature.POTENT_CANTRIP}),
                )
            ],
            [20, 8],
            {"enemy_save_bonus": 0},
            {"damage": 4, "executions": 1, "resolutions": 1, "calls": []},
            id="potent-cantrip-successful-save",
        ),
        pytest.param(
            [
                AttackProfile(
                    "save",
                    None,
                    "1d6",
                    1,
                    resolution_type=ResolutionType.SAVING_THROW,
                    save_dc=15,
                )
            ],
            [4, 5],
            {"enemy_save_bonus": 0},
            {"damage": 5, "executions": 1, "resolutions": 1, "calls": []},
            id="single-target-saving-throw",
        ),
        pytest.param(
            [
                AttackProfile(
                    "multi-save",
                    None,
                    "1d6",
                    1,
                    affected_targets=2,
                    resolution_type=ResolutionType.SAVING_THROW,
                    save_dc=15,
                )
            ],
            [5, 4, 18],
            {"enemy_save_bonus": 0},
            {"damage": 5, "executions": 1, "resolutions": 2, "calls": []},
            id="multi-target-saving-throw",
        ),
        pytest.param(
            [
                AttackProfile(
                    "half-save",
                    None,
                    "1d6",
                    1,
                    resolution_type=ResolutionType.SAVING_THROW,
                    save_dc=10,
                    successful_save_damage=SuccessfulSaveDamage.HALF_DAMAGE,
                )
            ],
            [20, 5],
            {"enemy_save_bonus": 0},
            {"damage": 2, "executions": 1, "resolutions": 1, "calls": []},
            id="half-damage-on-save",
        ),
        pytest.param(
            [
                AttackProfile(
                    "auto",
                    None,
                    "1d4",
                    1,
                    resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                )
            ],
            [3],
            {},
            {"damage": 3, "executions": 1, "resolutions": 1, "calls": []},
            id="automatic-damage",
        ),
        pytest.param(
            [
                AttackProfile(
                    "stop", 0, "1", 3, features=frozenset({AttackFeature.STOP_ON_MISS})
                )
            ],
            [2],
            {},
            {"damage": 0, "executions": 1, "resolutions": 1, "skipped": 2, "calls": []},
            id="stop-on-miss",
        ),
        pytest.param(
            [
                AttackProfile("source", 20, "1", 1, attack_id="source"),
                AttackProfile(
                    "round-trigger",
                    None,
                    "1",
                    1,
                    resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                    attack_id="round",
                    trigger_type=TriggerType.AFTER_SUCCESS,
                    trigger_source_attack_id="source",
                    trigger_frequency=TriggerFrequency.ONCE_PER_ROUND,
                ),
                AttackProfile(
                    "combat-trigger",
                    None,
                    "1",
                    1,
                    resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                    attack_id="combat",
                    trigger_type=TriggerType.AFTER_SUCCESS,
                    trigger_source_attack_id="source",
                    trigger_frequency=TriggerFrequency.ONCE_PER_COMBAT,
                ),
            ],
            [10, 10],
            {"rounds": 2},
            {
                "damage": 5,
                "executions": 5,
                "resolutions": 5,
                "triggered": 3,
                "calls": [],
            },
            id="once-per-round-and-combat-triggers-multiple-rounds",
        ),
        pytest.param(
            [
                AttackProfile(
                    "sometimes",
                    None,
                    "1",
                    1,
                    resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                    trigger_type=TriggerType.SOMETIMES,
                    trigger_chance_percent=50,
                )
            ],
            [50],
            {},
            {
                "damage": 1,
                "executions": 1,
                "resolutions": 1,
                "triggered": 1,
                "calls": [],
            },
            id="sometimes-trigger",
        ),
        pytest.param(
            [
                AttackProfile(
                    "resource",
                    None,
                    "1",
                    2,
                    resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                    resource_costs=(ResourceCost("ki", 1),),
                )
            ],
            [],
            {"managed_resources": (ManagedResource("ki", "Ki", 1),)},
            {
                "damage": 1,
                "executions": 1,
                "resolutions": 1,
                "skipped": 1,
                "resource": 1,
                "calls": [],
            },
            id="resource-blocked-execution",
        ),
        pytest.param(
            [
                AttackProfile(
                    "compound",
                    None,
                    "1d4+1d4!4",
                    1,
                    resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
                )
            ],
            [2, 4, 3],
            {},
            {"damage": 9, "executions": 1, "resolutions": 1, "calls": []},
            id="compound-and-exploding-damage-expression",
        ),
    ]


@pytest.mark.parametrize(
    ("profiles", "rolls", "options", "expected"), _optimized_regression_cases()
)
def test_run_damage_simulations_optimized_engine_regression_matrix(
    profiles, rolls, options, expected
) -> None:
    rng = PredictableRng(list(rolls))
    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        damage_dice="1",
        rounds=options.get("rounds", 1),
        simulations=1,
        enemy_save_bonus=options.get("enemy_save_bonus", 0),
        attack_profiles=tuple(profiles),
        rng=rng,
        managed_resources=options.get("managed_resources", ()),
    )

    assert result.average_total_damage_per_simulation == expected["damage"]
    assert result.total_attacks_made == expected["executions"]
    assert result.total_target_resolutions == expected["resolutions"]
    assert result.triggered_profile_uses == expected.get("triggered", 0)
    assert result.total_skipped_profile_uses == expected.get("skipped", 0)
    if "resource" in expected:
        assert (
            result.resource_usage_results[0].average_consumed_per_combat
            == expected["resource"]
        )
    assert rng.rolls == expected["calls"]


def test_build_math_defaults_do_not_affect_simulation_results_or_comparison() -> None:
    from dataclasses import replace

    from dnd_combat_simulator.build_math import BuildMathDefaults

    profile = AttackProfile("Strike", 5, "1d8+3", 1, attack_id="strike")
    base = BuildConfig(
        name="Build",
        attack_bonus=5,
        damage_dice="1d8+3",
        attacks_per_round=1,
        attack_profiles=(profile,),
    )
    custom_defaults = BuildMathDefaults(5, 4, 2, 1)
    custom = replace(base, math_defaults=custom_defaults)
    scenario = ScenarioConfig(15, 3, 20)

    assert simulate_build(base, scenario, seed=42) == simulate_build(
        custom, scenario, seed=42
    )

    comparison = compare_builds(
        first_build=custom,
        second_build=replace(
            base, name="Other", math_defaults=BuildMathDefaults(-1, 0, -2, -4)
        ),
        scenario=scenario,
        seed=42,
    )
    assert comparison.first_build.math_defaults == custom_defaults
    assert comparison.second_build.math_defaults != comparison.first_build.math_defaults


def test_build_math_defaults_do_not_change_simulation_behavior_or_rng() -> None:
    profile = AttackProfile(
        name="Resource trigger",
        attack_bonus=7,
        damage_dice="1d6+2",
        attacks_per_round=1,
        attack_id="resource-trigger",
        trigger_type=TriggerType.SOMETIMES,
        trigger_frequency=TriggerFrequency.ONCE_PER_ROUND,
        trigger_chance_percent=50,
        resource_costs=(ResourceCost("focus", 1),),
    )
    resources = (ManagedResource("focus", "Focus", 2),)
    scenario = ScenarioConfig(
        target_armor_class=15,
        enemy_save_bonus=2,
        rounds=3,
        simulations=25,
        managed_resources=resources,
    )
    base = BuildConfig("Manual", 7, "1d6+2", 1, attack_profiles=(profile,))
    edited = BuildConfig(
        "Manual",
        7,
        "1d6+2",
        1,
        attack_profiles=(profile,),
        math_defaults=BuildMathDefaults(5, 4, 1, 1),
    )

    assert base.math_defaults != edited.math_defaults
    assert base.resolved_attack_profiles() == edited.resolved_attack_profiles()
    assert base.resolved_attack_profiles()[0].attack_bonus == 7

    assert simulate_build(base, scenario, seed=1234) == simulate_build(
        edited, scenario, seed=1234
    )

    rng_a = Random(1234)
    rng_b = Random(1234)
    result_a = run_damage_simulations(
        attack_bonus=base.attack_bonus,
        target_armor_class=scenario.target_armor_class,
        enemy_save_bonus=scenario.enemy_save_bonus,
        damage_dice=base.damage_dice,
        rounds=scenario.rounds,
        simulations=scenario.simulations,
        attacks_per_round=base.attacks_per_round,
        attack_profiles=base.resolved_attack_profiles(),
        rng=rng_a,
        managed_resources=scenario.managed_resources,
    )
    result_b = run_damage_simulations(
        attack_bonus=edited.attack_bonus,
        target_armor_class=scenario.target_armor_class,
        enemy_save_bonus=scenario.enemy_save_bonus,
        damage_dice=edited.damage_dice,
        rounds=scenario.rounds,
        simulations=scenario.simulations,
        attacks_per_round=edited.attacks_per_round,
        attack_profiles=edited.resolved_attack_profiles(),
        rng=rng_b,
        managed_resources=scenario.managed_resources,
    )
    assert result_a == result_b
    assert rng_a.getstate() == rng_b.getstate()
    assert result_a.resource_usage_results == result_b.resource_usage_results


def test_stage44_resolves_build_inheritance_without_mutating_profile() -> None:
    from dnd_combat_simulator.simulation import resolve_attack_profile_values

    profile = AttackProfile(
        name="Inherited",
        attack_bonus=1,
        damage_dice=" 2d6+1 ",
        attacks_per_round=1,
        use_build_attack_bonus=True,
    )
    resolved = resolve_attack_profile_values(
        profile,
        BuildMathDefaults(
            ability_modifier=4,
            proficiency_bonus=3,
            attack_bonus_adjustment=2,
        ),
    )

    assert resolved.attack_bonus == 9
    assert resolved.save_dc is None
    assert resolved.damage_formula == "2d6+1"
    assert profile.attack_bonus == 1
    assert profile.damage_dice == " 2d6+1 "


def test_stage44_inherited_attack_bonus_and_damage_match_manual_effective_values() -> (
    None
):
    manual = AttackProfile(
        name="Manual",
        attack_bonus=5,
        damage_dice="1d8+3",
        attacks_per_round=1,
    )
    inherited = AttackProfile(
        name="Manual",
        attack_bonus=-10,
        damage_dice="1d8+3",
        attacks_per_round=1,
        use_build_attack_bonus=True,
    )
    kwargs = dict(
        attack_bonus=0,
        target_armor_class=12,
        damage_dice="1d4",
        rounds=3,
        simulations=50,
        rng=Random(42),
    )

    manual_result = run_damage_simulations(attack_profiles=(manual,), **kwargs)
    kwargs["rng"] = Random(42)
    inherited_result = run_damage_simulations(
        attack_profiles=(inherited,),
        math_defaults=BuildMathDefaults(),
        **kwargs,
    )

    assert inherited_result == manual_result


def test_stage44_multi_target_saving_throw_uses_inherited_save_dc() -> None:
    profile = AttackProfile(
        name="Blast",
        attack_bonus=None,
        damage_dice="4",
        attacks_per_round=1,
        affected_targets=2,
        resolution_type=ResolutionType.SAVING_THROW,
        save_dc=1,
        use_build_save_dc=True,
    )

    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        enemy_save_bonus=0,
        damage_dice="1",
        rounds=1,
        simulations=1,
        attack_profiles=(profile,),
        rng=PredictableRng([4, 2, 14]),
        math_defaults=BuildMathDefaults(
            ability_modifier=10,
            proficiency_bonus=0,
            save_dc_adjustment=0,
        ),
    )

    assert result.failed_save_rate == 1
    assert result.average_total_damage_per_simulation == 8


def test_stage44_build_damage_modifier_is_not_doubled_on_critical_hit() -> None:
    profile = AttackProfile(
        name="Crit",
        attack_bonus=99,
        damage_dice="1d8+3",
        attacks_per_round=1,
    )

    result = run_damage_simulations(
        attack_bonus=0,
        target_armor_class=10,
        damage_dice="1",
        rounds=1,
        simulations=1,
        attack_profiles=(profile,),
        rng=PredictableRng([20, 4, 5]),
        math_defaults=BuildMathDefaults(ability_modifier=3),
    )

    assert result.critical_hit_rate == 1
    assert result.average_total_damage_per_simulation == 12


def test_stage44_inheritance_fields_require_real_booleans() -> None:
    with pytest.raises(ValueError, match="use_build_attack_bonus must be a boolean"):
        AttackProfile(
            name="Bad",
            attack_bonus=1,
            damage_dice="1d4",
            attacks_per_round=1,
            use_build_attack_bonus=1,  # type: ignore[arg-type]
        )
