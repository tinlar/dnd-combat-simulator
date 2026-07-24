"""Focused Streamlit UI helpers."""

from __future__ import annotations

from dnd_combat_simulator.combat import (
    ResolutionType,
)
from dnd_combat_simulator.simulation import (
    AttackProfileResult,
    BuildComparisonResult,
    BuildConfig,
    SimulationResult,
    TriggerType,
)
from dnd_combat_simulator.ui.components import _render_section_container
from dnd_combat_simulator.ui.inputs import format_features


def format_damage(value: float) -> str:
    """Format a damage value for display."""
    return f"{value:.2f}"


def format_compact_decimal(value: float) -> str:
    """Format a decimal with up to two places and no unnecessary trailing zeros."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def format_rate(value: float) -> str:
    """Format a fractional rate as a percentage for display."""
    return f"{value:.2%}"


def format_signed_damage(value: float) -> str:
    """Format a signed damage delta for display."""
    return f"{value:+.2f}"


def format_signed_compact_decimal(value: float) -> str:
    """Format a signed decimal delta with compact trailing zero handling."""
    return f"{value:+.2f}".rstrip("0").rstrip(".")


def format_signed_rate(value: float) -> str:
    """Format a signed fractional rate as a percentage-point delta."""
    return f"{value:+.2%}"


def format_positive_damage(value: float) -> str:
    """Format a non-negative damage delta for display."""
    return f"{value:.2f}"


def format_positive_compact_decimal(value: float) -> str:
    """Format a non-negative decimal delta with compact trailing zero handling."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def format_positive_rate(value: float) -> str:
    """Format a non-negative fractional rate as a percentage-point delta."""
    return f"{value:.2%}"


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
        "Maximum attacks per active round": profile.attacks_per_round,
        "Attacks per active round": profile.attacks_per_round,
        "Target resolutions": profile.affected_targets,
        "Actual profile uses": profile_result.total_profile_uses,
        "Skipped profile uses": profile_result.total_skipped_profile_uses,
        "Average damage per use": profile_result.average_damage_per_use,
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
            "Actual profile uses": profile_result.total_profile_uses,
            "Skipped profile uses": profile_result.total_skipped_profile_uses,
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
                    "Maximum attacks per active round:Q",
                    title="Maximum attacks per active round",
                ),
                alt.Tooltip("Actual profile uses:Q", title="Actual profile uses"),
                alt.Tooltip("Skipped profile uses:Q", title="Skipped profile uses"),
                alt.Tooltip(
                    "Average damage per use:Q",
                    title="Average damage per use",
                    format=".2f",
                ),
                alt.Tooltip("Target resolutions:Q", title="Target Resolutions"),
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
                alt.Tooltip("Actual profile uses:Q", title="Actual profile uses"),
                alt.Tooltip("Skipped profile uses:Q", title="Skipped profile uses"),
                alt.Tooltip(
                    "Maximum attacks per active round:Q",
                    title="Maximum attacks per active round",
                ),
                alt.Tooltip("Target resolutions:Q", title="Target Resolutions"),
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


def _result_difference_column_label(comparison: BuildComparisonResult) -> str:
    """Describe the higher-DPR baseline comparison direction."""
    first_dpr = comparison.first_result.average_damage_per_round
    second_dpr = comparison.second_result.average_damage_per_round
    if second_dpr > first_dpr:
        return (
            "Difference "
            f"({comparison.second_build.name} − {comparison.first_build.name})"
        )
    return (
        f"Difference ({comparison.first_build.name} − {comparison.second_build.name})"
    )


