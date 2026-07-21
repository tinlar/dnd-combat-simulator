"""Streamlit application entry point."""

from __future__ import annotations

from dataclasses import dataclass

from dnd_combat_simulator import APP_TITLE
from dnd_combat_simulator.combat import AttackRollMode
from dnd_combat_simulator.simulation import (
    BuildComparisonResult,
    BuildConfig,
    ScenarioConfig,
    SimulationResult,
    compare_builds,
    run_damage_simulations,
)


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
    attack_roll_mode: AttackRollMode = AttackRollMode.NORMAL


@dataclass(frozen=True)
class ComparisonInputs:
    """Validated user inputs for a named build comparison."""

    first_build: BuildConfig
    second_build: BuildConfig
    scenario: ScenarioConfig
    seed: int


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


def format_signed_damage(value: float) -> str:
    """Format a signed damage delta for display."""
    return f"{value:+.2f}"


def format_signed_rate(value: float) -> str:
    """Format a signed fractional rate as a percentage-point delta."""
    return f"{value:+.2%}"


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
        attack_roll_mode=inputs.attack_roll_mode,
    )


def run_comparison_from_inputs(inputs: ComparisonInputs) -> BuildComparisonResult:
    """Validate inputs and run the shared comparison engine."""
    return compare_builds(
        first_build=inputs.first_build,
        second_build=inputs.second_build,
        scenario=inputs.scenario,
        seed=inputs.seed,
    )


def _result_rows(comparison: BuildComparisonResult) -> list[dict[str, str]]:
    """Build side-by-side display rows for comparison results."""
    first = comparison.first_result
    second = comparison.second_result
    difference = comparison.difference
    return [
        {
            "Metric": "Average damage per round",
            comparison.first_build.name: format_damage(first.average_damage_per_round),
            comparison.second_build.name: format_damage(
                second.average_damage_per_round
            ),
            "Difference": format_signed_damage(difference.average_damage_per_round),
        },
        {
            "Metric": "Average total damage",
            comparison.first_build.name: format_damage(
                first.average_total_damage_per_simulation
            ),
            comparison.second_build.name: format_damage(
                second.average_total_damage_per_simulation
            ),
            "Difference": format_signed_damage(difference.average_total_damage),
        },
        {
            "Metric": "Hit percentage",
            comparison.first_build.name: format_rate(first.hit_rate),
            comparison.second_build.name: format_rate(second.hit_rate),
            "Difference": format_signed_rate(difference.hit_rate),
        },
        {
            "Metric": "Critical hit percentage",
            comparison.first_build.name: format_rate(first.critical_hit_rate),
            comparison.second_build.name: format_rate(second.critical_hit_rate),
            "Difference": format_signed_rate(difference.critical_hit_rate),
        },
    ]


def _render_results(result: SimulationResult) -> None:
    """Render simulation results in a compact metric grid."""
    import streamlit as st

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

    st.caption(f"Attack roll mode: {result.attack_roll_mode.value.title()}")


def _render_comparison_results(comparison: BuildComparisonResult) -> None:
    """Render two build results side by side with deltas."""
    import streamlit as st

    st.subheader("Build comparison")
    if comparison.higher_average_damage_build_name is None:
        st.success("Both builds have the same average damage per round.")
    else:
        st.success(
            f"{comparison.higher_average_damage_build_name} has higher average damage."
        )
    st.table(_result_rows(comparison))
    st.caption(
        "Difference is first build minus second build. Both builds used separate "
        "random-number-generator instances initialized with the same seed."
    )


def _build_inputs(prefix: str, default_name: str) -> BuildConfig:
    """Render and collect one build's input controls."""
    import streamlit as st

    st.markdown(f"#### {default_name}")
    name = st.text_input("Build name", value=default_name, key=f"{prefix}-name")
    row_one = st.columns(2)
    attack_bonus = row_one[0].number_input(
        "Attack bonus", value=5, step=1, key=f"{prefix}-attack-bonus"
    )
    damage_dice = row_one[1].text_input(
        "Damage dice", value="1d8", key=f"{prefix}-damage-dice"
    )
    row_two = st.columns(3)
    damage_modifier = row_two[0].number_input(
        "Damage modifier", value=3, step=1, key=f"{prefix}-damage-modifier"
    )
    attacks_per_round = row_two[1].number_input(
        "Attacks per round", min_value=1, value=1, step=1, key=f"{prefix}-attacks"
    )
    attack_roll_mode_label = row_two[2].selectbox(
        "Attack roll mode",
        options=[mode.value.title() for mode in AttackRollMode],
        index=0,
        key=f"{prefix}-mode",
    )
    return BuildConfig(
        name=name,
        attack_bonus=int(attack_bonus),
        damage_dice=damage_dice,
        damage_modifier=int(damage_modifier),
        attacks_per_round=int(attacks_per_round),
        attack_roll_mode=AttackRollMode(attack_roll_mode_label.lower()),
    )


def main() -> None:
    """Render the Streamlit simulation page."""
    import streamlit as st

    st.set_page_config(page_title=APP_TITLE, page_icon="🎲")
    st.title(APP_TITLE)
    st.write(
        "Compare two named DnD combat builds against the same target Armor "
        "Class, round count, and simulation count."
    )

    with st.form("comparison-inputs"):
        st.subheader("Shared scenario")
        scenario_row = st.columns(4)
        target_armor_class = scenario_row[0].number_input(
            "Target Armor Class", min_value=1, value=15, step=1
        )
        rounds = scenario_row[1].number_input(
            "Number of rounds", min_value=1, value=5, step=1
        )
        simulations = scenario_row[2].number_input(
            "Number of simulations", min_value=1, value=10_000, step=1
        )
        seed = scenario_row[3].number_input("Random seed", value=20240721, step=1)

        build_columns = st.columns(2)
        with build_columns[0]:
            first_build = _build_inputs("first", "Build A")
        with build_columns[1]:
            second_build = _build_inputs("second", "Build B")

        submitted = st.form_submit_button("Compare Builds")

    if submitted:
        inputs = ComparisonInputs(
            first_build=first_build,
            second_build=second_build,
            scenario=ScenarioConfig(
                target_armor_class=int(target_armor_class),
                rounds=int(rounds),
                simulations=int(simulations),
            ),
            seed=int(seed),
        )
        try:
            comparison = run_comparison_from_inputs(inputs)
        except ValueError as error:
            st.error(str(error))
        else:
            _render_comparison_results(comparison)


if __name__ == "__main__":
    main()
