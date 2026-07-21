import pytest

from dnd_combat_simulator import APP_TITLE
from dnd_combat_simulator.app import (
    SimulationInputs,
    format_damage,
    format_rate,
    run_simulation_from_inputs,
    validate_simulation_inputs,
)
from dnd_combat_simulator.combat import AttackRollMode


def test_app_title() -> None:
    assert APP_TITLE == "DnD Combat Simulator"


def test_format_damage_uses_two_decimal_places() -> None:
    assert format_damage(12) == "12.00"
    assert format_damage(12.345) == "12.35"


def test_format_rate_uses_percentage() -> None:
    assert format_rate(0.625) == "62.50%"


@pytest.mark.parametrize(
    ("inputs", "message"),
    [
        (
            SimulationInputs(5, 15, "", 3, 5, 1, 10_000),
            "Damage dice is required",
        ),
        (
            SimulationInputs(5, 0, "1d8", 3, 5, 1, 10_000),
            "Target Armor Class must be at least 1",
        ),
        (
            SimulationInputs(5, 15, "1d8", 3, 0, 1, 10_000),
            "Number of rounds must be at least 1",
        ),
        (
            SimulationInputs(5, 15, "1d8", 3, 5, 0, 10_000),
            "Attacks per round must be at least 1",
        ),
        (
            SimulationInputs(5, 15, "1d8", 3, 5, 1, 0),
            "Number of simulations must be at least 1",
        ),
    ],
)
def test_validate_simulation_inputs_rejects_unusable_values(
    inputs: SimulationInputs, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_simulation_inputs(inputs)


def test_run_simulation_from_inputs_reuses_shared_simulation_logic() -> None:
    result = run_simulation_from_inputs(
        SimulationInputs(
            attack_bonus=5,
            target_armor_class=15,
            damage_dice=" 1d8 ",
            damage_modifier=3,
            rounds=1,
            attacks_per_round=2,
            simulations=1,
            attack_roll_mode=AttackRollMode.DISADVANTAGE,
        )
    )

    assert result.simulations_run == 1
    assert result.rounds_per_simulation == 1
    assert result.attacks_per_round == 2
    assert result.total_attacks_made == 2
    assert result.attack_roll_mode is AttackRollMode.DISADVANTAGE


def test_result_rows_show_side_by_side_comparison() -> None:
    from dnd_combat_simulator.app import (
        ComparisonInputs,
        _result_rows,
        run_comparison_from_inputs,
    )
    from dnd_combat_simulator.simulation import BuildConfig, ScenarioConfig

    comparison = run_comparison_from_inputs(
        ComparisonInputs(
            first_build=BuildConfig("Build A", 20, "1d4", 0, 1),
            second_build=BuildConfig("Build B", 20, "1d4", 1, 1),
            scenario=ScenarioConfig(target_armor_class=1, rounds=1, simulations=2),
            seed=7,
        )
    )

    rows = _result_rows(comparison)

    assert rows[0]["Metric"] == "Average damage per round"
    assert rows[0]["Build A"] == "1.50"
    assert rows[0]["Build B"] == "2.50"
    assert rows[0]["Difference"] == "-1.00"
    assert rows[2]["Metric"] == "Hit percentage"
    assert rows[2]["Difference"] == "+0.00%"


@pytest.mark.parametrize(
    ("additional_count", "expected_headings", "expected_prefixes"),
    [
        (0, ["Primary Attack"], ["build-primary"]),
        (
            1,
            ["Primary Attack", "Additional Attack 1"],
            ["build-primary", "build-additional-1"],
        ),
        (
            2,
            ["Primary Attack", "Additional Attack 1", "Additional Attack 2"],
            ["build-primary", "build-additional-1", "build-additional-2"],
        ),
        (
            3,
            [
                "Primary Attack",
                "Additional Attack 1",
                "Additional Attack 2",
                "Additional Attack 3",
            ],
            [
                "build-primary",
                "build-additional-1",
                "build-additional-2",
                "build-additional-3",
            ],
        ),
    ],
)
def test_profile_definitions_support_dynamic_additional_attacks(
    additional_count: int, expected_headings: list[str], expected_prefixes: list[str]
) -> None:
    from dnd_combat_simulator.app import _profile_definitions

    definitions = _profile_definitions("build", additional_count)

    assert [definition[0] for definition in definitions] == expected_prefixes
    assert [definition[1] for definition in definitions] == expected_headings


def test_builds_can_use_different_numbers_of_attack_profiles() -> None:
    from dnd_combat_simulator.app import _build_config_from_profiles
    from dnd_combat_simulator.simulation import (
        AttackProfile,
        ScenarioConfig,
        compare_builds,
    )

    first_profiles = (
        AttackProfile("Primary A", 20, "1d4", 0, 1),
        AttackProfile("Extra A 1", 20, "1d4", 0, 1),
        AttackProfile("Extra A 2", 20, "1d4", 0, 1),
    )
    second_profiles = (AttackProfile("Primary B", 20, "1d4", 0, 1),)

    comparison = compare_builds(
        first_build=_build_config_from_profiles("Build A", first_profiles),
        second_build=_build_config_from_profiles("Build B", second_profiles),
        scenario=ScenarioConfig(target_armor_class=1, rounds=1, simulations=1),
        seed=4,
    )

    assert len(comparison.first_build.attack_profiles) == 3
    assert len(comparison.second_build.attack_profiles) == 1
    assert comparison.first_result.total_attacks_made == 3
    assert comparison.second_result.total_attacks_made == 1
