#!/usr/bin/env python3
"""Repeatable simulation benchmarks for representative combat scenarios."""

from __future__ import annotations

import argparse
import json
import platform
import time
from dataclasses import asdict, dataclass
from random import Random

from dnd_combat_simulator.combat import (
    AttackFeature,
    ResolutionType,
    SuccessfulSaveDamage,
)
from dnd_combat_simulator.simulation import (
    AttackProfile,
    ManagedResource,
    ResourceCost,
    TriggerFrequency,
    TriggerType,
    run_damage_simulations,
)


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    description: str
    simulations: int
    rounds: int
    profiles: tuple[AttackProfile, ...]
    resources: tuple[ManagedResource, ...] = ()


@dataclass(frozen=True)
class BenchmarkResult:
    name: str
    description: str
    simulations: int
    rounds: int
    runtime_seconds: float
    baseline_seconds: float | None
    percent_change_vs_baseline: float | None


def _cases(include_large: bool) -> tuple[BenchmarkCase, ...]:
    cases = [
        BenchmarkCase(
            "basic_attack",
            "One basic attack-roll profile.",
            10_000,
            3,
            (AttackProfile("Strike", 7, "1d8+4", 2),),
        ),
        BenchmarkCase(
            "five_profiles",
            "Five mixed attack-roll profiles.",
            10_000,
            3,
            tuple(AttackProfile(f"Strike {i}", 7, "1d8+4", 1) for i in range(5)),
        ),
        BenchmarkCase(
            "multi_target_saves",
            "Multi-target saving throws with half damage on successful saves.",
            10_000,
            3,
            (
                AttackProfile(
                    "Fireball",
                    None,
                    "8d6",
                    1,
                    affected_targets=6,
                    resolution_type=ResolutionType.SAVING_THROW,
                    save_dc=15,
                    successful_save_damage=SuccessfulSaveDamage.HALF_DAMAGE,
                ),
            ),
        ),
        BenchmarkCase(
            "triggered_attacks",
            "Follow-up attack triggers once per successful source hit.",
            10_000,
            3,
            (
                AttackProfile("Main", 7, "1d8+4", 2, attack_id="main"),
                AttackProfile(
                    "Rider",
                    7,
                    "1d6",
                    1,
                    attack_id="rider",
                    trigger_type=TriggerType.AFTER_SUCCESS,
                    trigger_source_attack_id="main",
                    trigger_frequency=TriggerFrequency.PER_SUCCESS,
                ),
            ),
        ),
        BenchmarkCase(
            "managed_resources",
            "Profiles consume a limited per-combat resource.",
            10_000,
            4,
            (
                AttackProfile(
                    "Smite",
                    7,
                    "1d8+4+2d8",
                    2,
                    resource_costs=(ResourceCost("slots", 1),),
                ),
            ),
            (ManagedResource("slots", "Spell slots", 3),),
        ),
        BenchmarkCase(
            "complex_dice",
            "Exploding, rerolled, keep/drop dice with damage features.",
            10_000,
            3,
            (
                AttackProfile(
                    "Complex",
                    7,
                    "4d6r<2!kh3+2d8dl1+4",
                    2,
                    features=frozenset(
                        {
                            AttackFeature.GREAT_WEAPON_FIGHTING,
                            AttackFeature.TAVERN_BRAWLER,
                        }
                    ),
                ),
            ),
        ),
        BenchmarkCase(
            "representative_10000",
            "Representative 10,000-simulation mixed workload.",
            10_000,
            5,
            (
                AttackProfile("Attack", 8, "1d10+5", 2, attack_id="attack"),
                AttackProfile(
                    "Save",
                    None,
                    "3d8",
                    1,
                    affected_targets=3,
                    resolution_type=ResolutionType.SAVING_THROW,
                    save_dc=16,
                    successful_save_damage=SuccessfulSaveDamage.HALF_DAMAGE,
                ),
            ),
        ),
    ]
    if include_large:
        cases.append(
            BenchmarkCase(
                "representative_100000",
                "Representative 100,000-simulation mixed workload.",
                100_000,
                5,
                cases[-1].profiles,
            )
        )
    return tuple(cases)


def _load_baseline(path: str | None) -> dict[str, float]:
    if path is None:
        return {}
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return {result["name"]: result["runtime_seconds"] for result in data["results"]}


def run_benchmarks(
    *, include_large: bool, baseline_path: str | None
) -> dict[str, object]:
    baseline = _load_baseline(baseline_path)
    results: list[BenchmarkResult] = []
    for case in _cases(include_large):
        started = time.perf_counter()
        run_damage_simulations(
            attack_bonus=7,
            target_armor_class=15,
            damage_dice="1d8+4",
            rounds=case.rounds,
            simulations=case.simulations,
            attack_profiles=case.profiles,
            managed_resources=case.resources,
            rng=Random(20260722),
        )
        runtime = time.perf_counter() - started
        baseline_seconds = baseline.get(case.name)
        percent_change = None
        if baseline_seconds:
            percent_change = ((runtime - baseline_seconds) / baseline_seconds) * 100
        results.append(
            BenchmarkResult(
                case.name,
                case.description,
                case.simulations,
                case.rounds,
                runtime,
                baseline_seconds,
                percent_change,
            )
        )
    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "results": [asdict(result) for result in results],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-large", action="store_true")
    parser.add_argument("--baseline-json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    data = run_benchmarks(
        include_large=args.include_large, baseline_path=args.baseline_json
    )
    if args.json:
        print(json.dumps(data, indent=2))
        return
    print(f"Python: {data['python_version']}")
    print(f"Platform: {data['platform']}")
    for result in data["results"]:
        baseline = result["baseline_seconds"]
        change = result["percent_change_vs_baseline"]
        suffix = ""
        if baseline is not None and change is not None:
            suffix = f" | baseline {baseline:.6f}s | change {change:+.1f}%"
        print(
            f"{result['name']}: {result['runtime_seconds']:.6f}s | "
            f"{result['simulations']} sims | {result['description']}{suffix}"
        )


if __name__ == "__main__":
    main()
