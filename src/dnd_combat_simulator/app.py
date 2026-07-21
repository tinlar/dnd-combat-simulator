"""Streamlit application entry point."""

from __future__ import annotations

from dataclasses import dataclass

from dnd_combat_simulator import APP_TITLE
from dnd_combat_simulator.combat import AttackRollMode
from dnd_combat_simulator.simulation import (
    AttackProfile,
    AttackUse,
    BuildComparisonResult,
    BuildConfig,
    RoundPlan,
    RoundSchedule,
    ScenarioConfig,
    SimulationResult,
    UndefinedRoundBehavior,
    compare_builds,
    run_damage_simulations,
)

PAGE_WIDTH_CSS = """
<style>
    .stApp .block-container {
        width: 90vw;
        max-width: 90vw;
        margin-left: auto;
        margin-right: auto;
        padding-left: clamp(1rem, 2vw, 2.5rem);
        padding-right: clamp(1rem, 2vw, 2.5rem);
        box-sizing: border-box;
    }

    @media (max-width: 640px) {
        .stApp .block-container {
            width: 100%;
            max-width: 100%;
            padding-left: 1rem;
            padding-right: 1rem;
        }
    }
</style>
"""


def configure_page() -> None:
    """Configure Streamlit to use a wide, centered application layout."""
    import streamlit as st

    st.set_page_config(page_title=APP_TITLE, page_icon="🎲", layout="wide")
    st.markdown(PAGE_WIDTH_CSS, unsafe_allow_html=True)


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
        {
            "Metric": "Round 1 burst damage",
            comparison.first_build.name: format_damage(first.first_round_burst_damage),
            comparison.second_build.name: format_damage(
                second.first_round_burst_damage
            ),
            "Difference": format_signed_damage(
                first.first_round_burst_damage - second.first_round_burst_damage
            ),
        },
        {
            "Metric": "Average damage after round 1",
            comparison.first_build.name: format_damage(
                first.average_damage_after_round_1
            ),
            comparison.second_build.name: format_damage(
                second.average_damage_after_round_1
            ),
            "Difference": format_signed_damage(
                first.average_damage_after_round_1 - second.average_damage_after_round_1
            ),
        },
        {
            "Metric": "Highest-damage round",
            comparison.first_build.name: str(first.highest_damage_round),
            comparison.second_build.name: str(second.highest_damage_round),
            "Difference": "—",
        },
    ]


def _winner_label(
    first_name: str, first_value: float, second_name: str, second_value: float
) -> str:
    if first_value > second_value:
        return first_name
    if second_value > first_value:
        return second_name
    return "Tie"


def _round_breakdown_rows(comparison: BuildComparisonResult) -> list[dict[str, str]]:
    """Build side-by-side per-round result rows."""
    rows = []
    for first_round, second_round in zip(
        comparison.first_result.round_results,
        comparison.second_result.round_results,
        strict=True,
    ):
        rows.append(
            {
                "Round": str(first_round.round_number),
                f"{comparison.first_build.name} avg damage": format_damage(
                    first_round.average_damage
                ),
                f"{comparison.second_build.name} avg damage": format_damage(
                    second_round.average_damage
                ),
                f"{comparison.first_build.name} avg attacks": format_damage(
                    first_round.average_attacks
                ),
                f"{comparison.second_build.name} avg attacks": format_damage(
                    second_round.average_attacks
                ),
                f"{comparison.first_build.name} hit %": format_rate(
                    first_round.hit_rate
                ),
                f"{comparison.second_build.name} hit %": format_rate(
                    second_round.hit_rate
                ),
                f"{comparison.first_build.name} crit %": format_rate(
                    first_round.critical_hit_rate
                ),
                f"{comparison.second_build.name} crit %": format_rate(
                    second_round.critical_hit_rate
                ),
            }
        )
    return rows


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


