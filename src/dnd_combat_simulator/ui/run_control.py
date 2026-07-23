# ruff: noqa
"""Focused Streamlit UI helpers."""

from __future__ import annotations

from dnd_combat_simulator.ui._shared import *  # noqa: F403
from dnd_combat_simulator.ui.constants import *  # noqa: F403


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


def _mark_simulation_pending() -> None:
    """Request one simulation run unless another run is already active."""
    import streamlit as st

    state = getattr(st, "session_state", {})
    if state.get(SIMULATION_RUNNING_KEY):
        return
    state[SIMULATION_PENDING_KEY] = True


def _run_single_build_with_feedback(inputs: SingleBuildInputs) -> SimulationResult:
    """Run a single-build simulation with Streamlit-visible loading feedback."""
    import streamlit as st

    state = getattr(st, "session_state", {})
    state[SIMULATION_RUNNING_KEY] = True
    start = time.perf_counter()
    try:
        with st.spinner("Calculating..."):
            result = run_single_build_from_inputs(inputs)
    except (ValueError, SharedConfigurationError):
        state.pop(SIMULATION_DURATION_MESSAGE_KEY, None)
        raise
    else:
        elapsed = time.perf_counter() - start
        state[SIMULATION_DURATION_MESSAGE_KEY] = (
            f"Simulation complete in {elapsed:.1f} seconds."
        )
        return result
    finally:
        state[SIMULATION_RUNNING_KEY] = False
        state[SIMULATION_PENDING_KEY] = False


def _run_comparison_with_feedback(inputs: ComparisonInputs) -> BuildComparisonResult:
    """Run a build comparison with Streamlit-visible loading feedback."""
    import streamlit as st

    state = getattr(st, "session_state", {})
    state[SIMULATION_RUNNING_KEY] = True
    start = time.perf_counter()
    try:
        with st.spinner("Calculating..."):
            result = run_comparison_from_inputs(inputs)
    except (ValueError, SharedConfigurationError):
        state.pop(SIMULATION_DURATION_MESSAGE_KEY, None)
        raise
    else:
        elapsed = time.perf_counter() - start
        state[SIMULATION_DURATION_MESSAGE_KEY] = (
            f"Simulation complete in {elapsed:.1f} seconds."
        )
        return result
    finally:
        state[SIMULATION_RUNNING_KEY] = False
        state[SIMULATION_PENDING_KEY] = False


def _render_run_simulation_button(disabled: bool) -> bool:
    """Render the shared simulation button for single and comparison workflows."""
    import streamlit as st

    state = getattr(st, "session_state", {})
    simulation_running = bool(state.get(SIMULATION_RUNNING_KEY))
    clicked = st.button(
        "Run Simulation",
        disabled=disabled or simulation_running,
        on_click=_mark_simulation_pending,
    )
    if clicked and not simulation_running and not disabled:
        state[SIMULATION_PENDING_KEY] = True
    return bool(state.get(SIMULATION_PENDING_KEY)) and not disabled
