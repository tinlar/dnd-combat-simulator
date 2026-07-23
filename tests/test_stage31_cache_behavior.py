from __future__ import annotations

import pytest

from dnd_combat_simulator.simulation import (
    AttackProfile,
    BuildConfig,
    ManagedResource,
    ResourceCost,
    ScenarioConfig,
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
    return ScenarioConfig(15, 3, 2, simulations, managed_resources=resources)


@pytest.fixture(autouse=True)
def clear_streamlit_cache():
    _clear_cache()
    yield
    _clear_cache()


def test_actual_cache_reuses_identical_request_and_keys_result_affecting_changes(
    monkeypatch,
):
    calls = []

    def fake_simulate(build, scenario, seed):
        calls.append((build, scenario, seed))
        return {"call": len(calls)}

    monkeypatch.setattr(run_control, "simulate_build", fake_simulate)
    base = canonical_single_build_request(SingleBuildInputs(_build(), _scenario(), 1))
    assert run_control.execute_canonical_request(base) == {"call": 1}
    assert run_control.execute_canonical_request(base) == {"call": 1}
    variants = [
        canonical_single_build_request(SingleBuildInputs(_build(), _scenario(), 2)),
        canonical_single_build_request(SingleBuildInputs(_build(), _scenario(11), 1)),
        canonical_single_build_request(
            SingleBuildInputs(_build(), ScenarioConfig(16, 3, 2, 10), 1)
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
    for expected, request in enumerate(variants, start=2):
        assert run_control.execute_canonical_request(request) == {"call": expected}
    assert len(calls) == 7


def test_actual_cache_isolates_single_comparison_reversed_builds_and_cache_version(
    monkeypatch,
):
    calls = []

    def fake_simulate(build, scenario, seed):
        calls.append("single")
        return {"kind": "single", "call": len(calls)}

    def fake_compare(first_build, second_build, scenario, seed):
        calls.append((first_build.name, second_build.name))
        return {"kind": "comparison", "call": len(calls)}

    monkeypatch.setattr(run_control, "simulate_build", fake_simulate)
    monkeypatch.setattr(run_control, "compare_builds", fake_compare)
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
    for request in (single, comp, rev, versioned):
        run_control.execute_canonical_request(request)
    assert len(calls) == 4


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
    calls = 0

    def flaky(build, scenario, seed):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        return {"ok": True}

    monkeypatch.setattr(run_control, "simulate_build", flaky)
    request = canonical_single_build_request(
        SingleBuildInputs(_build(), _scenario(), 1)
    )
    with pytest.raises(RuntimeError):
        run_control.execute_canonical_request(request)
    assert run_control.execute_canonical_request(request) == {"ok": True}
    assert calls == 2
