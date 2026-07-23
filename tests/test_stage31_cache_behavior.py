from __future__ import annotations

import pytest

from dnd_combat_simulator.simulation import (
    AttackProfile,
    BuildConfig,
    ScenarioConfig,
    SimulationResult,
)
from dnd_combat_simulator.ui import run_control
from dnd_combat_simulator.ui.run_control import CanonicalSimulationRequest


def _request(
    seed: int = 1, simulations: int = 2, damage: str = "1d4"
) -> CanonicalSimulationRequest:
    build = BuildConfig(
        "A",
        5,
        damage,
        1,
        attack_profiles=(AttackProfile("A", 5, damage, 1, attack_id="a"),),
    )
    return CanonicalSimulationRequest(
        1, False, ScenarioConfig(15, 1, simulations), build, None, simulations, seed
    )


def test_invalid_request_never_calls_cache_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def cached(request):
        nonlocal calls
        calls += 1
        return SimulationResult(1, 1, 1)

    monkeypatch.setattr(run_control, "_cached_execute_canonical_request", cached)
    bad = _request(simulations=0)
    with pytest.raises(ValueError):
        run_control.execute_canonical_request(bad)
    assert calls == 0


def test_failed_engine_execution_is_not_cached_by_test_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def cached(request):
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    monkeypatch.setattr(run_control, "_cached_execute_canonical_request", cached)
    with pytest.raises(RuntimeError):
        run_control.execute_canonical_request(_request())
    with pytest.raises(RuntimeError):
        run_control.execute_canonical_request(_request())
    assert calls == 2
