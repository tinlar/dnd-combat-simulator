from __future__ import annotations

from dnd_combat_simulator.simulation import AttackProfile, BuildConfig, ScenarioConfig
from dnd_combat_simulator.ui.run_control import (
    SingleBuildInputs,
    canonical_single_build_request,
)


def test_stage31_cache_request_is_stable_for_equivalent_inputs() -> None:
    profile = AttackProfile("Strike", 5, "1d8+3", 1, attack_id="strike")
    build = BuildConfig("Build", 5, "1d8+3", 1, attack_profiles=(profile,))
    scenario = ScenarioConfig(15, 3, 2, 10)

    first = canonical_single_build_request(SingleBuildInputs(build, scenario, seed=123))
    second = canonical_single_build_request(
        SingleBuildInputs(build, scenario, seed=123)
    )

    assert first == second
