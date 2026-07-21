"""Repeated combat simulation logic independent from the Streamlit interface."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
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
    active_rounds: str = ""


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


_ACTIVE_ROUNDS_GROUP_PATTERN = re.compile(r"\d+(?:\s*-\s*\d+)?")


def parse_active_rounds(active_rounds: str | None) -> frozenset[int] | None:
    """Parse an Active Rounds expression into sorted unique round numbers.

    Returns ``None`` when the expression is blank, meaning every scenario round.
    """
    text = (active_rounds or "").strip()
    if not text:
        return None

    rounds: set[int] = set()
    for group in text.split(","):
        group = group.strip()
        if not group:
            msg = "Active Rounds contains an empty comma group."
            raise ValueError(msg)
        if not _ACTIVE_ROUNDS_GROUP_PATTERN.fullmatch(group):
            msg = (
                "Active Rounds must contain positive integers or ranges such "
                "as 1-5, separated by commas."
            )
            raise ValueError(msg)
        if "-" in group:
            start_text, end_text = re.split(r"\s*-\s*", group, maxsplit=1)
            start = int(start_text)
            end = int(end_text)
            if start <= 0 or end <= 0:
                msg = "Active Rounds round numbers must be positive integers."
                raise ValueError(msg)
            if start > end:
                msg = "Active Rounds ranges must not be reversed."
                raise ValueError(msg)
            rounds.update(range(start, end + 1))
        else:
            round_number = int(group)
            if round_number <= 0:
                msg = "Active Rounds round numbers must be positive integers."
                raise ValueError(msg)
            rounds.add(round_number)

    return frozenset(sorted(rounds))


def _profile_id(profile: AttackProfile) -> str:
    return profile.name.strip()


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
        msg = f"{label} attack profile names must be unique."
        raise ValueError(msg)


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
    rng: RandomNumberGenerator | None = None,
) -> SimulationResult:
    """Run repeated damage simulations with one or more active attack profiles."""
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
        msg = "Attack profile names must be unique."
        raise ValueError(msg)
    active_round_sets = tuple(
        parse_active_rounds(profile.active_rounds) for profile in profiles
    )

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
            for profile_index, profile in enumerate(profiles):
                active_round_set = active_round_sets[profile_index]
                if (
                    active_round_set is not None
                    and round_number not in active_round_set
                ):
                    continue
                for _ in range(profile.attacks_per_round):
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