def _result_rows(comparison: BuildComparisonResult) -> list[dict[str, str]]:
    """Build side-by-side display rows for comparison results."""
    first = comparison.first_result
    second = comparison.second_result
    difference_label = _result_difference_column_label(comparison)

    difference = comparison.difference

    def damage_gap(value: float) -> str:
        return format_positive_damage(value)

    def nondamage_gap(first_value: float, second_value: float) -> str:
        return format_positive_compact_decimal(abs(first_value - second_value))

    return [
        {
            "Metric": "Average damage per round",
            comparison.first_build.name: format_damage(first.average_damage_per_round),
            comparison.second_build.name: format_damage(
                second.average_damage_per_round
            ),
            difference_label: damage_gap(difference.average_damage_per_round),
        },
        {
            "Metric": "Average total damage per combat",
            comparison.first_build.name: format_damage(
                first.average_total_damage_per_simulation
            ),
            comparison.second_build.name: format_damage(
                second.average_total_damage_per_simulation
            ),
            difference_label: damage_gap(difference.average_total_damage),
        },
        {
            "Metric": "Expected damage per target resolution",
            comparison.first_build.name: format_damage(
                first.average_damage_per_target_per_round
            ),
            comparison.second_build.name: format_damage(
                second.average_damage_per_target_per_round
            ),
            difference_label: damage_gap(
                difference.average_damage_per_target_per_round
            ),
        },
        {
            "Metric": "Average attack executions per combat",
            comparison.first_build.name: format_compact_decimal(
                _average_attack_executions_per_combat(first)
            ),
            comparison.second_build.name: format_compact_decimal(
                _average_attack_executions_per_combat(second)
            ),
            difference_label: nondamage_gap(
                _average_attack_executions_per_combat(first),
                _average_attack_executions_per_combat(second),
            ),
        },
        {
            "Metric": "Average attack executions per round",
            comparison.first_build.name: format_compact_decimal(
                _average_attack_executions_per_round(first)
            ),
            comparison.second_build.name: format_compact_decimal(
                _average_attack_executions_per_round(second)
            ),
            difference_label: nondamage_gap(
                _average_attack_executions_per_round(first),
                _average_attack_executions_per_round(second),
            ),
        },
        {
            "Metric": "Average damaging target resolutions per combat",
            comparison.first_build.name: format_compact_decimal(
                _average_targets_damaged_per_combat(first)
            ),
            comparison.second_build.name: format_compact_decimal(
                _average_targets_damaged_per_combat(second)
            ),
            difference_label: nondamage_gap(
                _average_targets_damaged_per_combat(first),
                _average_targets_damaged_per_combat(second),
            ),
        },
        {
            "Metric": "Average damaging target resolutions per round",
            comparison.first_build.name: format_compact_decimal(
                _average_targets_damaged_per_round(first)
            ),
            comparison.second_build.name: format_compact_decimal(
                _average_targets_damaged_per_round(second)
            ),
            difference_label: nondamage_gap(
                _average_targets_damaged_per_round(first),
                _average_targets_damaged_per_round(second),
            ),
        },
        {
            "Metric": "Hit percentage",
            comparison.first_build.name: format_rate(first.hit_rate),
            comparison.second_build.name: format_rate(second.hit_rate),
            difference_label: format_positive_rate(difference.hit_rate),
        },
        {
            "Metric": "Critical hit percentage",
            comparison.first_build.name: format_rate(first.critical_hit_rate),
            comparison.second_build.name: format_rate(second.critical_hit_rate),
            difference_label: format_positive_rate(difference.critical_hit_rate),
        },
        {
            "Metric": "Round 1 burst damage",
            comparison.first_build.name: format_damage(first.first_round_burst_damage),
            comparison.second_build.name: format_damage(
                second.first_round_burst_damage
            ),
            difference_label: format_positive_damage(
                abs(first.first_round_burst_damage - second.first_round_burst_damage)
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
            difference_label: format_positive_damage(
                abs(
                    first.average_damage_after_round_1
                    - second.average_damage_after_round_1
                )
            ),
        },
        {
            "Metric": "Highest-damage round",
            comparison.first_build.name: str(first.highest_damage_round),
            comparison.second_build.name: str(second.highest_damage_round),
            difference_label: "—",
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
                f"{comparison.first_build.name} avg total damage": format_damage(
                    first_round.average_damage
                ),
                f"{comparison.second_build.name} avg total damage": format_damage(
                    second_round.average_damage
                ),
                f"{comparison.first_build.name} avg dmg resolutions": format_damage(
                    first_round.average_targets_affected
                ),
                f"{comparison.first_build.name} exp dmg / resolution": format_damage(
                    first_round.average_damage_per_target_resolution
                ),
                f"{comparison.second_build.name} avg dmg resolutions": format_damage(
                    second_round.average_targets_affected
                ),
                f"{comparison.second_build.name} exp dmg / resolution": format_damage(
                    second_round.average_damage_per_target_resolution
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


def _total_simulated_rounds(result: SimulationResult) -> int:
    """Return the number of completed combat rounds represented by a result."""
    return result.simulations_run * result.rounds_per_simulation


def _average_attack_executions_per_combat(result: SimulationResult) -> float:
    """Return average attack profile executions in each completed combat."""
    return result.total_attacks_made / result.simulations_run


def _average_attack_executions_per_round(result: SimulationResult) -> float:
    """Return average attack profile executions in each simulated combat round."""
    return result.total_attacks_made / _total_simulated_rounds(result)


def _average_targets_damaged_per_combat(result: SimulationResult) -> float:
    """Return average damaged targets in each completed combat.

    The simulator counts each damage event's affected targets and does not identify
    whether multiple events damaged the same creature.
    """
    return result.total_targets_affected / result.simulations_run


def _average_targets_damaged_per_round(result: SimulationResult) -> float:
    """Return average damaged targets in each simulated combat round."""
    return result.total_targets_affected / _total_simulated_rounds(result)


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
        "Average attack executions per combat",
        format_compact_decimal(_average_attack_executions_per_combat(result)),
        help="Average number of attack profile executions in each completed combat.",
    )
    second_row[1].metric(
        "Average attack executions per round",
        format_compact_decimal(_average_attack_executions_per_round(result)),
        help=(
            "Average number of attack profile executions in each simulated "
            "combat round."
        ),
    )
    second_row[2].metric(
        "Average damaging target resolutions per combat",
        format_compact_decimal(_average_targets_damaged_per_combat(result)),
        help=(
            "Average number of targets damaged in each completed combat. "
            "A creature damaged more than once can be counted more than once."
        ),
    )
    second_row[3].metric(
        "Average damaging target resolutions per round",
        format_compact_decimal(_average_targets_damaged_per_round(result)),
        help=(
            "Average number of targets damaged in each simulated combat round. "
            "A creature damaged more than once can be counted more than once."
        ),
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
            "Maximum attacks per active round": str(profile.attacks_per_round),
            "Target resolutions": str(profile.affected_targets),
            "Active Rounds": profile.active_rounds or "Every round",
            "Feats and Features": format_features(profile.features),
            "Average damage per use": format_damage(
                profile_result.average_damage_per_use
            ),
            "Damage per Round contribution": format_damage(
                profile_result.average_damage_per_round
            ),
            "Average damage per target per round": format_damage(
                profile_result.average_damage_per_target_per_round
            ),
            "Average total damage across all affected targets": format_damage(
                profile_result.average_total_damage_per_simulation
            ),
            "Average executions per combat": format_compact_decimal(
                profile_result.average_executions_per_combat
            ),
            "Average executions per round": format_compact_decimal(
                profile_result.average_executions_per_round
            ),
            "Average Empowered uses per combat": format_compact_decimal(
                profile_result.average_empowered_uses_per_combat
            ),
            "Average damage gained from Empowered": format_damage(
                profile_result.average_empowered_damage_gained_per_combat
            ),
            "Average Matching Rescue attempts per combat": format_compact_decimal(
                profile_result.average_empowered_matching_rescue_attempts_per_combat
            ),
            "Matching Rescue success rate": (
                f"{profile_result.empowered_matching_rescue_success_rate:.1%}"
            ),
            "Average attacks enabled by Matching Rescue": format_compact_decimal(
                profile_result.average_empowered_matching_rescue_attacks_enabled_per_combat
            ),
        }
        average_triggered = profile_result.average_triggered_profile_uses_per_simulation
        if profile.trigger_type is TriggerType.ALWAYS:
            row["Trigger"] = "Executes normally each round."
        elif profile.trigger_type is TriggerType.SOMETIMES:
            row["Trigger"] = (
                "Triggered "
                f"{format_compact_decimal(average_triggered)} times per combat "
                f"from a {profile.trigger_chance_percent}% once-per-round chance."
            )
        else:
            source = next(
                (
                    item.attack_profile.name
                    for item in result.attack_profile_results
                    if item.attack_profile.attack_id == profile.trigger_source_attack_id
                ),
                "selected attack",
            )
            outcomes = {
                TriggerType.AFTER_SUCCESS: "hits",
                TriggerType.AFTER_FAILURE: "misses",
                TriggerType.AFTER_CRITICAL: "scores a critical hit",
            }
            row["Trigger"] = (
                "Triggered "
                f"{format_compact_decimal(average_triggered)} times per combat "
                f"after {source} {outcomes[profile.trigger_type]}."
            )
        if profile.resolution_type is ResolutionType.SAVING_THROW:
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
            "Metric": "Average total damage per combat",
            "Value": format_damage(result.average_total_damage_per_simulation),
        },
        {
            "Metric": "Average damage per round",
            "Value": format_damage(result.average_damage_per_round),
        },
        {
            "Metric": "Expected damage per target resolution",
            "Value": format_damage(result.average_damage_per_target_per_round),
            "Details": (
                "A creature damaged by multiple attacks can contribute multiple times."
            ),
        },
        {
            "Metric": "Average attack executions per combat",
            "Value": format_compact_decimal(
                _average_attack_executions_per_combat(result)
            ),
        },
        {
            "Metric": "Average attack executions per round",
            "Value": format_compact_decimal(
                _average_attack_executions_per_round(result)
            ),
        },
        {
            "Metric": "Average damaging target resolutions per combat",
            "Value": format_compact_decimal(
                _average_targets_damaged_per_combat(result)
            ),
            "Details": (
                "A creature damaged by multiple attacks can contribute multiple times."
            ),
        },
        {
            "Metric": "Average damaging target resolutions per round",
            "Value": format_compact_decimal(_average_targets_damaged_per_round(result)),
            "Details": (
                "A creature damaged by multiple attacks can contribute multiple times."
            ),
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
    ]


def _single_round_breakdown_rows(result: SimulationResult) -> list[dict[str, str]]:
    """Build per-round rows for a single-build result."""
    return [
        {
            "Round": str(round_result.round_number),
            "Avg Total Damage": format_damage(round_result.average_damage),
            "Avg Damaging Resolutions": format_damage(
                round_result.average_targets_affected
            ),
            "Expected Damage / Resolution": format_damage(
                round_result.average_damage_per_target_resolution
            ),
            "Hit percentage": format_rate(round_result.hit_rate),
            "Critical hit percentage": format_rate(round_result.critical_hit_rate),
            "Failed save percentage": format_rate(round_result.failed_save_rate),
            "Successful save percentage": format_rate(
                round_result.successful_save_rate
            ),
        }
        for round_result in result.round_results
    ]


def _resource_usage_rows(result: SimulationResult) -> list[dict[str, str]]:
    return [
        {
            "Resource": usage.resource.name,
            "Starting amount": str(usage.resource.starting_value),
            "Avg consumed / combat": format_compact_decimal(
                usage.average_consumed_per_combat
            ),
            "Avg remaining / combat": format_compact_decimal(
                usage.average_remaining_per_combat
            ),
            "Combats Ending at 0": format_rate(usage.ended_at_zero_combat_rate),
            "Average Blocked Executions": format_compact_decimal(
                usage.average_blocked_executions_per_combat
            ),
            "Combats with Blocked Executions": format_rate(
                usage.blocked_execution_combat_rate
            ),
        }
        for usage in result.resource_usage_results
    ]


def _render_resource_usage(result: SimulationResult) -> None:
    import streamlit as st

    rows = _resource_usage_rows(result)
    if rows:
        st.markdown("##### Resource Usage")
        st.table(rows)


def _resource_limited_metric(result: SimulationResult) -> tuple[str, str]:
    return (
        "Blocked executions per combat",
        format_compact_decimal(result.average_resource_blocked_executions_per_combat),
    )


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
        if result.resource_usage_results:
            label, value = _resource_limited_metric(result)
            metric_rows[4].metric(label, value)
        else:
            metric_rows[4].metric(
                "Highest-damage round",
                (
                    f"{result.highest_damage_round} "
                    f"({format_damage(result.highest_round_average_damage)})"
                ),
            )
        _render_single_build_charts(build, result)
        _render_resource_usage(result)
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
            if result.resource_usage_results:
                label, value = _resource_limited_metric(result)
                cols[4].metric(f"{build.name} {label}", value)
            else:
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
            _render_resource_usage(comparison.first_result)
            st.markdown(f"##### {comparison.second_build.name} attack breakdown")
            st.table(_profile_breakdown_rows(comparison.second_result))
            _render_resource_usage(comparison.second_result)
            st.caption(
                f"Difference uses {_result_difference_column_label(comparison)} for "
                "every metric row. Both builds used separate random-number-generator "
                "instances initialized with the same seed."
            )
