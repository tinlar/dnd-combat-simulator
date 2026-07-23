"""Focused UI helpers moved from the Streamlit entry point."""

from __future__ import annotations

from dnd_combat_simulator.ui.monolith import (
    SIMULATION_DURATION_MESSAGE_KEY,
    SIMULATION_PENDING_KEY,
    SIMULATION_RUNNING_KEY,
    ComparisonInputs,
    SimulationInputs,
    SingleBuildInputs,
    _mark_simulation_pending,
    _render_run_simulation_button,
    _run_comparison_with_feedback,
    _run_single_build_with_feedback,
    run_comparison_from_inputs,
    run_simulation_from_inputs,
    run_single_build_from_inputs,
    validate_simulation_inputs,
)

__all__ = [
    "SimulationInputs",
    "ComparisonInputs",
    "SingleBuildInputs",
    "SIMULATION_RUNNING_KEY",
    "SIMULATION_PENDING_KEY",
    "SIMULATION_DURATION_MESSAGE_KEY",
    "validate_simulation_inputs",
    "run_simulation_from_inputs",
    "run_single_build_from_inputs",
    "run_comparison_from_inputs",
    "_mark_simulation_pending",
    "_run_single_build_with_feedback",
    "_run_comparison_with_feedback",
    "_render_run_simulation_button",
]
