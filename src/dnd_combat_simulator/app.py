"""Streamlit application entry point."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from dnd_combat_simulator import APP_TITLE
from dnd_combat_simulator.simulation import SimulationResult, run_damage_simulations


@dataclass(frozen=True)
class SimulationInputs:
    """Validated user inputs for a damage simulation run."""

    attack_bonus: int
    target_armor_class: int
    damage_dice: str
    damage_modifier: int
    rounds: int
    attacks_per_round: int
    simulations: int


def validate_simulation_inputs(inputs: SimulationInputs) -> None:
    """Validate Streamlit form inputs before running a simulation.

    Raises:
        ValueError: If an input cannot produce a usable damage simulation.
    """
    if not inputs.damage_dice.strip():
        msg = "Damage dice is required. Use notation such as 1d8."
        raise ValueError(msg)
    if inputs.target_armor_class < 1:
        msg = "Target Armor Class must be at least 1."
        raise ValueError(msg)
    if inputs.rounds < 1:
        msg = "Number of rounds must be at least 1."
        raise ValueError(msg)
    if inputs.attacks_per_round < 1:
        msg = "Attacks per round must be at least 1."
        raise ValueError(msg)
    if inputs.simulations < 1:
        msg = "Number of simulations must be at least 1."
        raise ValueError(msg)


def format_damage(value: float) -> str:
    """Format a damage value for display."""
    return f"{value:.2f}"


def format_rate(value: float) -> str:
    """Format a fractional rate as a percentage for display."""
    return f"{value:.2%}"


def run_simulation_from_inputs(inputs: SimulationInputs) -> SimulationResult:
    """Validate inputs and run the shared simulation engine."""
    validate_simulation_inputs(inputs)
    return run_damage_simulations(
        attack_bonus=inputs.attack_bonus,
        target_armor_class=inputs.target_armor_class,
        damage_dice=inputs.damage_dice.strip(),
        damage_modifier=inputs.damage_modifier,
        rounds=inputs.rounds,
        simulations=inputs.simulations,
        attacks_per_round=inputs.attacks_per_round,
    )


def _render_results(result: SimulationResult) -> None:
    """Render simulation results in a compact metric grid."""
    st.subheader("Results")

    first_row = st.columns(4)
    first_row[0].metric(
        "Average damage per round", format_damage(result.average_damage_per_round)
    )
    first_row[1].metric(
        "Average total damage",
        format_damage(result.average_total_damage_per_simulation),
    )
    first_row[2].metric("Hit percentage", format_rate(result.hit_rate))
    first_row[3].metric(
        "Critical hit percentage", format_rate(result.critical_hit_rate)
    )

    second_row = st.columns(3)
    second_row[0].metric(
        "Minimum total damage",
        format_damage(result.minimum_total_damage_in_simulation),
    )
    second_row[1].metric(
        "Maximum total damage",
        format_damage(result.maximum_total_damage_in_simulation),
    )
    second_row[2].metric("Total attacks simulated", f"{result.total_attacks_made:,}")


def main() -> None:
    """Render the Streamlit simulation page."""
    st.set_page_config(page_title=APP_TITLE, page_icon="🎲")
    st.title(APP_TITLE)
    st.write(
        "Estimate weapon damage over repeated combats with one or more "
        "attacks per round."
    )

    with st.form("simulation-inputs"):
        first_row = st.columns(2)
        attack_bonus = first_row[0].number_input("Attack bonus", value=5, step=1)
        target_armor_class = first_row[1].number_input(
            "Target Armor Class", min_value=1, value=15, step=1
        )

        second_row = st.columns(2)
        damage_dice = second_row[0].text_input("Damage dice", value="1d8")
        damage_modifier = second_row[1].number_input("Damage modifier", value=3, step=1)

        third_row = st.columns(3)
        rounds = third_row[0].number_input(
            "Number of rounds", min_value=1, value=5, step=1
        )
        attacks_per_round = third_row[1].number_input(
            "Attacks per round", min_value=1, value=1, step=1
        )
        simulations = third_row[2].number_input(
            "Number of simulations", min_value=1, value=10_000, step=1
        )

        submitted = st.form_submit_button("Run Simulation")

    if submitted:
        inputs = SimulationInputs(
            attack_bonus=int(attack_bonus),
            target_armor_class=int(target_armor_class),
            damage_dice=damage_dice,
            damage_modifier=int(damage_modifier),
            rounds=int(rounds),
            attacks_per_round=int(attacks_per_round),
            simulations=int(simulations),
        )
        try:
            result = run_simulation_from_inputs(inputs)
        except ValueError as error:
            st.error(str(error))
        else:
            _render_results(result)


if __name__ == "__main__":
    main()
