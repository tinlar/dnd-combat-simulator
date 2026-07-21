"""Repeated combat simulation logic independent from the Streamlit interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from random import Random

from dnd_combat_simulator.combat import AttackRollMode, resolve_weapon_attack
from dnd_combat_simulator.dice import RandomNumberGenerator


@dataclass(frozen=True)
class AttackProfile:
    """One distinct attack routine within a build."""

    name: str
    attack_bonus: int
    damage_dice: str
    damage_modifier: int
    attacks_per_round: int
    attack_roll_mode: AttackRollMode = AttackRollMode.NORMAL


class UndefinedRoundBehavior(StrEnum):
    """How schedules resolve rounds after the final explicitly scheduled round."""

    REPEAT_FINAL_ROUND = "repeat_final_round"
    REPEAT_ENTIRE_SCHEDULE = "repeat_entire_schedule"
    NO_ATTACKS = "no_attacks"


@dataclass(frozen=True)
class AttackUse:
    """A scheduled use count for a reusable attack profile."""

    attack_profile_id: str
    number_of_attacks: int


@dataclass(frozen=True)
class RoundPlan:
    """Attack uses for one explicit round number."""

    round_number: int
    attack_uses: tuple[AttackUse, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RoundSchedule:
    """Ordered set of round plans for a build."""

    round_plans: tuple[RoundPlan, ...] = field(default_factory=tuple)
    undefined_round_behavior: UndefinedRoundBehavior = (
        UndefinedRoundBehavior.REPEAT_FINAL_ROUND
    )


@dataclass(frozen=True)
class RoundResult:
    """Summary statistics for one simulated round number."""

    round_number: int
    average_damage: float
    average_attacks: float
    hit_rate: float
    critical_hit_rate: float


@dataclass(frozen=True)
class AttackProfileResult:
    """Summary statistics for one attack profile inside a simulation."""

    attack_profile: AttackProfile
    total_attacks_made: int
    average_total_damage_per_simulation: float
    average_damage_per_round: float
    hit_rate: float
    critical_hit_rate: float


@dataclass(frozen=True)
class SimulationResult:
    """Summary statistics for repeated weapon-attack simulations."""

    simulations_run: int
    rounds_per_simulation: int
    attacks_per_round: int
    attack_roll_mode: AttackRollMode
    total_attacks_made: int
    average_total_damage_per_simulation: float
    average_damage_per_round: float
    hit_rate: float
    critical_hit_rate: float
    minimum_total_damage_in_simulation: int
    maximum_total_damage_in_simulation: int
    first_round_burst_damage: float = field(default=0, compare=False)
    average_damage_after_round_1: float = field(default=0, compare=False)
    highest_damage_round: int = field(default=1, compare=False)
    highest_round_average_damage: float = field(default=0, compare=False)
    average_total_damage: float = field(default=0, compare=False)
    attack_profile_results: tuple[AttackProfileResult, ...] = field(
        default_factory=tuple, compare=False
    )
    round_results: tuple[RoundResult, ...] = field(default_factory=tuple, compare=False)


@dataclass(frozen=True)
class BuildConfig:
    """Named combat build configuration for simulations and comparisons."""

    name: str
    attack_bonus: int
    damage_dice: str
    damage_modifier: int
    attacks_per_round: int
    attack_roll_mode: AttackRollMode = AttackRollMode.NORMAL
    attack_profiles: tuple[AttackProfile, ...] = field(default_factory=tuple)
    round_schedule: RoundSchedule | None = None

    def resolved_attack_profiles(self) -> tuple[AttackProfile, ...]:
        """Return explicit profiles or a compatibility profile from legacy fields."""
        if self.attack_profiles:
            return self.attack_profiles
        return (
            AttackProfile(
                name="Attack",
                attack_bonus=self.attack_bonus,
                damage_dice=self.damage_dice,
                damage_modifier=self.damage_modifier,
                attacks_per_round=self.attacks_per_round,
                attack_roll_mode=self.attack_roll_mode,
            ),
        )


@dataclass(frozen=True)
class ScenarioConfig:
    """Shared scenario inputs applied to every compared build."""

    target_armor_class: int
    rounds: int
    simulations: int


@dataclass(frozen=True)
class ComparisonDifference:
    """Build A minus Build B deltas for comparison metrics."""

    average_damage_per_round: float
    average_total_damage: float
    hit_rate: float
    critical_hit_rate: float


@dataclass(frozen=True)
class BuildComparisonResult:
    """Side-by-side result for two named builds in one shared scenario."""

    first_build: BuildConfig
    second_build: BuildConfig
    scenario: ScenarioConfig
    first_result: SimulationResult
    second_result: SimulationResult
    difference: ComparisonDifference
    higher_average_damage_build_name: str | None


def _profile_id(profile: AttackProfile) -> str:
    return profile.name.strip()


def _legacy_round_schedule(profiles: tuple[AttackProfile, ...]) -> RoundSchedule:
    return RoundSchedule(
        (
            RoundPlan(
                1,
                tuple(
                    AttackUse(_profile_id(profile), profile.attacks_per_round)
                    for profile in profiles
                ),
            ),
        ),
        UndefinedRoundBehavior.REPEAT_FINAL_ROUND,
    )


def _resolve_round_plan(schedule: RoundSchedule, round_number: int) -> RoundPlan:
    plans = schedule.round_plans
    if not plans:
        return RoundPlan(round_number, ())
    if round_number <= len(plans):
        return plans[round_number - 1]
    if schedule.undefined_round_behavior is UndefinedRoundBehavior.NO_ATTACKS:
        return RoundPlan(round_number, ())
    if (
        schedule.undefined_round_behavior
        is UndefinedRoundBehavior.REPEAT_ENTIRE_SCHEDULE
    ):
        return plans[(round_number - 1) % len(plans)]
    return plans[-1]


def _validate_round_schedule(
    schedule: RoundSchedule, profiles: tuple[AttackProfile, ...], *, label: str
) -> None:
    profile_ids = {_profile_id(profile) for profile in profiles}
    seen_rounds: set[int] = set()
    expected_round = 1
    for plan in schedule.round_plans:
        if plan.round_number in seen_rounds:
            msg = f"{label} round schedule has duplicate round {plan.round_number}."
            raise ValueError(msg)
        if plan.round_number != expected_round:
            msg = (
                f"{label} round schedule round numbers must be ordered and start at 1."
            )
            raise ValueError(msg)
        seen_rounds.add(plan.round_number)
        expected_round += 1
        seen_profiles: set[str] = set()
        for attack_use in plan.attack_uses:
            if attack_use.number_of_attacks < 0:
                msg = (
                    f"{label} round {plan.round_number} attack counts cannot "
                    "be negative."
                )
                raise ValueError(msg)
            if attack_use.attack_profile_id not in profile_ids:
                msg = (
                    f"{label} round {plan.round_number} references unknown attack "
                    f"profile '{attack_use.attack_profile_id}'."
                )
                raise ValueError(msg)
            if attack_use.attack_profile_id in seen_profiles:
                msg = (
                    f"{label} round {plan.round_number} contains duplicate uses of "
                    f"'{attack_use.attack_profile_id}'. Combine them into one row."
                )
                raise ValueError(msg)
            seen_profiles.add(attack_use.attack_profile_id)


def _validate_attack_profile(profile: AttackProfile, *, label: str) -> None:
    if not profile.name.strip():
        msg = f"{label} attack name is required."
        raise ValueError(msg)
    if not profile.damage_dice.strip():
        msg = f"{label} damage dice is required. Use notation such as 1d8."
        raise ValueError(msg)
    if profile.attacks_per_round < 1:
        msg = f"{label} attacks per round must be at least 1."
        if label == "Attack profile 1":
            msg = "Attacks per round must be at least 1."
        raise ValueError(msg)


def _validate_build(build: BuildConfig, *, label: str) -> None:
    if not build.name.strip():
        msg = f"{label} build name is required."
        raise ValueError(msg)
    profiles = build.resolved_attack_profiles()
    if not profiles:
        msg = f"{label} build must include at least one attack profile."
        raise ValueError(msg)
    for index, profile in enumerate(profiles, start=1):
        _validate_attack_profile(profile, label=f"{label} profile {index}")
    if len({_profile_id(profile) for profile in profiles}) != len(profiles):
        msg = f"{label} attack profile names must be unique for scheduling."
        raise ValueError(msg)
    _validate_round_schedule(
        build.round_schedule or _legacy_round_schedule(profiles), profiles, label=label
    )


def _validate_scenario(scenario: ScenarioConfig) -> None:
    if scenario.target_armor_class < 1:
        msg = "Target Armor Class must be at least 1."
        raise ValueError(msg)
    if scenario.rounds < 1:
        msg = "Number of rounds must be at least 1."
        raise ValueError(msg)
    if scenario.simulations < 1:
        msg = "Number of simulations must be at least 1."
        raise ValueError(msg)


def run_damage_simulations(
    *,
    attack_bonus: int,
    target_armor_class: int,
    damage_dice: str,
    damage_modifier: int,
    rounds: int,
    simulations: int,
    attacks_per_round: int = 1,
    attack_roll_mode: AttackRollMode = AttackRollMode.NORMAL,
    attack_profiles: tuple[AttackProfile, ...] | None = None,
    round_schedule: RoundSchedule | None = None,
    rng: RandomNumberGenerator | None = None,
) -> SimulationResult:
    """Run repeated damage simulations with one or more scheduled attack profiles."""
    if rounds < 1:
        msg = "Number of rounds must be at least 1."
        raise ValueError(msg)
    if simulations < 1:
        msg = "Number of simulations must be at least 1."
        raise ValueError(msg)

    profiles = (
        (
            AttackProfile(
                name="Attack",
                attack_bonus=attack_bonus,
                damage_dice=damage_dice,
                damage_modifier=damage_modifier,
                attacks_per_round=attacks_per_round,
                attack_roll_mode=attack_roll_mode,
            ),
        )
        if attack_profiles is None
        else attack_profiles
    )
    if not profiles:
        msg = "At least one attack profile is required."
        raise ValueError(msg)
    for index, profile in enumerate(profiles, start=1):
        _validate_attack_profile(profile, label=f"Attack profile {index}")
    if len({_profile_id(profile) for profile in profiles}) != len(profiles):
        msg = "Attack profile names must be unique for scheduling."
        raise ValueError(msg)

    schedule = round_schedule or _legacy_round_schedule(profiles)
    _validate_round_schedule(schedule, profiles, label="Build")
    profile_by_id = {
        _profile_id(profile): index for index, profile in enumerate(profiles)
    }

    random_number_generator = rng if rng is not None else Random()
    total_rounds = rounds * simulations
    total_attacks = 0
    total_damage_all_simulations = 0
    total_hits = 0
    total_critical_hits = 0
    profile_damage_totals = dict.fromkeys(range(len(profiles)), 0)
    profile_attacks = dict.fromkeys(range(len(profiles)), 0)
    profile_hits = dict.fromkeys(range(len(profiles)), 0)
    profile_critical_hits = dict.fromkeys(range(len(profiles)), 0)
    round_damage_totals = dict.fromkeys(range(1, rounds + 1), 0)
    round_attacks = dict.fromkeys(range(1, rounds + 1), 0)
    round_hits = dict.fromkeys(range(1, rounds + 1), 0)
    round_critical_hits = dict.fromkeys(range(1, rounds + 1), 0)
    minimum_total_damage: int | None = None
    maximum_total_damage: int | None = None

    for _ in range(simulations):
        simulation_damage = 0
        for round_number in range(1, rounds + 1):
            plan = _resolve_round_plan(schedule, round_number)
            for attack_use in plan.attack_uses:
                profile_index = profile_by_id[attack_use.attack_profile_id]
                profile = profiles[profile_index]
                for _ in range(attack_use.number_of_attacks):
                    attack = resolve_weapon_attack(
                        attack_bonus=profile.attack_bonus,
                        target_armor_class=target_armor_class,
                        damage_dice=profile.damage_dice.strip(),
                        damage_modifier=profile.damage_modifier,
                        attack_roll_mode=profile.attack_roll_mode,
                        rng=random_number_generator,
                    )
                    simulation_damage += attack.damage_dealt
                    round_damage_totals[round_number] += attack.damage_dealt
                    profile_damage_totals[profile_index] += attack.damage_dealt
                    total_attacks += 1
                    round_attacks[round_number] += 1
                    profile_attacks[profile_index] += 1
                    total_hits += int(attack.hit)
                    round_hits[round_number] += int(attack.hit)
                    profile_hits[profile_index] += int(attack.hit)
                    total_critical_hits += int(attack.critical_hit)
                    round_critical_hits[round_number] += int(attack.critical_hit)
                    profile_critical_hits[profile_index] += int(attack.critical_hit)

        total_damage_all_simulations += simulation_damage
        minimum_total_damage = (
            simulation_damage
            if minimum_total_damage is None
            else min(minimum_total_damage, simulation_damage)
        )
        maximum_total_damage = (
            simulation_damage
            if maximum_total_damage is None
            else max(maximum_total_damage, simulation_damage)
        )

    profile_results = tuple(
        AttackProfileResult(
            attack_profile=profile,
            total_attacks_made=profile_attacks[index],
            average_total_damage_per_simulation=(
                profile_damage_totals[index] / simulations
            ),
            average_damage_per_round=profile_damage_totals[index] / total_rounds,
            hit_rate=(profile_hits[index] / profile_attacks[index])
            if profile_attacks[index]
            else 0,
            critical_hit_rate=(
                profile_critical_hits[index] / profile_attacks[index]
                if profile_attacks[index]
                else 0
            ),
        )
        for index, profile in enumerate(profiles)
    )
    round_results = tuple(
        RoundResult(
            round_number=round_number,
            average_damage=round_damage_totals[round_number] / simulations,
            average_attacks=round_attacks[round_number] / simulations,
            hit_rate=(round_hits[round_number] / round_attacks[round_number])
            if round_attacks[round_number]
            else 0,
            critical_hit_rate=(
                round_critical_hits[round_number] / round_attacks[round_number]
                if round_attacks[round_number]
                else 0
            ),
        )
        for round_number in range(1, rounds + 1)
    )
    first_round_burst = round_results[0].average_damage
    average_after_round_1 = (
        sum(result.average_damage for result in round_results[1:]) / (rounds - 1)
        if rounds > 1
        else 0
    )
    highest = max(round_results, key=lambda result: result.average_damage)

    return SimulationResult(
        simulations_run=simulations,
        rounds_per_simulation=rounds,
        attacks_per_round=int(
            round(sum(result.average_attacks for result in round_results) / rounds)
        ),
        attack_roll_mode=profiles[0].attack_roll_mode,
        total_attacks_made=total_attacks,
        average_total_damage_per_simulation=total_damage_all_simulations / simulations,
        average_damage_per_round=total_damage_all_simulations / total_rounds,
        hit_rate=total_hits / total_attacks if total_attacks else 0,
        critical_hit_rate=total_critical_hits / total_attacks if total_attacks else 0,
        minimum_total_damage_in_simulation=minimum_total_damage or 0,
        maximum_total_damage_in_simulation=maximum_total_damage or 0,
        first_round_burst_damage=first_round_burst,
        average_damage_after_round_1=average_after_round_1,
        highest_damage_round=highest.round_number,
        highest_round_average_damage=highest.average_damage,
        average_total_damage=total_damage_all_simulations / simulations,
        attack_profile_results=profile_results,
        round_results=round_results,
    )


def compare_builds(
    *,
    first_build: BuildConfig,
    second_build: BuildConfig,
    scenario: ScenarioConfig,
    seed: int,
) -> BuildComparisonResult:
    """Run two builds against one scenario with fair deterministic randomness.

    Each build receives a separate ``random.Random`` instance initialized with the
    same seed. The two simulations are therefore repeatable and consume identical
    random-number streams without sharing mutable RNG state.
    """
    _validate_scenario(scenario)
    _validate_build(first_build, label="First")
    _validate_build(second_build, label="Second")

    first_result = run_damage_simulations(
        attack_bonus=first_build.attack_bonus,
        target_armor_class=scenario.target_armor_class,
        damage_dice=first_build.damage_dice.strip(),
        damage_modifier=first_build.damage_modifier,
        rounds=scenario.rounds,
        simulations=scenario.simulations,
        attacks_per_round=first_build.attacks_per_round,
        attack_roll_mode=first_build.attack_roll_mode,
        attack_profiles=first_build.resolved_attack_profiles(),
        round_schedule=first_build.round_schedule,
        rng=Random(seed),
    )
    second_result = run_damage_simulations(
        attack_bonus=second_build.attack_bonus,
        target_armor_class=scenario.target_armor_class,
        damage_dice=second_build.damage_dice.strip(),
        damage_modifier=second_build.damage_modifier,
        rounds=scenario.rounds,
        simulations=scenario.simulations,
        attacks_per_round=second_build.attacks_per_round,
        attack_roll_mode=second_build.attack_roll_mode,
        attack_profiles=second_build.resolved_attack_profiles(),
        round_schedule=second_build.round_schedule,
        rng=Random(seed),
    )

    if first_result.average_damage_per_round > second_result.average_damage_per_round:
        higher_name = first_build.name.strip()
    elif second_result.average_damage_per_round > first_result.average_damage_per_round:
        higher_name = second_build.name.strip()
    else:
        higher_name = None

    return BuildComparisonResult(
        first_build=first_build,
        second_build=second_build,
        scenario=scenario,
        first_result=first_result,
        second_result=second_result,
        difference=ComparisonDifference(
            average_damage_per_round=(
                first_result.average_damage_per_round
                - second_result.average_damage_per_round
            ),
            average_total_damage=(
                first_result.average_total_damage_per_simulation
                - second_result.average_total_damage_per_simulation
            ),
            hit_rate=first_result.hit_rate - second_result.hit_rate,
            critical_hit_rate=(
                first_result.critical_hit_rate - second_result.critical_hit_rate
            ),
        ),
        higher_average_damage_build_name=higher_name,
    )