def _profile_breakdown_rows(result: SimulationResult) -> list[dict[str, str]]:
    """Build per-profile damage breakdown rows."""
    return [
        {
            "Attack profile": profile_result.attack_profile.name,
            "Average damage per round": format_damage(
                profile_result.average_damage_per_round
            ),
            "Average total damage": format_damage(
                profile_result.average_total_damage_per_simulation
            ),
            "Hit percentage": format_rate(profile_result.hit_rate),
            "Critical hit percentage": format_rate(profile_result.critical_hit_rate),
        }
        for profile_result in result.attack_profile_results
    ]


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
    st.markdown("##### Winners")
    st.write(
        "Round 1 burst: "
        + _winner_label(
            comparison.first_build.name,
            comparison.first_result.first_round_burst_damage,
            comparison.second_build.name,
            comparison.second_result.first_round_burst_damage,
        )
    )
    st.write(
        "Sustained damage after round 1: "
        + _winner_label(
            comparison.first_build.name,
            comparison.first_result.average_damage_after_round_1,
            comparison.second_build.name,
            comparison.second_result.average_damage_after_round_1,
        )
    )
    st.write(
        "Total average damage: "
        + _winner_label(
            comparison.first_build.name,
            comparison.first_result.average_total_damage_per_simulation,
            comparison.second_build.name,
            comparison.second_result.average_total_damage_per_simulation,
        )
    )
    st.markdown("##### Per-round damage")
    st.table(_round_breakdown_rows(comparison))
    st.markdown(f"##### {comparison.first_build.name} attack breakdown")
    st.table(_profile_breakdown_rows(comparison.first_result))
    st.markdown(f"##### {comparison.second_build.name} attack breakdown")
    st.table(_profile_breakdown_rows(comparison.second_result))
    st.caption(
        "Difference is first build minus second build. Both builds used separate "
        "random-number-generator instances initialized with the same seed."
    )


def _attack_profile_inputs(prefix: str, default_name: str) -> AttackProfile:
    """Render and collect one attack profile's input controls."""
    import streamlit as st

    attack_name = st.text_input("Attack name", value=default_name, key=f"{prefix}-name")
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
    return AttackProfile(
        name=attack_name,
        attack_bonus=int(attack_bonus),
        damage_dice=damage_dice,
        damage_modifier=int(damage_modifier),
        attacks_per_round=int(attacks_per_round),
        attack_roll_mode=AttackRollMode(attack_roll_mode_label.lower()),
    )


def _profile_definitions(
    build_prefix: str, additional_attack_count: int
) -> tuple[tuple[str, str, str], ...]:
    """Return stable key prefixes, headings, and default names for visible profiles."""
    if additional_attack_count < 0:
        msg = "Additional attack count must be at least 0."
        raise ValueError(msg)
    if additional_attack_count > 10:
        msg = "Additional attack count must be no more than 10."
        raise ValueError(msg)

    return (
        (f"{build_prefix}-primary", "Primary Attack", "Primary attack"),
        *(
            (
                f"{build_prefix}-additional-{index}",
                f"Additional Attack {index}",
                f"Additional attack {index}",
            )
            for index in range(1, additional_attack_count + 1)
        ),
    )


def _build_config_from_profiles(
    name: str,
    profiles: tuple[AttackProfile, ...],
    round_schedule: RoundSchedule | None = None,
) -> BuildConfig:
    """Create a build config with every displayed profile attached."""
    primary = profiles[0]
    return BuildConfig(
        name=name,
        attack_bonus=primary.attack_bonus,
        damage_dice=primary.damage_dice,
        damage_modifier=primary.damage_modifier,
        attacks_per_round=primary.attacks_per_round,
        attack_roll_mode=primary.attack_roll_mode,
        attack_profiles=profiles,
        round_schedule=round_schedule,
    )


