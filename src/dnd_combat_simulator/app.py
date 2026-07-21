"""Streamlit application entry point."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from textwrap import dedent

from dnd_combat_simulator import APP_TITLE
from dnd_combat_simulator.combat import (
    AttackFeature,
    AttackRollMode,
    ResolutionType,
    SuccessfulSaveDamage,
)
from dnd_combat_simulator.simulation import (
    AttackProfile,
    AttackProfileResult,
    BuildComparisonResult,
    BuildConfig,
    ScenarioConfig,
    SimulationResult,
    compare_builds,
    run_damage_simulations,
    simulate_build,
)

FEATURE_LABELS = {
    AttackFeature.ELVEN_ACCURACY: "Elven Accuracy",
    AttackFeature.GREAT_WEAPON_FIGHTING: "Great Weapon Fighting",
    AttackFeature.TAVERN_BRAWLER: "Tavern Brawler",
}

FEATURE_HELP = {
    AttackFeature.ELVEN_ACCURACY: (
        "When this profile makes an eligible Dexterity, Intelligence, Wisdom, or "
        "Charisma attack with Advantage, reroll one of the two d20s once. The "
        "lower die is rerolled and the highest remaining result is used."
    ),
    AttackFeature.GREAT_WEAPON_FIGHTING: (
        "Whenever this profile rolls a damage die, treat a result of 1 or 2 as a "
        "3. This changes the die's damage contribution but does not change its "
        "natural face for exploding-die checks."
    ),
    AttackFeature.TAVERN_BRAWLER: (
        "Whenever this profile rolls a damage die and the accepted result is 1, "
        "reroll that die once. The replacement result must be used, even if it "
        "is another 1."
    ),
}

FEATURE_ORDER = (
    AttackFeature.ELVEN_ACCURACY,
    AttackFeature.GREAT_WEAPON_FIGHTING,
    AttackFeature.TAVERN_BRAWLER,
)

DAMAGE_FORMULA_HELP = dedent(
    """
    **Basic**

    - `1d8`
    - `2d6+4`
    - `1d10-1`

    **Reroll**

    - `2d8r<2` — reroll 1s and 2s
    - `2d8r8` — reroll 8s
    - `2d8r1r3r5r7` — reroll odd results

    **Exploding**

    - `3d6!` — explode on 6
    - `3d6!>4` — explode on 4, 5, or 6
    - `3d6!3` — explode only on 3

    **Keep or drop**

    - `4d6kh3` — keep highest 3
    - `4d6kl3` — keep lowest 3
    - `8d100dl3` — drop lowest 3
    - `8d100dh3` — drop highest 3

    **Combined**

    - `4d6r1!kh3+2`

    **Processing order**

    Formula rerolls, Tavern Brawler, explosion checks, Great Weapon Fighting
    damage contribution, keep/drop, then apply the modifier.
    """
).strip()

DAMAGE_FORMULA_PLACEHOLDER = "Examples: 1d8+4, 3d6!, 3d6!>4, 4d6kh3+2, 8d100dh3."

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

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 14px;
        border-color: rgba(128, 128, 128, 0.28);
        box-shadow: 0 0.25rem 0.8rem rgba(0, 0, 0, 0.06);
    }

    div[data-testid="stVerticalBlockBorderWrapper"] > div {
        padding: clamp(0.75rem, 1.3vw, 1.25rem);
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
    rounds: int
    attacks_per_round: int
    simulations: int
    enemy_save_bonus: int = 3
    attack_roll_mode: AttackRollMode = AttackRollMode.NORMAL


@dataclass(frozen=True)
class ComparisonInputs:
    """Validated user inputs for a named build comparison."""

    first_build: BuildConfig
    second_build: BuildConfig
    scenario: ScenarioConfig
    seed: int


@dataclass(frozen=True)
class SingleBuildInputs:
    """Validated user inputs for a single named build simulation."""

    build: BuildConfig
    scenario: ScenarioConfig
    seed: int


def validate_simulation_inputs(inputs: SimulationInputs) -> None:
    """Validate Streamlit form inputs before running a simulation.

    Raises:
        ValueError: If an input cannot produce a usable damage simulation.
    """
    if not inputs.damage_dice.strip():
        msg = "Damage Formula is required. Use notation such as 1d8+4."
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
        enemy_save_bonus=inputs.enemy_save_bonus,
        damage_dice=inputs.damage_dice.strip(),
        rounds=inputs.rounds,
        simulations=inputs.simulations,
        attacks_per_round=inputs.attacks_per_round,
        attack_roll_mode=inputs.attack_roll_mode,
    )


def run_single_build_from_inputs(inputs: SingleBuildInputs) -> SimulationResult:
    """Validate inputs and run the shared single-build simulation engine."""
    return simulate_build(inputs.build, inputs.scenario, inputs.seed)


def run_comparison_from_inputs(inputs: ComparisonInputs) -> BuildComparisonResult:
    """Validate inputs and run the shared comparison engine."""
    return compare_builds(
        first_build=inputs.first_build,
        second_build=inputs.second_build,
        scenario=inputs.scenario,
        seed=inputs.seed,
    )


def _render_section_container():
    """Return a bordered Streamlit container when available."""
    import streamlit as st

    container = getattr(st, "container", None)
    if container is None:
        return nullcontext()
    try:
        return container(border=True)
    except TypeError:
        return container()


def _round_chart_data(
    result: SimulationResult, build_name: str
) -> list[dict[str, int | float | str]]:
    """Build round-level chart data for one simulation result."""
    return [
        {
            "Round": round_result.round_number,
            "Average total damage": round_result.average_damage,
            "Build": build_name,
        }
        for round_result in result.round_results
    ]


def _comparison_round_chart_data(
    comparison: BuildComparisonResult,
) -> list[dict[str, int | float | str]]:
    """Build round-level chart data for both compared builds."""
    return [
        *_round_chart_data(comparison.first_result, comparison.first_build.name),
        *_round_chart_data(comparison.second_result, comparison.second_build.name),
    ]


def _profile_metadata(
    profile_result: AttackProfileResult, index: int, build_name: str
) -> dict[str, int | float | str]:
    profile = profile_result.attack_profile
    return {
        "Profile": profile.name,
        "Order": index,
        "Build": build_name,
        "Resolution type": profile.resolution_type.value.replace("_", " ").title(),
        "Active Rounds": profile.active_rounds or "Every round",
        "Attacks per active round": profile.attacks_per_round,
        "Affected targets": profile.affected_targets,
    }


def _profile_contribution_chart_data(
    result: SimulationResult, build_name: str
) -> list[dict[str, int | float | str]]:
    """Build profile contribution chart data in configured attack-profile order."""
    total = result.average_damage_per_round
    rows = []
    for index, profile_result in enumerate(result.attack_profile_results, start=1):
        contribution = profile_result.average_damage_per_round
        rows.append(
            {
                **_profile_metadata(profile_result, index, build_name),
                "Damage per Round contribution": contribution,
                "Contribution percentage": contribution / total * 100 if total else 0,
            }
        )
    return rows


def _profile_damage_per_use_chart_data(
    result: SimulationResult, build_name: str
) -> list[dict[str, int | float | str]]:
    """Build average damage per profile use chart data in configured order."""
    return [
        {
            **_profile_metadata(profile_result, index, build_name),
            "Average damage per use": profile_result.average_damage_per_use,
            "Total profile uses": profile_result.total_profile_uses,
        }
        for index, profile_result in enumerate(result.attack_profile_results, start=1)
    ]


def _line_chart(data, *, x: str, y: str, color: str):
    import altair as alt
    import pandas as pd

    return (
        alt.Chart(pd.DataFrame(data))
        .mark_line(point=True)
        .encode(
            x=alt.X(x, title="Round number", axis=alt.Axis(format="d")),
            y=alt.Y(y, title="Average total damage"),
            color=alt.Color(color, title="Build"),
            tooltip=[
                alt.Tooltip(x, title="Round"),
                alt.Tooltip(y, title="Average damage", format=".2f"),
                alt.Tooltip(color, title="Build"),
            ],
        )
    )


def _profile_contribution_bar_chart(data):
    import altair as alt
    import pandas as pd

    return (
        alt.Chart(pd.DataFrame(data))
        .mark_bar()
        .encode(
            x=alt.X("Profile:N", sort=alt.SortField("Order"), title="Attack profile"),
            y=alt.Y(
                "Damage per Round contribution:Q",
                title="Damage per Round contribution",
            ),
            tooltip=[
                alt.Tooltip("Profile:N", title="Attack name"),
                alt.Tooltip("Resolution type:N", title="Resolution type"),
                alt.Tooltip(
                    "Damage per Round contribution:Q",
                    title="Damage per Round contribution",
                    format=".2f",
                ),
                alt.Tooltip(
                    "Contribution percentage:Q",
                    title="Contribution percentage",
                    format=".1f",
                ),
                alt.Tooltip("Active Rounds:N", title="Active Rounds"),
                alt.Tooltip(
                    "Attacks per active round:Q", title="Attacks per active round"
                ),
                alt.Tooltip("Affected targets:Q", title="Affected Targets"),
            ],
        )
    )


def _profile_damage_per_use_bar_chart(data):
    import altair as alt
    import pandas as pd

    return (
        alt.Chart(pd.DataFrame(data))
        .mark_bar()
        .encode(
            x=alt.X("Profile:N", sort=alt.SortField("Order"), title="Attack profile"),
            y=alt.Y(
                "Average damage per use:Q",
                title="Average total damage from one use",
            ),
            tooltip=[
                alt.Tooltip("Profile:N", title="Attack name"),
                alt.Tooltip("Resolution type:N", title="Resolution type"),
                alt.Tooltip(
                    "Average damage per use:Q",
                    title="Average damage per use",
                    format=".2f",
                ),
                alt.Tooltip("Total profile uses:Q", title="Total profile uses"),
                alt.Tooltip("Affected targets:Q", title="Affected Targets"),
                alt.Tooltip("Active Rounds:N", title="Active Rounds"),
            ],
        )
    )


def _render_single_build_charts(build: BuildConfig, result: SimulationResult) -> None:
    """Render focused single-build damage charts above detailed result tables."""
    import streamlit as st

    st.markdown("##### Damage per Round")
    st.caption("Average total damage in each round, including zero-damage rounds.")
    st.altair_chart(
        _line_chart(
            _round_chart_data(result, build.name),
            x="Round:O",
            y="Average total damage:Q",
            color="Build:N",
        ),
        width="stretch",
    )

    contribution_data = _profile_contribution_chart_data(result, build.name)
    damage_per_use_data = _profile_damage_per_use_chart_data(result, build.name)
    first_col, second_col = st.columns(2)
    with first_col:
        st.markdown("##### Attack Contribution to Damage per Round")
        st.caption(
            "How much each attack adds to the build's overall average Damage per Round."
        )
        st.altair_chart(
            _profile_contribution_bar_chart(contribution_data), width="stretch"
        )
    with second_col:
        st.markdown("##### Average Damage per Attack Use")
        st.caption(
            "Expected total damage each time the attack is used, including misses, "
            "saves, and all affected targets."
        )
        st.altair_chart(
            _profile_damage_per_use_bar_chart(damage_per_use_data), width="stretch"
        )


def _render_comparison_charts(comparison: BuildComparisonResult) -> None:
    """Render focused comparison charts while keeping profiles separate."""
    import streamlit as st

    st.markdown("##### Damage per Round")
    st.caption("Round-by-round damage for each build on the same round axis.")
    st.altair_chart(
        _line_chart(
            _comparison_round_chart_data(comparison),
            x="Round:O",
            y="Average total damage:Q",
            color="Build:N",
        ),
        width="stretch",
    )

    for build, result in (
        (comparison.first_build, comparison.first_result),
        (comparison.second_build, comparison.second_result),
    ):
        st.markdown(f"##### {build.name}")
        first_col, second_col = st.columns(2)
        with first_col:
            st.markdown("###### Attack Contribution to Damage per Round")
            st.caption(
                "How much each attack adds to the build's overall average "
                "Damage per Round."
            )
            st.altair_chart(
                _profile_contribution_bar_chart(
                    _profile_contribution_chart_data(result, build.name)
                ),
                width="stretch",
            )
        with second_col:
            st.markdown("###### Average Damage per Attack Use")
            st.caption(
                "Expected total damage each time the attack is used, including misses, "
                "saves, and all affected targets."
            )
            st.altair_chart(
                _profile_damage_per_use_bar_chart(
                    _profile_damage_per_use_chart_data(result, build.name)
                ),
                width="stretch",
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
            "Metric": "Average total damage across all affected targets",
            comparison.first_build.name: format_damage(
                first.average_total_damage_per_simulation
            ),
            comparison.second_build.name: format_damage(
                second.average_total_damage_per_simulation
            ),
            "Difference": format_signed_damage(difference.average_total_damage),
        },
        {
            "Metric": "Average damage per target per round",
            comparison.first_build.name: format_damage(
                first.average_damage_per_target_per_round
            ),
            comparison.second_build.name: format_damage(
                second.average_damage_per_target_per_round
            ),
            "Difference": format_signed_damage(
                difference.average_damage_per_target_per_round
            ),
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
        "Average total damage per round",
        format_damage(result.average_damage_per_round),
    )
    first_row[1].metric(
        "Average total damage across targets",
        format_damage(result.average_total_damage_per_simulation),
    )
    first_row[2].metric("Attack-roll hit percentage", format_rate(result.hit_rate))
    first_row[3].metric(
        "Attack-roll critical hit percentage", format_rate(result.critical_hit_rate)
    )

    second_row = st.columns(4)
    second_row[0].metric(
        "Minimum total damage",
        format_damage(result.minimum_total_damage_in_simulation),
    )
    second_row[1].metric(
        "Maximum total damage",
        format_damage(result.maximum_total_damage_in_simulation),
    )
    second_row[2].metric("Total attacks simulated", f"{result.total_attacks_made:,}")
    second_row[3].metric(
        "Target resolutions simulated", f"{result.total_target_resolutions:,}"
    )

    st.caption(f"Attack roll mode: {result.attack_roll_mode.value.title()}")


def _profile_breakdown_rows(result: SimulationResult) -> list[dict[str, str]]:
    """Build per-profile damage breakdown rows."""
    rows = []
    for profile_result in result.attack_profile_results:
        profile = profile_result.attack_profile
        row = {
            "Attack profile": profile.name,
            "Resolution type": profile.resolution_type.value.replace("_", " ").title(),
            "Attacks per active round": str(profile.attacks_per_round),
            "Affected targets": str(profile.affected_targets),
            "Active Rounds": profile.active_rounds or "Every round",
            "Feats and Features": format_features(profile.features),
            "Profile uses": f"{profile_result.total_profile_uses:,}",
            "Target resolutions": f"{profile_result.total_target_resolutions:,}",
            "Average damage per use": format_damage(
                profile_result.average_damage_per_use
            ),
            "Contribution to total Damage per Round": format_damage(
                profile_result.average_damage_per_round
            ),
            "Average damage per target per round": format_damage(
                profile_result.average_damage_per_target_per_round
            ),
            "Average total damage across all affected targets": format_damage(
                profile_result.average_total_damage_per_simulation
            ),
        }
        if profile.resolution_type is ResolutionType.AUTOMATIC_DAMAGE:
            row["Automatic damage applications"] = (
                f"{profile_result.automatic_damage_applications:,}"
            )
        elif profile.resolution_type is ResolutionType.SAVING_THROW:
            row["Failed save percentage"] = format_rate(profile_result.failed_save_rate)
            row["Successful save percentage"] = format_rate(
                profile_result.successful_save_rate
            )
        else:
            row["Hit percentage"] = format_rate(profile_result.hit_rate)
            row["Critical hit percentage"] = format_rate(
                profile_result.critical_hit_rate
            )
        rows.append(row)
    return rows


def _single_result_rows(result: SimulationResult) -> list[dict[str, str]]:
    """Build aggregate rows for a single-build result table."""
    return [
        {
            "Metric": "Average total damage per round",
            "Value": format_damage(result.average_damage_per_round),
        },
        {
            "Metric": "Average total damage across the combat",
            "Value": format_damage(result.average_total_damage_per_simulation),
        },
        {
            "Metric": "Average damage per target per round",
            "Value": format_damage(result.average_damage_per_target_per_round),
        },
        {
            "Metric": "Round 1 burst damage",
            "Value": format_damage(result.first_round_burst_damage),
        },
        {
            "Metric": "Average damage after round 1",
            "Value": format_damage(result.average_damage_after_round_1),
        },
        {
            "Metric": "Highest-damage round",
            "Value": (
                f"{result.highest_damage_round} "
                f"({format_damage(result.highest_round_average_damage)})"
            ),
        },
        {
            "Metric": "Minimum total damage",
            "Value": format_damage(result.minimum_total_damage_in_simulation),
        },
        {
            "Metric": "Maximum total damage",
            "Value": format_damage(result.maximum_total_damage_in_simulation),
        },
        {"Metric": "Total attack uses", "Value": f"{result.total_attacks_made:,}"},
        {
            "Metric": "Total target resolutions",
            "Value": f"{result.total_target_resolutions:,}",
        },
    ]


def _single_round_breakdown_rows(result: SimulationResult) -> list[dict[str, str]]:
    """Build per-round rows for a single-build result."""
    return [
        {
            "Round": str(round_result.round_number),
            "Average damage": format_damage(round_result.average_damage),
            "Average attack uses": format_damage(round_result.average_attacks),
            "Hit percentage": format_rate(round_result.hit_rate),
            "Critical hit percentage": format_rate(round_result.critical_hit_rate),
            "Failed save percentage": format_rate(round_result.failed_save_rate),
            "Successful save percentage": format_rate(
                round_result.successful_save_rate
            ),
        }
        for round_result in result.round_results
    ]


def _render_single_build_results(build: BuildConfig, result: SimulationResult) -> None:
    """Render complete results for one build without comparison labels or deltas."""
    import streamlit as st

    heading = build.name.strip() or "Simulation"
    with _render_section_container():
        st.subheader(f"{heading} results")
        metric_rows = st.columns(5)
        metric_rows[0].metric(
            "Average damage per round", format_damage(result.average_damage_per_round)
        )
        metric_rows[1].metric(
            "Average total damage",
            format_damage(result.average_total_damage_per_simulation),
        )
        metric_rows[2].metric(
            "Round 1 burst", format_damage(result.first_round_burst_damage)
        )
        metric_rows[3].metric(
            "Sustained after round 1",
            format_damage(result.average_damage_after_round_1),
        )
        metric_rows[4].metric(
            "Highest-damage round",
            (
                f"{result.highest_damage_round} "
                f"({format_damage(result.highest_round_average_damage)})"
            ),
        )
        _render_single_build_charts(build, result)
        with st.expander("Detailed Results", expanded=False):
            st.table(_single_result_rows(result))
            st.markdown("##### Per-round breakdown")
            st.table(_single_round_breakdown_rows(result))
            st.markdown("##### Per-attack-profile breakdown")
            st.table(_profile_breakdown_rows(result))


def _render_comparison_results(comparison: BuildComparisonResult) -> None:
    """Render two build results side by side with deltas."""
    import streamlit as st

    with _render_section_container():
        st.subheader("Build comparison")
        if comparison.higher_average_damage_build_name is None:
            st.success("Both builds have the same average damage per round.")
        else:
            st.success(
                f"{comparison.higher_average_damage_build_name} has higher "
                "average damage."
            )
        first_cols = st.columns(5)
        for cols, build, result in (
            (first_cols, comparison.first_build, comparison.first_result),
            (st.columns(5), comparison.second_build, comparison.second_result),
        ):
            cols[0].metric(
                f"{build.name} avg/round",
                format_damage(result.average_damage_per_round),
            )
            cols[1].metric(
                f"{build.name} total",
                format_damage(result.average_total_damage_per_simulation),
            )
            cols[2].metric(
                f"{build.name} round 1", format_damage(result.first_round_burst_damage)
            )
            cols[3].metric(
                f"{build.name} sustained",
                format_damage(result.average_damage_after_round_1),
            )
            cols[4].metric(
                f"{build.name} highest round",
                (
                    f"{result.highest_damage_round} "
                    f"({format_damage(result.highest_round_average_damage)})"
                ),
            )
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
        _render_comparison_charts(comparison)
        with st.expander("Detailed Results", expanded=False):
            st.table(_result_rows(comparison))
            st.markdown("##### Per-round damage")
            st.table(_round_breakdown_rows(comparison))
            st.markdown(f"##### {comparison.first_build.name} attack breakdown")
            st.table(_profile_breakdown_rows(comparison.first_result))
            st.markdown(f"##### {comparison.second_build.name} attack breakdown")
            st.table(_profile_breakdown_rows(comparison.second_result))
            st.caption(
                "Difference is first build minus second build. Both builds used "
                "separate random-number-generator instances initialized with the "
                "same seed."
            )


def format_features(features: frozenset[AttackFeature]) -> str:
    """Format selected profile features in stable interface order."""
    selected = [
        FEATURE_LABELS[feature] for feature in FEATURE_ORDER if feature in features
    ]
    return ", ".join(selected) if selected else "None"


def _feature_inputs(
    prefix: str, resolution_type: ResolutionType
) -> frozenset[AttackFeature]:
    """Render feats and features controls for one attack profile."""
    import streamlit as st

    selected = set()
    expander = getattr(st, "expander", None)
    checkbox = getattr(st, "checkbox", None)
    if expander is None or checkbox is None:
        return frozenset()
    with expander("Feats and Features", expanded=False):
        for feature in FEATURE_ORDER:
            disabled = (
                feature is AttackFeature.ELVEN_ACCURACY
                and resolution_type is not ResolutionType.ATTACK_ROLL
            )
            checked = checkbox(
                FEATURE_LABELS[feature],
                value=False,
                key=f"{prefix}-feature-{feature.value}",
                help=FEATURE_HELP[feature],
                disabled=disabled,
            )
            if checked and not disabled:
                selected.add(feature)
    return frozenset(selected)


def _attack_profile_inputs(prefix: str, default_name: str) -> AttackProfile:
    """Render and collect one attack profile's input controls."""
    import streamlit as st

    attack_name = st.text_input("Attack name", value=default_name, key=f"{prefix}-name")
    resolution_type_label = st.selectbox(
        "Resolution Type",
        options=["Attack Roll", "Saving Throw", "Automatic Damage"],
        index=0,
        key=f"{prefix}-resolution-type",
    )
    resolution_type = {
        "Attack Roll": ResolutionType.ATTACK_ROLL,
        "Saving Throw": ResolutionType.SAVING_THROW,
        "Automatic Damage": ResolutionType.AUTOMATIC_DAMAGE,
    }[resolution_type_label]
    row_one = st.columns(2)
    if resolution_type is ResolutionType.ATTACK_ROLL:
        attack_bonus = row_one[0].number_input(
            "Attack bonus", value=5, step=1, key=f"{prefix}-attack-bonus"
        )
        save_dc = None
    elif resolution_type is ResolutionType.SAVING_THROW:
        attack_bonus = None
        save_dc = row_one[0].number_input(
            "Save DC", min_value=1, value=13, step=1, key=f"{prefix}-save-dc"
        )
    else:
        attack_bonus = None
        save_dc = None
    damage_dice = row_one[1].text_input(
        "Damage Formula",
        value="1d8+3",
        placeholder=DAMAGE_FORMULA_PLACEHOLDER,
        help=DAMAGE_FORMULA_HELP,
        key=f"{prefix}-damage-dice",
    )
    row_two = st.columns(3)
    attacks_per_round = row_two[0].number_input(
        "Attacks per round", min_value=1, value=1, step=1, key=f"{prefix}-attacks"
    )
    affected_targets = row_two[1].number_input(
        "Affected Targets",
        min_value=1,
        value=1,
        step=1,
        key=f"{prefix}-affected-targets",
    )
    if resolution_type is ResolutionType.ATTACK_ROLL:
        attack_roll_mode_label = row_two[2].selectbox(
            "Attack roll mode",
            options=[mode.value.title() for mode in AttackRollMode],
            index=0,
            key=f"{prefix}-mode",
        )
        attack_roll_mode = AttackRollMode(attack_roll_mode_label.lower())
        successful_save_damage = SuccessfulSaveDamage.NO_DAMAGE
    elif resolution_type is ResolutionType.SAVING_THROW:
        successful_save_damage_label = row_two[2].selectbox(
            "Successful Save Damage",
            options=["No damage", "Half damage"],
            index=0,
            key=f"{prefix}-successful-save-damage",
        )
        attack_roll_mode = AttackRollMode.NORMAL
        successful_save_damage = (
            SuccessfulSaveDamage.HALF_DAMAGE
            if successful_save_damage_label == "Half damage"
            else SuccessfulSaveDamage.NO_DAMAGE
        )
    else:
        attack_roll_mode = AttackRollMode.NORMAL
        successful_save_damage = SuccessfulSaveDamage.NO_DAMAGE
    active_rounds = st.text_input(
        "Active Rounds",
        value="",
        help="Leave blank for every round. Examples: 1-5 or 1, 3-5, 8.",
        key=f"{prefix}-active-rounds",
    )
    features = _feature_inputs(prefix, resolution_type)
    return AttackProfile(
        name=attack_name,
        attack_bonus=None if attack_bonus is None else int(attack_bonus),
        damage_dice=damage_dice,
        attacks_per_round=int(attacks_per_round),
        affected_targets=int(affected_targets),
        attack_roll_mode=attack_roll_mode,
        active_rounds=active_rounds,
        resolution_type=resolution_type,
        save_dc=None if save_dc is None else int(save_dc),
        successful_save_damage=successful_save_damage,
        features=features,
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
) -> BuildConfig:
    """Create a build config with every displayed profile attached."""
    primary = profiles[0]
    return BuildConfig(
        name=name,
        attack_bonus=primary.attack_bonus or 0,
        damage_dice=primary.damage_dice,
        attacks_per_round=primary.attacks_per_round,
        attack_roll_mode=primary.attack_roll_mode,
        attack_profiles=profiles,
    )


