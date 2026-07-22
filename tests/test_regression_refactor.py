from random import Random

import pytest

from dnd_combat_simulator.combat import ResolutionType, SuccessfulSaveDamage
from dnd_combat_simulator.dice import (
    parse_damage_expression,
    roll_compiled_damage_expression,
    roll_damage_formula_breakdown,
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


class RecordingRandom(Random):
    def __init__(self, seed: int) -> None:
        super().__init__(seed)
        self.calls: list[tuple[int, int]] = []

    def randint(self, a: int, b: int) -> int:
        self.calls.append((a, b))
        return super().randint(a, b)


@pytest.mark.parametrize(
    ("formula", "critical", "features"),
    [
        ("7", False, frozenset()),
        ("1d6", False, frozenset()),
        ("1d6+2d4", False, frozenset()),
        ("2d6+3", False, frozenset()),
        ("2d6-3", False, frozenset()),
        ("1d8+2", True, frozenset()),
        ("2d8r8", False, frozenset()),
        ("2d8r<2", False, frozenset()),
        ("1d6!", False, frozenset()),
        ("1d6!3", False, frozenset()),
        ("1d6!>4", False, frozenset()),
        ("4d6kh3", False, frozenset()),
        ("4d6kl2", False, frozenset()),
        ("4d6dh1", False, frozenset()),
        ("4d6dl1", False, frozenset()),
        ("4d6", False, frozenset({"great_weapon_fighting"})),
        ("4d6", False, frozenset({"tavern_brawler"})),
        (
            "4d6",
            False,
            frozenset({"great_weapon_fighting", "tavern_brawler"}),
        ),
        (
            "4d6r<2!kh3+2d8dl1-1d4+4",
            True,
            frozenset({"great_weapon_fighting", "tavern_brawler"}),
        ),
    ],
)
@pytest.mark.parametrize("seed", range(5))
def test_compiled_damage_expression_matches_independent_breakdown(
    formula: str, critical: bool, features: frozenset[str], seed: int
) -> None:
    expression = parse_damage_expression(formula)
    fast_rng = RecordingRandom(seed)
    detailed_rng = RecordingRandom(seed)

    assert (
        roll_compiled_damage_expression(
            expression, critical=critical, rng=fast_rng, features=features
        )
        == roll_damage_formula_breakdown(
            formula, critical=critical, rng=detailed_rng, features=features
        ).total
    )
    assert fast_rng.calls == detailed_rng.calls


def test_run_damage_simulations_parses_each_profile_damage_once(monkeypatch):
    import dnd_combat_simulator.simulation as simulation

    original = simulation.parse_damage_expression
    parsed: list[str] = []

    def counting_parse(text: str):
        parsed.append(text)
        return original(text)

    monkeypatch.setattr(simulation, "parse_damage_expression", counting_parse)

    run_damage_simulations(
        attack_bonus=7,
        target_armor_class=15,
        damage_dice="1d8+4",
        rounds=3,
        simulations=5,
        attack_profiles=(
            AttackProfile("Strike", 7, "1d8+4", 2),
            AttackProfile(
                "Burst",
                None,
                "2d6",
                1,
                resolution_type=ResolutionType.AUTOMATIC_DAMAGE,
            ),
        ),
        rng=Random(1),
    )

    assert parsed == ["1d8+4", "2d6"]
