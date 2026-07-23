from __future__ import annotations

import pytest

from dnd_combat_simulator.simulation import (
    AttackProfile,
    BuildComparisonResult,
    BuildConfig,
    ManagedResource,
    ResourceCost,
    ScenarioConfig,
    SimulationResult,
)
from dnd_combat_simulator.ui import run_control
from dnd_combat_simulator.ui.run_control import (
    ComparisonInputs,
    SingleBuildInputs,
    canonical_comparison_request,
    canonical_single_build_request,
)


def _clear_cache() -> None:
    clear = getattr(run_control._cached_execute_canonical_request, "clear", None)
    if clear is not None:
        clear()


def _build(
    name="Build", damage="1d8+3", attack_ids=("a",), resource_id: str | None = None
) -> BuildConfig:
    profiles = []
    for aid in attack_ids:
        profiles.append(
            AttackProfile(
                "Strike" + aid,
                5,
                damage,
                1,
                attack_id=aid,
                resource_costs=(
                    (ResourceCost(resource_id, 1),) if resource_id is not None else ()
                ),
            )
        )
    return BuildConfig(name, 5, damage, 1, attack_profiles=tuple(profiles))


def _scenario(simulations=10, seed_resource=False) -> ScenarioConfig:
    resources = (ManagedResource("focus", "Focus", 2),) if seed_resource else ()
    return ScenarioConfig(15, 3, simulations, managed_resources=resources)


@pytest.fixture(autouse=True)
def clear_streamlit_cache():
    _clear_cache()
    yield
    _clear_cache()


def test_actual_cache_reuses_identical_request_and_keys_result_affecting_changes(
    monkeypatch,
):
    real_simulate_build = run_control.simulate_build
    calls = []

    def counting_simulate_build(build, scenario, seed):
        calls.append((build, scenario, seed))
        return real_simulate_build(build, scenario, seed)

    monkeypatch.setattr(run_control, "simulate_build", counting_simulate_build)
    base = canonical_single_build_request(SingleBuildInputs(_build(), _scenario(), 1))

    first_result = run_control.execute_canonical_request(base)
    second_result = run_control.execute_canonical_request(base)

    assert isinstance(first_result, SimulationResult)
    assert isinstance(second_result, SimulationResult)
    assert second_result == first_result
    assert len(calls) == 1

    variants = [
        canonical_single_build_request(SingleBuildInputs(_build(), _scenario(), 2)),
        canonical_single_build_request(SingleBuildInputs(_build(), _scenario(11), 1)),
        canonical_single_build_request(
            SingleBuildInputs(_build(), ScenarioConfig(16, 3, 10), 1)
        ),
        canonical_single_build_request(
            SingleBuildInputs(_build(damage="1d10+3"), _scenario(), 1)
        ),
        canonical_single_build_request(
            SingleBuildInputs(_build(attack_ids=("b", "a")), _scenario(), 1)
        ),
        canonical_single_build_request(
            SingleBuildInputs(
                _build(resource_id="focus"), _scenario(seed_resource=True), 1
            )
        ),
    ]
    for expected_call_count, request in enumerate(variants, start=2):
        result = run_control.execute_canonical_request(request)
        assert isinstance(result, SimulationResult)
        assert len(calls) == expected_call_count
        assert isinstance(
            run_control.execute_canonical_request(request), SimulationResult
        )
        assert len(calls) == expected_call_count