def _round_schedule_inputs(
    prefix: str, profiles: tuple[AttackProfile, ...], default_rounds: int
) -> RoundSchedule:
    """Render controls that schedule reusable attack profiles by round."""
    import streamlit as st

    count_key = f"{prefix}-scheduled-round-count"
    if count_key not in st.session_state:
        st.session_state[count_key] = default_rounds

    st.markdown("##### Round Schedule")
    behavior_label = st.selectbox(
        "Undefined-round behavior",
        options=[
            "Repeat final round",
            "Repeat entire schedule",
            "No attacks",
        ],
        key=f"{prefix}-undefined-round-behavior",
    )
    behavior = {
        "Repeat final round": UndefinedRoundBehavior.REPEAT_FINAL_ROUND,
        "Repeat entire schedule": UndefinedRoundBehavior.REPEAT_ENTIRE_SCHEDULE,
        "No attacks": UndefinedRoundBehavior.NO_ATTACKS,
    }[behavior_label]

    actions = st.columns(2)
    if actions[0].button("Add a scheduled round", key=f"{prefix}-add-round"):
        st.session_state[count_key] += 1
    if actions[1].button("Remove final scheduled round", key=f"{prefix}-remove-round"):
        st.session_state[count_key] = max(1, st.session_state[count_key] - 1)

    profile_names = [profile.name for profile in profiles]
    plans = []
    for round_number in range(1, int(st.session_state[count_key]) + 1):
        st.markdown(f"Round {round_number}")
        round_prefix = f"{prefix}-round-{round_number}"
        attack_count_key = f"{round_prefix}-attack-count"
        if attack_count_key not in st.session_state:
            st.session_state[attack_count_key] = len(profiles)

        buttons = st.columns(3)
        if (
            buttons[0].button("Copy previous round", key=f"{round_prefix}-copy")
            and round_number > 1
        ):
            previous_prefix = f"{prefix}-round-{round_number - 1}"
            previous_count = int(
                st.session_state.get(f"{previous_prefix}-attack-count", 0)
            )
            st.session_state[attack_count_key] = previous_count
            for index in range(1, previous_count + 1):
                st.session_state[f"{round_prefix}-use-{index}-profile"] = (
                    st.session_state.get(
                        f"{previous_prefix}-use-{index}-profile", profile_names[0]
                    )
                )
                st.session_state[f"{round_prefix}-use-{index}-count"] = (
                    st.session_state.get(f"{previous_prefix}-use-{index}-count", 1)
                )
        if buttons[1].button("Clear round", key=f"{round_prefix}-clear"):
            st.session_state[attack_count_key] = 0
        if buttons[2].button("Add attack to round", key=f"{round_prefix}-add-attack"):
            st.session_state[attack_count_key] += 1

        uses = []
        for index in range(1, int(st.session_state[attack_count_key]) + 1):
            row = st.columns([3, 1, 1])
            profile_id = row[0].selectbox(
                "Attack profile",
                options=profile_names,
                key=f"{round_prefix}-use-{index}-profile",
            )
            count = row[1].number_input(
                "Uses",
                min_value=0,
                value=1,
                step=1,
                key=f"{round_prefix}-use-{index}-count",
            )
            if row[2].button("Remove", key=f"{round_prefix}-use-{index}-remove"):
                st.session_state[f"{round_prefix}-use-{index}-count"] = 0
                count = 0
            if int(count) > 0:
                uses.append(AttackUse(profile_id, int(count)))
        plans.append(RoundPlan(round_number, tuple(uses)))

    return RoundSchedule(tuple(plans), behavior)


def _build_inputs(prefix: str, default_name: str, default_rounds: int) -> BuildConfig:
    """Render and collect one build's input controls."""
    import streamlit as st

    st.markdown(f"#### {default_name}")
    name = st.text_input("Build name", value=default_name, key=f"{prefix}-build-name")
    additional_attack_count = st.number_input(
        "Additional Distinct Attacks",
        min_value=0,
        max_value=10,
        value=0,
        step=1,
        key=f"{prefix}-additional-attack-count",
    )

    profiles = []
    for profile_prefix, heading, default_attack_name in _profile_definitions(
        prefix, int(additional_attack_count)
    ):
        st.markdown(f"##### {heading}")
        profiles.append(_attack_profile_inputs(profile_prefix, default_attack_name))

    round_schedule = _round_schedule_inputs(prefix, tuple(profiles), default_rounds)
    return _build_config_from_profiles(name, tuple(profiles), round_schedule)


def main() -> None:
    """Render the Streamlit simulation page."""
    import streamlit as st

    configure_page()
    st.title(APP_TITLE)
    st.write(
        "Compare two named DnD combat builds against the same target Armor "
        "Class, round count, and simulation count."
    )

    st.subheader("Shared scenario")
    scenario_row = st.columns(4)
    target_armor_class = scenario_row[0].number_input(
        "Target Armor Class", min_value=1, value=15, step=1, key="scenario-target-ac"
    )
    rounds = scenario_row[1].number_input(
        "Number of rounds", min_value=1, value=5, step=1, key="scenario-rounds"
    )
    simulations = scenario_row[2].number_input(
        "Number of simulations",
        min_value=1,
        value=10_000,
        step=1,
        key="scenario-simulations",
    )
    seed = scenario_row[3].number_input(
        "Random seed", value=20240721, step=1, key="scenario-seed"
    )

    build_columns = st.columns(2)
    with build_columns[0]:
        first_build = _build_inputs("first", "Build A", int(rounds))
    with build_columns[1]:
        second_build = _build_inputs("second", "Build B", int(rounds))

    if st.button("Compare Builds"):
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
