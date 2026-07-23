"""Run-button state and deterministic simulation execution caching."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace

from dnd_combat_simulator.combat import AttackRollMode
from dnd_combat_simulator.sharing import SharedConfigurationError
from dnd_combat_simulator.simulation import (
    BuildComparisonResult,
    BuildConfig,
    ScenarioConfig,
    SimulationResult,
    compare_builds,
    run_damage_simulations,
    simulate_build,
)
from dnd_combat_simulator.ui.constants import (
    SIMULATION_DURATION_MESSAGE_KEY,
    SIMULATION_PENDING_KEY,
    SIMULATION_RUNNING_KEY,
)
from dnd_combat_simulator.ui.validation import (
    ValidationIssue,
    ValidationScope,
    validate_build_fields,
    validate_scenario_fields,
)

logger = logging.getLogger(__name__)
SIMULATION_CACHE_VERSION = 1
SIMULATION_CACHE_MAX_ENTRIES = 64


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


@dataclass(frozen=True)
class CanonicalSimulationRequest:
    """Immutable cache identity for validated simulation execution."""

    cache_version: int
    comparison_enabled: bool
    scenario: ScenarioConfig
    first_build: BuildConfig
    second_build: BuildConfig | None
    simulations: int
    seed: int


def canonical_single_build_request(
    inputs: SingleBuildInputs,
) -> CanonicalSimulationRequest:
    return CanonicalSimulationRequest(
        cache_version=SIMULATION_CACHE_VERSION,
        comparison_enabled=False,
        scenario=inputs.scenario,
        first_build=inputs.build,
        second_build=None,
        simulations=inputs.scenario.simulations,
        seed=inputs.seed,
    )


def canonical_comparison_request(
    inputs: ComparisonInputs,
) -> CanonicalSimulationRequest:
    return CanonicalSimulationRequest(
        cache_version=SIMULATION_CACHE_VERSION,
        comparison_enabled=True,
        scenario=inputs.scenario,
        first_build=inputs.first_build,
        second_build=inputs.second_build,
        simulations=inputs.scenario.simulations,
        seed=inputs.seed,
    )


def validate_simulation_inputs(inputs: SimulationInputs) -> None:
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


def _execute_canonical_request_uncached(
    request: CanonicalSimulationRequest,
) -> SimulationResult | BuildComparisonResult:
    logger.info("Executing simulation cache boundary")
    scenario = replace(request.scenario, simulations=request.simulations)
    if request.comparison_enabled:
        if request.second_build is None:
            msg = "Comparison request requires Build B."
            raise ValueError(msg)
        return compare_builds(
            first_build=request.first_build,
            second_build=request.second_build,
            scenario=scenario,
            seed=request.seed,
        )
    return simulate_build(request.first_build, scenario, request.seed)


try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - streamlit is a runtime dependency
    st = None  # type: ignore[assignment]

if st is not None:
    _cached_execute_canonical_request = st.cache_data(
        show_spinner=False,
        max_entries=SIMULATION_CACHE_MAX_ENTRIES,
    )(_execute_canonical_request_uncached)
else:
    _cached_execute_canonical_request = _execute_canonical_request_uncached


def validate_canonical_request(
    request: CanonicalSimulationRequest,
) -> tuple[ValidationIssue, ...]:
    """Validate the complete immutable request before it reaches the cache."""
    issues: list[ValidationIssue] = []
    issues.extend(validate_scenario_fields(request.scenario))
    available_resource_ids = frozenset(
        resource.resource_id
        for resource in request.scenario.managed_resources
        if resource.resource_id
    )
    issues.extend(
        validate_build_fields(
            request.first_build,
            prefix="first",
            available_resource_ids=available_resource_ids,
        )
    )
    if request.comparison_enabled:
        if request.second_build is None:
            issues.append(
                ValidationIssue(
                    scope=ValidationScope.BUILD,
                    message="Comparison request requires Build B.",
                    field="second_build",
                    build_key="second",
                )
            )
        else:
            issues.extend(
                validate_build_fields(
                    request.second_build,
                    prefix="second",
                    available_resource_ids=available_resource_ids,
                )
            )
    elif request.second_build is not None:
        issues.append(
            ValidationIssue(
                scope=ValidationScope.BUILD,
                message="Single-build request must not include Build B.",
                field="second_build",
                build_key="second",
            )
        )
    if request.simulations < 1:
        issues.append(
            ValidationIssue(
                scope=ValidationScope.SCENARIO,
                message="Number of simulations must be at least 1.",
                field="simulations",
                widget_key="simulations",
            )
        )
    return tuple(issues)


def _raise_for_canonical_issues(issues: tuple[ValidationIssue, ...]) -> None:
    if not issues:
        return
    summary = "; ".join(issue.message for issue in issues[:3])
    if len(issues) > 3:
        summary += f"; and {len(issues) - 3} more validation issue(s)"
    raise ValueError(f"Invalid simulation request: {summary}")


def execute_canonical_request(
    request: CanonicalSimulationRequest,
) -> SimulationResult | BuildComparisonResult:
    issues = validate_canonical_request(request)
    _raise_for_canonical_issues(issues)
    return _cached_execute_canonical_request(request)


def run_single_build_from_inputs(inputs: SingleBuildInputs) -> SimulationResult:
    result = execute_canonical_request(canonical_single_build_request(inputs))
    if not isinstance(result, SimulationResult):
        msg = "Cached comparison result returned for single-build request."
        raise TypeError(msg)
    return result


def run_comparison_from_inputs(inputs: ComparisonInputs) -> BuildComparisonResult:
    result = execute_canonical_request(canonical_comparison_request(inputs))
    if not isinstance(result, BuildComparisonResult):
        msg = "Cached single-build result returned for comparison request."
        raise TypeError(msg)
    return result


def _mark_simulation_pending() -> None:
    import streamlit as st

    state = getattr(st, "session_state", {})
    if state.get(SIMULATION_RUNNING_KEY):
        return
    state[SIMULATION_PENDING_KEY] = True


def _run_single_build_with_feedback(
    inputs: SingleBuildInputs,
    *,
    execute=run_single_build_from_inputs,
    clock=time.perf_counter,
) -> SimulationResult:
    import streamlit as st

    state = getattr(st, "session_state", {})
    state[SIMULATION_RUNNING_KEY] = True
    start = clock()
    logger.info("Starting single-build simulation")
    try:
        with st.spinner("Calculating..."):
            result = execute(inputs)
    except (ValueError, SharedConfigurationError):
        state.pop(SIMULATION_DURATION_MESSAGE_KEY, None)
        raise
    except Exception:
        state.pop(SIMULATION_DURATION_MESSAGE_KEY, None)
        logger.exception("Unexpected single-build simulation failure")
        raise
    else:
        elapsed = clock() - start
        logger.info("Completed single-build simulation in %.3f seconds", elapsed)
        state[SIMULATION_DURATION_MESSAGE_KEY] = (
            f"Simulation complete in {elapsed:.1f} seconds."
        )
        return result
    finally:
        state[SIMULATION_RUNNING_KEY] = False
        state[SIMULATION_PENDING_KEY] = False


def _run_comparison_with_feedback(
    inputs: ComparisonInputs,
    *,
    execute=run_comparison_from_inputs,
    clock=time.perf_counter,
) -> BuildComparisonResult:
    import streamlit as st

    state = getattr(st, "session_state", {})
    state[SIMULATION_RUNNING_KEY] = True
    start = clock()
    logger.info("Starting comparison simulation")
    try:
        with st.spinner("Calculating..."):
            result = execute(inputs)
    except (ValueError, SharedConfigurationError):
        state.pop(SIMULATION_DURATION_MESSAGE_KEY, None)
        raise
    except Exception:
        state.pop(SIMULATION_DURATION_MESSAGE_KEY, None)
        logger.exception("Unexpected comparison simulation failure")
        raise
    else:
        elapsed = clock() - start
        logger.info("Completed comparison simulation in %.3f seconds", elapsed)
        state[SIMULATION_DURATION_MESSAGE_KEY] = (
            f"Simulation complete in {elapsed:.1f} seconds."
        )
        return result
    finally:
        state[SIMULATION_RUNNING_KEY] = False
        state[SIMULATION_PENDING_KEY] = False


def _render_run_simulation_button(disabled: bool) -> bool:
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


__all__ = [
    "SIMULATION_CACHE_VERSION",
    "CanonicalSimulationRequest",
    "ComparisonInputs",
    "SingleBuildInputs",
    "SimulationInputs",
    "canonical_comparison_request",
    "canonical_single_build_request",
    "execute_canonical_request",
    "validate_canonical_request",
    "run_comparison_from_inputs",
    "run_simulation_from_inputs",
    "run_single_build_from_inputs",
    "validate_simulation_inputs",
]
