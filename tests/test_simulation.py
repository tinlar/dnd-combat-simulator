import pytest

from dnd_combat_simulator.combat import AttackRollMode
from dnd_combat_simulator.simulation import (
    BuildConfig,
    ComparisonDifference,
    ScenarioConfig,
    SimulationResult,
    compare_builds,
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
        damage_dice="1d6",
        damage_modifier=2,
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
        damage_modifier=4,
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
            damage_modifier=3,
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
            damage_modifier=3,
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
            damage_modifier=3,
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
        damage_dice="1d6",
        damage_modifier=2,
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
    with pytest.raises(ValueError, match="Damage dice must not include a modifier"):
        run_damage_simulations(
            attack_bonus=5,
            target_armor_class=15,
            damage_dice="1d8+3",
            damage_modifier=0,
            rounds=1,
            simulations=1,
            rng=PredictableRng([]),
        )


def test_attack_roll_mode_applies_to_every_attack_in_simulation() -> None:
    rng = PredictableRng([1, 12, 4, 18, 7, 5])

    result = run_damage_simulations(
        attack_bonus=3,
        target_armor_class=15,
        damage_dice="1d6",
        damage_modifier=1,
        rounds=1,
        simulations=1,
        attacks_per_round=2,
        attack_roll_mode=AttackRollMode.ADVANTAGE,
        rng=rng,
    )

    assert result.attack_roll_mode is AttackRollMode.ADVANTAGE
    assert result.total_attacks_made == 2
    assert result.hit_rate == 1
    assert result.average_total_damage_per_simulation == 11
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
            damage_modifier=0,
            attacks_per_round=1,
        ),
        second_build=BuildConfig(
            name="Heavy",
            attack_bonus=20,
            damage_dice="1d4",
            damage_modifier=0,
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
            damage_modifier=4,
            attacks_per_round=1,
        ),
        second_build=BuildConfig(
            name="Greatsword",
            attack_bonus=5,
            damage_dice="1d8",
            damage_modifier=6,
            attacks_per_round=1,
        ),
        scenario=ScenarioConfig(target_armor_class=14, rounds=2, simulations=5),
        seed=99,
    )

    assert comparison.higher_average_damage_build_name == "Greatsword"
    assert comparison.difference.average_damage_per_round == pytest.approx(-1.2)
    assert comparison.difference.average_total_damage == pytest.approx(-2.4)
    assert comparison.difference.hit_rate == 0
    assert comparison.difference.critical_hit_rate == 0
