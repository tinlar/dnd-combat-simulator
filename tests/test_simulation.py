import pytest

from dnd_combat_simulator.combat import (
    AttackRollMode,
    ResolutionType,
    SuccessfulSaveDamage,
)
from dnd_combat_simulator.simulation import (
    AttackProfile,
    BuildConfig,
    ComparisonDifference,
    ScenarioConfig,
    SimulationResult,
    compare_builds,
    parse_active_rounds,
    run_damage_simulations,
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
    assert comparison.difference.average_damage_per_round == pytest.approx(-0.6)
    assert comparison.difference.average_total_damage == pytest.approx(-1.2)
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
    assert result.average_damage_per_target_per_round == 13.5
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
