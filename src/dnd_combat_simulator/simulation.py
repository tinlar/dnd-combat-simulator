"""Repeated combat simulation logic independent from the Streamlit interface."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from random import Random

from dnd_combat_simulator.combat import (
    AttackFeature,
    AttackRollMode,
    ResolutionType,
    SuccessfulSaveDamage,
    resolve_automatic_damage,
    resolve_saving_throw_damage,
    resolve_weapon_attack,
    validate_feature_resolution_combination,
)
from dnd_combat_simulator.dice import RandomNumberGenerator, roll_damage_formula


class TriggerType(StrEnum):
    ALWAYS = "always"
    AFTER_SUCCESS = "after_success"
    AFTER_FAILURE = "after_failure"
    AFTER_CRITICAL = "after_critical"
    SOMETIMES = "sometimes"


class TriggerFrequency(StrEnum):
    PER_SUCCESS = "per_success"
    ONCE_PER_ROUND = "once_per_round"
    ONCE_PER_COMBAT = "once_per_combat"
    # Backward-compatible alias for previously saved shared links.
    ONCE_IF_ANY = "once_if_any"


def _normalized_trigger_frequency(value: TriggerFrequency | str) -> TriggerFrequency:
    frequency = TriggerFrequency(value)
    if frequency is TriggerFrequency.ONCE_IF_ANY:
        return TriggerFrequency.ONCE_PER_ROUND
    return frequency


@dataclass(frozen=True)
class AttackProfile:
    """One distinct attack routine within a build."""

    name: str
    attack_bonus: int | None
    damage_dice: str
    attacks_per_round: int
    affected_targets: int = 1
    attack_roll_mode: AttackRollMode = AttackRollMode.NORMAL
    active_rounds: str = ""
    resolution_type: ResolutionType = ResolutionType.ATTACK_ROLL
    save_dc: int | None = None
    successful_save_damage: SuccessfulSaveDamage = SuccessfulSaveDamage.NO_DAMAGE
    features: frozenset[AttackFeature] = frozenset()
    attack_id: str = ""
    trigger_type: TriggerType = TriggerType.ALWAYS
    trigger_source_attack_id: str | None = None
    trigger_frequency: TriggerFrequency = TriggerFrequency.PER_SUCCESS
    trigger_chance_percent: int | None = None


@dataclass(frozen=True)
class RoundResult:
    """Summary statistics for one simulated round number."""

    round_number: int
    average_damage: float
    average_attacks: float
    hit_rate: float
    critical_hit_rate: float
    average_targets_affected: float = field(default=0, compare=False)
    average_individual_damage: float = field(default=0, compare=False)
    failed_save_rate: float = 0
    successful_save_rate: float = 0


@dataclass(frozen=True)
class AttackProfileResult:
    """Summary statistics for one attack profile inside a simulation."""

    attack_profile: AttackProfile
    total_attacks_made: int
    average_total_damage_per_simulation: float
    average_damage_per_round: float
    hit_rate: float
    critical_hit_rate: float
    average_damage_per_use: float = field(default=0, compare=False)
    total_profile_uses: int = field(default=0, compare=False)
    failed_save_rate: float = 0
    successful_save_rate: float = 0
    total_target_resolutions: int = field(default=0, compare=False)
    total_targets_affected: int = field(default=0, compare=False)
    average_damage_per_target_per_round: float = field(default=0, compare=False)
    automatic_damage_applications: int = field(default=0, compare=False)
    average_automatic_damage_per_application: float = field(default=0, compare=False)
    total_skipped_profile_uses: int = field(default=0, compare=False)
    average_skipped_profile_uses_per_simulation: float = field(default=0, compare=False)
    configured_profile_uses: int = field(default=0, compare=False)
    triggered_profile_uses: int = field(default=0, compare=False)
    average_triggered_profile_uses_per_simulation: float = field(
        default=0, compare=False
    )
    average_executions_per_combat: float = field(default=0, compare=False)
    average_executions_per_round: float = field(default=0, compare=False)


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
    failed_save_rate: float = 0
    successful_save_rate: float = 0
    total_target_resolutions: int = field(default=0, compare=False)
    total_targets_affected: int = field(default=0, compare=False)
    average_damage_per_target_per_round: float = field(default=0, compare=False)
    automatic_damage_applications: int = field(default=0, compare=False)
    average_automatic_damage_per_application: float = field(default=0, compare=False)
    first_round_burst_damage: float = field(default=0, compare=False)
    average_damage_after_round_1: float = field(default=0, compare=False)
    highest_damage_round: int = field(default=1, compare=False)
    highest_round_average_damage: float = field(default=0, compare=False)
    average_total_damage: float = field(default=0, compare=False)
    attack_profile_results: tuple[AttackProfileResult, ...] = field(
        default_factory=tuple, compare=False
    )
    round_results: tuple[RoundResult, ...] = field(default_factory=tuple, compare=False)
    total_skipped_profile_uses: int = field(default=0, compare=False)
    average_skipped_profile_uses_per_simulation: float = field(default=0, compare=False)
    configured_profile_uses: int = field(default=0, compare=False)
    triggered_profile_uses: int = field(default=0, compare=False)
    average_triggered_profile_uses_per_simulation: float = field(
        default=0, compare=False
    )


@dataclass(frozen=True)
class BuildConfig:
    """Named combat build configuration for simulations and comparisons."""

    name: str
    attack_bonus: int
    damage_dice: str
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
    enemy_save_bonus: int = 3


@dataclass(frozen=True)
class ComparisonDifference:
    """Build A minus Build B deltas for comparison metrics."""

    average_damage_per_round: float
    average_total_damage: float
    hit_rate: float
    critical_hit_rate: float
    average_damage_per_target_per_round: float = 0


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
    return profile.attack_id.strip() or profile.name.strip()


def validate_trigger_dependencies(
    profiles: tuple[AttackProfile, ...], *, label: str = "Build"
) -> None:
    ids = [_profile_id(profile) for profile in profiles]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{label} attack profile IDs must be unique.")
    id_to_index = {attack_id: index for index, attack_id in enumerate(ids)}
    edges: dict[str, str] = {}
    for index, profile in enumerate(profiles):
        trigger_type = TriggerType(profile.trigger_type)
        if trigger_type in (TriggerType.ALWAYS, TriggerType.SOMETIMES):
            continue
        source_id = profile.trigger_source_attack_id
        if not source_id:
            raise ValueError(f"{label} profile {index + 1} trigger source is required.")
        own_id = ids[index]
        if source_id == own_id:
            raise ValueError(f"{label} profile {index + 1} cannot trigger itself.")
        if source_id not in id_to_index:
            raise ValueError(
                f"{label} profile {index + 1} trigger source no longer exists."
            )
        source_resolution = ResolutionType(
            profiles[id_to_index[source_id]].resolution_type
        )
        if (
            trigger_type is TriggerType.AFTER_CRITICAL
            and source_resolution is not ResolutionType.ATTACK_ROLL
        ):
            raise ValueError(
                f"{label} profile {index + 1} critical-hit trigger "
                "source must use attack rolls."
            )
        _normalized_trigger_frequency(profile.trigger_frequency)
        edges[own_id] = source_id
    for attack_id in ids:
        seen: set[str] = set()
        current = attack_id
        while current in edges:
            current = edges[current]
            if current in seen:
                raise ValueError(f"{label} trigger dependencies contain a cycle.")
            seen.add(current)


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
    if not isinstance(profile.affected_targets, int) or profile.affected_targets < 1:
        msg = f"{label} affected targets must be an integer of at least 1."
        raise ValueError(msg)
    resolution_type = ResolutionType(profile.resolution_type)
    features = frozenset(AttackFeature(feature) for feature in profile.features)
    validate_feature_resolution_combination(
        features,
        resolution_type,
        label=label,
        affected_targets=profile.affected_targets,
    )
    if resolution_type is ResolutionType.ATTACK_ROLL and profile.attack_bonus is None:
        msg = f"{label} Attack Bonus is required for attack-roll profiles."
        raise ValueError(msg)
    if TriggerType(profile.trigger_type) is TriggerType.SOMETIMES:
        if (
            not isinstance(profile.trigger_chance_percent, int)
            or profile.trigger_chance_percent < 1
            or profile.trigger_chance_percent > 100
        ):
            msg = (
                f"{label} Sometimes percentage chance must be a whole number "
                "from 1 through 100."
            )
            raise ValueError(msg)
    if resolution_type is ResolutionType.SAVING_THROW:
        if profile.save_dc is None:
            msg = f"{label} Save DC is required for saving-throw profiles."
            raise ValueError(msg)
        if profile.save_dc < 1:
            msg = f"{label} Save DC must be a positive integer."
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
    validate_trigger_dependencies(profiles, label=label)


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
    enemy_save_bonus: int = 3,
    rounds: int,
    simulations: int,
    attacks_per_round: int = 1,
    attack_roll_mode: AttackRollMode = AttackRollMode.NORMAL,
    attack_profiles: tuple[AttackProfile, ...] | None = None,
    rng: RandomNumberGenerator | None = None,
) -> SimulationResult:
    """Run repeated damage simulations with one or more active attack profiles.

    Deterministic roll order is simulation, round, attack profile, profile use,
    then target. Attack-roll profiles roll the target's attack roll before that
    target's damage if it hits. Multi-target saving-throw profiles roll one
    shared damage result for the profile use before each target's saving throw.
    """
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
    validate_trigger_dependencies(profiles, label="Attack profiles")
    active_round_sets = tuple(
        parse_active_rounds(profile.active_rounds) for profile in profiles
    )

    random_number_generator = rng if rng is not None else Random()
    total_rounds = rounds * simulations
    total_attacks = 0
    total_skipped_attacks = 0
    total_target_resolutions = 0
    total_attack_roll_resolutions = 0
    total_saving_throw_resolutions = 0
    total_automatic_damage_applications = 0
    total_damage_all_simulations = 0
    total_hits = 0
    total_critical_hits = 0
    total_failed_saves = 0
    total_successful_saves = 0
    profile_damage_totals = dict.fromkeys(range(len(profiles)), 0)
    profile_attacks = dict.fromkeys(range(len(profiles)), 0)
    profile_skipped_attacks = dict.fromkeys(range(len(profiles)), 0)
    profile_configured_uses = dict.fromkeys(range(len(profiles)), 0)
    profile_triggered_uses = dict.fromkeys(range(len(profiles)), 0)
    profile_target_resolutions = dict.fromkeys(range(len(profiles)), 0)
    profile_attack_roll_resolutions = dict.fromkeys(range(len(profiles)), 0)
    profile_saving_throw_resolutions = dict.fromkeys(range(len(profiles)), 0)
    profile_automatic_damage_applications = dict.fromkeys(range(len(profiles)), 0)
    profile_hits = dict.fromkeys(range(len(profiles)), 0)
    profile_critical_hits = dict.fromkeys(range(len(profiles)), 0)
    profile_failed_saves = dict.fromkeys(range(len(profiles)), 0)
    profile_successful_saves = dict.fromkeys(range(len(profiles)), 0)
    profile_targets_affected_total = dict.fromkeys(range(len(profiles)), 0)
    profile_individual_damage_total = dict.fromkeys(range(len(profiles)), 0.0)
    round_damage_totals = dict.fromkeys(range(1, rounds + 1), 0)
    round_attacks = dict.fromkeys(range(1, rounds + 1), 0)
    round_targets_affected_totals = dict.fromkeys(range(1, rounds + 1), 0)
    round_individual_damage_totals = dict.fromkeys(range(1, rounds + 1), 0.0)
    round_target_resolutions = dict.fromkeys(range(1, rounds + 1), 0)
    round_attack_roll_resolutions = dict.fromkeys(range(1, rounds + 1), 0)
    round_saving_throw_resolutions = dict.fromkeys(range(1, rounds + 1), 0)
    round_hits = dict.fromkeys(range(1, rounds + 1), 0)
    round_critical_hits = dict.fromkeys(range(1, rounds + 1), 0)
    round_failed_saves = dict.fromkeys(range(1, rounds + 1), 0)
    round_successful_saves = dict.fromkeys(range(1, rounds + 1), 0)
    minimum_total_damage: int | None = None
    maximum_total_damage: int | None = None

    def record_target_damage(
        *,
        profile_index: int,
        round_number: int,
        damage: int,
    ) -> None:
        if damage <= 0:
            return
        round_targets_affected_totals[round_number] += 1
        round_individual_damage_totals[round_number] += damage
        profile_targets_affected_total[profile_index] += 1
        profile_individual_damage_total[profile_index] += damage

    for _ in range(simulations):
        simulation_damage = 0
        combat_triggered_once: dict[tuple[int, int], bool] = {}
        for round_number in range(1, rounds + 1):
            successful_resolutions_by_profile = dict.fromkeys(range(len(profiles)), 0)
            failed_resolutions_by_profile = dict.fromkeys(range(len(profiles)), 0)
            critical_resolutions_by_profile = dict.fromkeys(range(len(profiles)), 0)
            for profile_index, profile in enumerate(profiles):
                active_round_set = active_round_sets[profile_index]
                if (
                    active_round_set is not None
                    and round_number not in active_round_set
                ):
                    continue
                trigger_type = TriggerType(profile.trigger_type)
                if trigger_type is TriggerType.SOMETIMES:
                    execution_count = int(
                        random_number_generator.randint(1, 100)
                        <= (profile.trigger_chance_percent or 0)
                    )
                    configured_uses = 0
                elif trigger_type is not TriggerType.ALWAYS:
                    source_index = next(
                        index
                        for index, source_profile in enumerate(profiles)
                        if _profile_id(source_profile)
                        == profile.trigger_source_attack_id
                    )
                    if trigger_type is TriggerType.AFTER_SUCCESS:
                        qualifying_resolutions = successful_resolutions_by_profile[
                            source_index
                        ]
                    elif trigger_type is TriggerType.AFTER_FAILURE:
                        qualifying_resolutions = failed_resolutions_by_profile[
                            source_index
                        ]
                    else:
                        qualifying_resolutions = critical_resolutions_by_profile[
                            source_index
                        ]
                    frequency = _normalized_trigger_frequency(profile.trigger_frequency)
                    if frequency is TriggerFrequency.PER_SUCCESS:
                        execution_count = qualifying_resolutions
                    elif frequency is TriggerFrequency.ONCE_PER_ROUND:
                        execution_count = int(qualifying_resolutions > 0)
                    else:
                        combat_key = (profile_index, source_index)
                        already_triggered = combat_triggered_once.get(combat_key, False)
                        execution_count = int(
                            qualifying_resolutions > 0 and not already_triggered
                        )
                        if execution_count:
                            combat_triggered_once[combat_key] = True
                    configured_uses = 0
                else:
                    execution_count = profile.attacks_per_round
                    configured_uses = profile.attacks_per_round
                profile_configured_uses[profile_index] += configured_uses
                if trigger_type is not TriggerType.ALWAYS:
                    profile_triggered_uses[profile_index] += execution_count
                stop_profile_after_miss = False
                for attack_index in range(execution_count):
                    if stop_profile_after_miss:
                        skipped = execution_count - attack_index
                        total_skipped_attacks += skipped
                        profile_skipped_attacks[profile_index] += skipped
                        break
                    total_attacks += 1
                    round_attacks[round_number] += 1
                    profile_attacks[profile_index] += 1
                    if (
                        ResolutionType(profile.resolution_type)
                        is ResolutionType.ATTACK_ROLL
                    ):
                        for _target_index in range(profile.affected_targets):
                            attack = resolve_weapon_attack(
                                attack_bonus=profile.attack_bonus or 0,
                                target_armor_class=target_armor_class,
                                damage_dice=profile.damage_dice.strip(),
                                attack_roll_mode=profile.attack_roll_mode,
                                rng=random_number_generator,
                                features=profile.features,
                            )
                            damage = attack.damage_dealt
                            simulation_damage += damage
                            round_damage_totals[round_number] += damage
                            profile_damage_totals[profile_index] += damage
                            record_target_damage(
                                profile_index=profile_index,
                                round_number=round_number,
                                damage=damage,
                            )
                            total_target_resolutions += 1
                            profile_target_resolutions[profile_index] += 1
                            round_target_resolutions[round_number] += 1
                            total_attack_roll_resolutions += 1
                            profile_attack_roll_resolutions[profile_index] += 1
                            round_attack_roll_resolutions[round_number] += 1
                            total_hits += int(attack.hit)
                            round_hits[round_number] += int(attack.hit)
                            profile_hits[profile_index] += int(attack.hit)
                            successful_resolutions_by_profile[profile_index] += int(
                                attack.hit
                            )
                            failed_resolutions_by_profile[profile_index] += int(
                                not attack.hit
                            )
                            critical_resolutions_by_profile[profile_index] += int(
                                attack.critical_hit
                            )
                            total_critical_hits += int(attack.critical_hit)
                            round_critical_hits[round_number] += int(
                                attack.critical_hit
                            )
                            profile_critical_hits[profile_index] += int(
                                attack.critical_hit
                            )
                            if (
                                AttackFeature.STOP_ON_MISS in profile.features
                                and not attack.hit
                            ):
                                stop_profile_after_miss = True
                    elif (
                        ResolutionType(profile.resolution_type)
                        is ResolutionType.SAVING_THROW
                    ):
                        if profile.affected_targets == 1:
                            save = resolve_saving_throw_damage(
                                save_dc=profile.save_dc or 0,
                                enemy_save_bonus=enemy_save_bonus,
                                damage_dice=profile.damage_dice.strip(),
                                successful_save_damage=(profile.successful_save_damage),
                                rng=random_number_generator,
                                features=profile.features,
                            )
                            damage = save.damage_dealt
                            simulation_damage += damage
                            round_damage_totals[round_number] += damage
                            profile_damage_totals[profile_index] += damage
                            record_target_damage(
                                profile_index=profile_index,
                                round_number=round_number,
                                damage=damage,
                            )
                            total_target_resolutions += 1
                            profile_target_resolutions[profile_index] += 1
                            round_target_resolutions[round_number] += 1
                            total_saving_throw_resolutions += 1
                            profile_saving_throw_resolutions[profile_index] += 1
                            round_saving_throw_resolutions[round_number] += 1
                            total_failed_saves += int(save.failed_save)
                            round_failed_saves[round_number] += int(save.failed_save)
                            profile_failed_saves[profile_index] += int(save.failed_save)
                            successful_resolutions_by_profile[profile_index] += int(
                                save.failed_save
                            )
                            failed_resolutions_by_profile[profile_index] += int(
                                save.successful_save
                            )
                            total_successful_saves += int(save.successful_save)
                            round_successful_saves[round_number] += int(
                                save.successful_save
                            )
                            profile_successful_saves[profile_index] += int(
                                save.successful_save
                            )
                            continue
                        shared_damage = roll_damage_formula(
                            profile.damage_dice.strip(),
                            rng=random_number_generator,
                            features=frozenset(
                                feature.value for feature in profile.features
                            ),
                        )
                        for _target_index in range(profile.affected_targets):
                            natural_save = random_number_generator.randint(1, 20)
                            successful_save = natural_save + enemy_save_bonus >= (
                                profile.save_dc or 0
                            )
                            failed_save = not successful_save
                            if failed_save:
                                damage = shared_damage
                            elif (
                                profile.successful_save_damage
                                is SuccessfulSaveDamage.HALF_DAMAGE
                                or AttackFeature.POTENT_CANTRIP in profile.features
                            ):
                                damage = shared_damage // 2
                            else:
                                damage = 0
                            simulation_damage += damage
                            round_damage_totals[round_number] += damage
                            profile_damage_totals[profile_index] += damage
                            record_target_damage(
                                profile_index=profile_index,
                                round_number=round_number,
                                damage=damage,
                            )
                            total_target_resolutions += 1
                            profile_target_resolutions[profile_index] += 1
                            round_target_resolutions[round_number] += 1
                            total_saving_throw_resolutions += 1
                            profile_saving_throw_resolutions[profile_index] += 1
                            round_saving_throw_resolutions[round_number] += 1
                            total_failed_saves += int(failed_save)
                            round_failed_saves[round_number] += int(failed_save)
                            profile_failed_saves[profile_index] += int(failed_save)
                            successful_resolutions_by_profile[profile_index] += int(
                                failed_save
                            )
                            failed_resolutions_by_profile[profile_index] += int(
                                successful_save
                            )
                            total_successful_saves += int(successful_save)
                            round_successful_saves[round_number] += int(successful_save)
                            profile_successful_saves[profile_index] += int(
                                successful_save
                            )

                    else:
                        for _target_index in range(profile.affected_targets):
                            automatic = resolve_automatic_damage(
                                damage_dice=profile.damage_dice.strip(),
                                rng=random_number_generator,
                                features=profile.features,
                            )
                            damage = automatic.damage_dealt
                            simulation_damage += damage
                            round_damage_totals[round_number] += damage
                            profile_damage_totals[profile_index] += damage
                            record_target_damage(
                                profile_index=profile_index,
                                round_number=round_number,
                                damage=damage,
                            )
                            total_target_resolutions += 1
                            profile_target_resolutions[profile_index] += 1
                            round_target_resolutions[round_number] += 1
                            total_automatic_damage_applications += 1
                            profile_automatic_damage_applications[profile_index] += 1
                            successful_resolutions_by_profile[profile_index] += 1

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
            average_damage_per_use=(
                profile_damage_totals[index] / profile_attacks[index]
                if profile_attacks[index]
                else 0
            ),
            total_profile_uses=profile_attacks[index],
            hit_rate=(
                (profile_hits[index] / profile_attack_roll_resolutions[index])
                if profile_attack_roll_resolutions[index]
                else 0
            ),
            critical_hit_rate=(
                profile_critical_hits[index] / profile_attack_roll_resolutions[index]
                if profile_attack_roll_resolutions[index]
                else 0
            ),
            failed_save_rate=(
                profile_failed_saves[index] / profile_saving_throw_resolutions[index]
                if profile_saving_throw_resolutions[index]
                else 0
            ),
            successful_save_rate=(
                profile_successful_saves[index]
                / profile_saving_throw_resolutions[index]
                if profile_saving_throw_resolutions[index]
                else 0
            ),
            total_target_resolutions=profile_target_resolutions[index],
            total_targets_affected=profile_targets_affected_total[index],
            average_damage_per_target_per_round=(
                profile_individual_damage_total[index]
                / profile_targets_affected_total[index]
                if profile_targets_affected_total[index]
                else 0
            ),
            automatic_damage_applications=profile_automatic_damage_applications[index],
            total_skipped_profile_uses=profile_skipped_attacks[index],
            average_skipped_profile_uses_per_simulation=(
                profile_skipped_attacks[index] / simulations
            ),
            configured_profile_uses=profile_configured_uses[index],
            triggered_profile_uses=profile_triggered_uses[index],
            average_triggered_profile_uses_per_simulation=(
                profile_triggered_uses[index] / simulations
            ),
            average_executions_per_combat=profile_attacks[index] / simulations,
            average_executions_per_round=(
                profile_attacks[index] / total_rounds if total_rounds else 0
            ),
            average_automatic_damage_per_application=(
                profile_damage_totals[index]
                / profile_automatic_damage_applications[index]
                if profile_automatic_damage_applications[index]
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
            average_targets_affected=(
                round_targets_affected_totals[round_number] / simulations
            ),
            average_individual_damage=(
                round_individual_damage_totals[round_number]
                / round_targets_affected_totals[round_number]
                if round_targets_affected_totals[round_number]
                else 0
            ),
            hit_rate=(
                (round_hits[round_number] / round_attack_roll_resolutions[round_number])
                if round_attack_roll_resolutions[round_number]
                else 0
            ),
            critical_hit_rate=(
                round_critical_hits[round_number]
                / round_attack_roll_resolutions[round_number]
                if round_attack_roll_resolutions[round_number]
                else 0
            ),
            failed_save_rate=(
                round_failed_saves[round_number]
                / round_saving_throw_resolutions[round_number]
                if round_saving_throw_resolutions[round_number]
                else 0
            ),
            successful_save_rate=(
                round_successful_saves[round_number]
                / round_saving_throw_resolutions[round_number]
                if round_saving_throw_resolutions[round_number]
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
        hit_rate=(
            total_hits / total_attack_roll_resolutions
            if total_attack_roll_resolutions
            else 0
        ),
        critical_hit_rate=(
            total_critical_hits / total_attack_roll_resolutions
            if total_attack_roll_resolutions
            else 0
        ),
        minimum_total_damage_in_simulation=minimum_total_damage or 0,
        maximum_total_damage_in_simulation=maximum_total_damage or 0,
        failed_save_rate=(
            total_failed_saves / total_saving_throw_resolutions
            if total_saving_throw_resolutions
            else 0
        ),
        successful_save_rate=(
            total_successful_saves / total_saving_throw_resolutions
            if total_saving_throw_resolutions
            else 0
        ),
        total_target_resolutions=total_target_resolutions,
        total_targets_affected=sum(profile_targets_affected_total.values()),
        average_damage_per_target_per_round=(
            total_damage_all_simulations / sum(profile_targets_affected_total.values())
            if sum(profile_targets_affected_total.values())
            else 0
        ),
        automatic_damage_applications=total_automatic_damage_applications,
        average_automatic_damage_per_application=(
            total_damage_all_simulations / total_automatic_damage_applications
            if total_automatic_damage_applications
            else 0
        ),
        first_round_burst_damage=first_round_burst,
        average_damage_after_round_1=average_after_round_1,
        highest_damage_round=highest.round_number,
        highest_round_average_damage=highest.average_damage,
        average_total_damage=total_damage_all_simulations / simulations,
        attack_profile_results=profile_results,
        round_results=round_results,
        total_skipped_profile_uses=total_skipped_attacks,
        average_skipped_profile_uses_per_simulation=total_skipped_attacks / simulations,
    )


def simulate_build(
    build: BuildConfig,
    scenario: ScenarioConfig,
    seed: int,
) -> SimulationResult:
    """Validate and simulate one build in one scenario with a deterministic seed."""
    _validate_scenario(scenario)
    _validate_build(build, label=build.name.strip() or "Build")
    return run_damage_simulations(
        attack_bonus=build.attack_bonus,
        target_armor_class=scenario.target_armor_class,
        enemy_save_bonus=scenario.enemy_save_bonus,
        damage_dice=build.damage_dice.strip(),
        rounds=scenario.rounds,
        simulations=scenario.simulations,
        attacks_per_round=build.attacks_per_round,
        attack_roll_mode=build.attack_roll_mode,
        attack_profiles=build.resolved_attack_profiles(),
        rng=Random(seed),
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
    first_result = simulate_build(first_build, scenario, seed)
    second_result = simulate_build(second_build, scenario, seed)

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
            average_damage_per_target_per_round=(
                first_result.average_damage_per_target_per_round
                - second_result.average_damage_per_target_per_round
            ),
        ),
        higher_average_damage_build_name=higher_name,
    )