def test_actual_cache_isolates_single_comparison_reversed_builds_and_cache_version(
    monkeypatch,
):
    real_simulate_build = run_control.simulate_build
    real_compare_builds = run_control.compare_builds
    calls = []

    def counting_simulate_build(build, scenario, seed):
        calls.append(("single", build.name))
        return real_simulate_build(build, scenario, seed)

    def counting_compare_builds(first_build, second_build, scenario, seed):
        calls.append(("comparison", first_build.name, second_build.name))
        return real_compare_builds(
            first_build=first_build,
            second_build=second_build,
            scenario=scenario,
            seed=seed,
        )

    monkeypatch.setattr(run_control, "simulate_build", counting_simulate_build)
    monkeypatch.setattr(run_control, "compare_builds", counting_compare_builds)
    first = _build("A", "1d8", ("a",))
    second = _build("B", "1d6", ("b",))
    scenario = _scenario()
    single = canonical_single_build_request(SingleBuildInputs(first, scenario, 1))
    comp = canonical_comparison_request(ComparisonInputs(first, second, scenario, 1))
    rev = canonical_comparison_request(ComparisonInputs(second, first, scenario, 1))
    versioned = run_control.CanonicalSimulationRequest(
        single.cache_version + 1,
        single.comparison_enabled,
        single.scenario,
        single.first_build,
        single.second_build,
        single.simulations,
        single.seed,
    )

    expected_types = (
        (single, SimulationResult),
        (comp, BuildComparisonResult),
        (rev, BuildComparisonResult),
        (versioned, SimulationResult),
    )
    for expected_call_count, (request, expected_type) in enumerate(
        expected_types, start=1
    ):
        result = run_control.execute_canonical_request(request)
        assert isinstance(result, expected_type)
        assert len(calls) == expected_call_count
        cached_result = run_control.execute_canonical_request(request)
        assert isinstance(cached_result, expected_type)
        assert cached_result == result
        assert len(calls) == expected_call_count

    assert calls == [
        ("single", "A"),
        ("comparison", "A", "B"),
        ("comparison", "B", "A"),
        ("single", "A"),
    ]


@pytest.mark.parametrize(
    "build",
    [
        _build(damage="1d6+"),
        _build(attack_ids=("",)),
        _build(attack_ids=("dup", "dup")),
        _build(resource_id="missing"),
    ],
)
def test_invalid_requests_never_reach_cached_boundary(monkeypatch, build):
    def fail(request):
        raise AssertionError("cached boundary reached")

    monkeypatch.setattr(run_control, "_cached_execute_canonical_request", fail)
    scenario = _scenario(seed_resource=True)
    with pytest.raises(ValueError):
        run_control.execute_canonical_request(
            canonical_single_build_request(SingleBuildInputs(build, scenario, 1))
        )


def test_engine_exceptions_are_not_cached(monkeypatch):
    real_simulate_build = run_control.simulate_build
    calls = 0

    def flaky_simulate_build(build, scenario, seed):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        return real_simulate_build(build, scenario, seed)

    monkeypatch.setattr(run_control, "simulate_build", flaky_simulate_build)
    request = canonical_single_build_request(
        SingleBuildInputs(_build(), _scenario(), 1)
    )

    with pytest.raises(RuntimeError):
        run_control.execute_canonical_request(request)

    retry_result = run_control.execute_canonical_request(request)
    assert isinstance(retry_result, SimulationResult)
    assert calls == 2

    cached_result = run_control.execute_canonical_request(request)
    assert isinstance(cached_result, SimulationResult)
    assert cached_result == retry_result
    assert calls == 2


def test_production_result_types_cross_actual_streamlit_cache_boundary(monkeypatch):
    real_simulate_build = run_control.simulate_build
    real_compare_builds = run_control.compare_builds
    calls = []

    def counting_simulate_build(build, scenario, seed):
        calls.append(("single", build.name))
        return real_simulate_build(build, scenario, seed)

    def counting_compare_builds(first_build, second_build, scenario, seed):
        calls.append(("comparison", first_build.name, second_build.name))
        return real_compare_builds(
            first_build=first_build,
            second_build=second_build,
            scenario=scenario,
            seed=seed,
        )

    monkeypatch.setattr(run_control, "simulate_build", counting_simulate_build)
    monkeypatch.setattr(run_control, "compare_builds", counting_compare_builds)

    first = _build("A", "1d8", ("a",))
    second = _build("B", "1d6", ("b",))
    scenario = _scenario()
    single = canonical_single_build_request(SingleBuildInputs(first, scenario, 1))
    comparison = canonical_comparison_request(
        ComparisonInputs(first, second, scenario, 1)
    )

    _clear_cache()
    single_result = run_control.execute_canonical_request(single)
    cached_single_result = run_control.execute_canonical_request(single)
    assert isinstance(single_result, SimulationResult)
    assert isinstance(cached_single_result, SimulationResult)
    assert cached_single_result == single_result
    assert calls == [("single", "A")]

    comparison_result = run_control.execute_canonical_request(comparison)
    cached_comparison_result = run_control.execute_canonical_request(comparison)
    assert isinstance(comparison_result, BuildComparisonResult)
    assert isinstance(cached_comparison_result, BuildComparisonResult)
    assert cached_comparison_result == comparison_result
    assert calls == [("single", "A"), ("comparison", "A", "B")]