def _build_inputs(prefix: str, default_name: str) -> BuildConfig:
    """Render and collect one build's input controls."""
    import streamlit as st

    with _render_section_container():
        st.markdown(f"#### {default_name}")
        name = st.text_input(
            "Build name", value=default_name, key=f"{prefix}-build-name"
        )
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
            divider = getattr(st, "divider", None)
            if divider is None:
                st.markdown("---")
            else:
                divider()
            st.markdown(f"##### {heading}")
            profiles.append(_attack_profile_inputs(profile_prefix, default_attack_name))

    return _build_config_from_profiles(name, tuple(profiles))


def main() -> None:
    """Render the Streamlit simulation page."""
    import streamlit as st

    configure_page()
    st.title(APP_TITLE)
    st.write(
        "Compare two named DnD combat builds against the same target Armor "
        "Class, round count, and simulation count."
    )

    with _render_section_container():
        st.subheader("Shared scenario")
        scenario_row = st.columns(5)
        target_armor_class = scenario_row[0].number_input(
            "Target Armor Class",
            min_value=1,
            value=15,
            step=1,
            key="scenario-target-ac",
        )
        enemy_save_bonus = scenario_row[1].number_input(
            "Enemy Save Bonus", value=3, step=1, key="scenario-enemy-save-bonus"
        )
        rounds = scenario_row[2].number_input(
            "Number of rounds", min_value=1, value=4, step=1, key="scenario-rounds"
        )
        simulations = scenario_row[3].number_input(
            "Number of simulations",
            min_value=1,
            value=10_000,
            step=1,
            key="scenario-simulations",
        )
        seed = scenario_row[4].number_input(
            "Random seed", value=20240721, step=1, key="scenario-seed"
        )

        compare_enabled = st.toggle(
            "Compare with another build",
            value=False,
            key="compare-builds-enabled",
        )

    scenario = ScenarioConfig(
        target_armor_class=int(target_armor_class),
        enemy_save_bonus=int(enemy_save_bonus),
        rounds=int(rounds),
        simulations=int(simulations),
    )

    if compare_enabled:
        build_columns = st.columns(2)
        with build_columns[0]:
            first_build = _build_inputs("first", "Build A")
        with build_columns[1]:
            second_build = _build_inputs("second", "Build B")

        if st.button("Compare Builds"):
            inputs = ComparisonInputs(
                first_build=first_build,
                second_build=second_build,
                scenario=scenario,
                seed=int(seed),
            )
            try:
                comparison = run_comparison_from_inputs(inputs)
            except ValueError as error:
                st.error(str(error))
            else:
                _render_comparison_results(comparison)
    else:
        first_build = _build_inputs("first", "Build A")

        if st.button("Run Simulation"):
            inputs = SingleBuildInputs(
                build=first_build,
                scenario=scenario,
                seed=int(seed),
            )
            try:
                result = run_single_build_from_inputs(inputs)
            except ValueError as error:
                st.error(str(error))
            else:
                _render_single_build_results(first_build, result)


if __name__ == "__main__":
    main()
