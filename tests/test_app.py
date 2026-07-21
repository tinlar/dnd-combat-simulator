import pytest

from dnd_combat_simulator import APP_TITLE
from dnd_combat_simulator.app import (
    SimulationInputs,
    format_damage,
    format_rate,
    run_simulation_from_inputs,
    validate_simulation_inputs,
)


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
            SimulationInputs(5, 15, "", 3, 5, 10_000),
            "Damage dice is required",
        ),
        (
            SimulationInputs(5, 0, "1d8", 3, 5, 10_000),
            "Target Armor Class must be at least 1",
        ),
        (
            SimulationInputs(5, 15, "1d8", 3, 0, 10_000),
            "Number of rounds must be at least 1",
        ),
        (
            SimulationInputs(5, 15, "1d8", 3, 5, 0),
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
            simulations=1,
        )
    )

    assert result.simulations_run == 1
    assert result.rounds_per_simulation == 1
    assert result.total_attacks_made == 1
