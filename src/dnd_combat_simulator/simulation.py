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
    resolve_compiled_saving_throw_damage,
    resolve_compiled_weapon_attack,
    validate_feature_resolution_combination,
)
from dnd_combat_simulator.dice import (
    DamageExpression,
    RandomNumberGenerator,
    parse_damage_expression,
    roll_compiled_damage_expression,
)


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
class ManagedResource:
    """A named scenario resource available to each simulated combat."""

    resource_id: str
    name: str
    starting_value: int


@dataclass(frozen=True)
class ResourceCost:
    """Cost paid by an attack profile when it actually executes."""

    resource_id: str
    amount: int


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
    resource_costs: tuple[ResourceCost, ...] = field(default_factory=tuple)


@dataclass(frozen=True, init=False)
class RoundResult:
    """Summary statistics for one simulated round number.

    ``average_damage_per_target_resolution`` is the canonical expected damage
    per target resolution. ``average_individual_damage`` is a read-only
    compatibility alias for the same value.
    """

    round_number: int
    average_damage: float
    average_attacks: float
    hit_rate: float
    critical_hit_rate: float
    average_targets_affected: float = field(default=0, compare=False)
    average_damage_per_target_resolution: float = field(default=0, compare=False)
    failed_save_rate: float = 0
    successful_save_rate: float = 0

    def __init__(
        self,
        round_number: int,
        average_damage: float,
        average_attacks: float,
        hit_rate: float,
        critical_hit_rate: float,
        average_targets_affected: float = 0,
        average_damage_per_target_resolution: float = 0,
        average_individual_damage: float | None = None,
        failed_save_rate: float = 0,
        successful_save_rate: float = 0,
    ) -> None:
        if average_individual_damage is not None:
            if (
                average_damage_per_target_resolution != 0
                and average_damage_per_target_resolution != average_individual_damage
            ):
                msg = (
                    "average_individual_damage is an alias for "
                    "average_damage_per_target_resolution and cannot conflict."
                )
                raise ValueError(msg)
            average_damage_per_target_resolution = average_individual_damage
        object.__setattr__(self, "round_number", round_number)
        object.__setattr__(self, "average_damage", average_damage)
        object.__setattr__(self, "average_attacks", average_attacks)
        object.__setattr__(self, "hit_rate", hit_rate)
        object.__setattr__(self, "critical_hit_rate", critical_hit_rate)
        object.__setattr__(self, "average_targets_affected", average_targets_affected)
        object.__setattr__(
            self,
            "average_damage_per_target_resolution",
            average_damage_per_target_resolution,
        )
        object.__setattr__(self, "failed_save_rate", failed_save_rate)
        object.__setattr__(self, "successful_save_rate", successful_save_rate)

    @property
    def average_individual_damage(self) -> float:
        return self.average_damage_per_target_resolution


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
class ResourceUsageResult:
    """Aggregated per-combat usage for one managed resource."""

    resource: ManagedResource
    average_consumed_per_combat: float
    average_remaining_per_combat: float
    exhausted_combat_rate: float
    average_skipped_executions_per_combat: float


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
    resource_usage_results: tuple[ResourceUsageResult, ...] = field(
        default_factory=tuple, compare=False
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
    managed_resources: tuple[ManagedResource, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ComparisonDifference:
    """Nonnegative comparison deltas using the higher-DPR build as baseline."""

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


@dataclass(frozen=True)
class CompiledResourceCost:
    resource_index: int
    amount: int


@dataclass(frozen=True)
class ProfileExecutionPlan:
    profile: AttackProfile
    profile_index: int
    resolution_type: ResolutionType
    attack_roll_mode: AttackRollMode
    successful_save_damage: SuccessfulSaveDamage
    active_rounds: frozenset[int] | None
    compiled_damage_expression: DamageExpression
    damage_features: frozenset[str]
    attack_features: frozenset[AttackFeature]
    trigger_type: TriggerType
    trigger_frequency: TriggerFrequency
    trigger_source_index: int | None
    trigger_chance_percent: int | None
    resource_costs: tuple[CompiledResourceCost, ...]
    stop_on_miss: bool


@dataclass
class ProfileAccumulator:
    damage_total: int = 0
    attacks: int = 0
    skipped_attacks: int = 0
    configured_uses: int = 0
    triggered_uses: int = 0
    target_resolutions: int = 0
    attack_roll_resolutions: int = 0
    saving_throw_resolutions: int = 0
    automatic_damage_applications: int = 0
    automatic_damage_total: int = 0
    hits: int = 0
    critical_hits: int = 0
    failed_saves: int = 0
    successful_saves: int = 0
    damaging_resolutions: int = 0


@dataclass
class RoundAccumulator:
    damage_total: int = 0
    attacks: int = 0
    damaging_resolutions: int = 0
    target_resolutions: int = 0
    attack_roll_resolutions: int = 0
    saving_throw_resolutions: int = 0
    hits: int = 0
    critical_hits: int = 0
    failed_saves: int = 0
    successful_saves: int = 0


@dataclass
class OverallAccumulator:
    attacks: int = 0
    skipped_attacks: int = 0
    target_resolutions: int = 0
    attack_roll_resolutions: int = 0
    saving_throw_resolutions: int = 0
    automatic_damage_applications: int = 0
    automatic_damage: int = 0
    damage_all_simulations: int = 0
    hits: int = 0
    critical_hits: int = 0
    failed_saves: int = 0
    successful_saves: int = 0


@dataclass
class CombatTriggerState:
    successful_resolutions_by_profile: list[int]
    failed_resolutions_by_profile: list[int]
    critical_resolutions_by_profile: list[int]
    triggered_once_by_profile: list[bool]


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


def _validate_managed_resources(resources: tuple[ManagedResource, ...]) -> None:
    names: list[str] = []
    ids: list[str] = []
    for index, resource in enumerate(resources, start=1):
        if not resource.resource_id.strip():
            raise ValueError(f"Managed resource {index} ID is required.")
        if not resource.name.strip():
            raise ValueError(f"Managed resource {index} name is required.")
        if not isinstance(resource.starting_value, int) or resource.starting_value < 0:
            raise ValueError(
                f"Managed resource {resource.name or index} starting value must be "
                "a whole number greater than or equal to 0."
            )
        ids.append(resource.resource_id)
        names.append(resource.name.strip().casefold())
    if len(set(ids)) != len(ids):
        raise ValueError("Managed resource IDs must be unique.")
    if len(set(names)) != len(names):
        raise ValueError("Managed resource names must be unique.")


def _validate_resource_costs(
    profiles: tuple[AttackProfile, ...],
    resources: tuple[ManagedResource, ...],
    *,
    label: str,
) -> None:
    resource_ids = {resource.resource_id for resource in resources}
    for profile_index, profile in enumerate(profiles, start=1):
        for cost in profile.resource_costs:
            if not cost.resource_id:
                raise ValueError(
                    f"{label} profile {profile_index} resource selection is required."
                )
            if cost.resource_id not in resource_ids:
                raise ValueError(
                    f"{label} profile {profile_index} references a missing resource."
                )
            if not isinstance(cost.amount, int) or cost.amount < 1:
                raise ValueError(
                    f"{label} profile {profile_index} resource cost must be a "
                    "whole number greater than 0."
                )


def _build_execution_plan(
    profiles: tuple[AttackProfile, ...], resources: tuple[ManagedResource, ...]
) -> tuple[ProfileExecutionPlan, ...]:
    profile_indexes = {
        _profile_id(profile): index for index, profile in enumerate(profiles)
    }
    resource_indexes = {
        resource.resource_id: index for index, resource in enumerate(resources)
    }
    plans: list[ProfileExecutionPlan] = []
    for index, profile in enumerate(profiles):
        resolution_type = ResolutionType(profile.resolution_type)
        attack_features = frozenset(
            AttackFeature(feature) for feature in profile.features
        )
        trigger_type = TriggerType(profile.trigger_type)
        source_id = profile.trigger_source_attack_id
        source_index = (
            None
            if trigger_type in (TriggerType.ALWAYS, TriggerType.SOMETIMES)
            else profile_indexes[str(source_id)]
        )
        plans.append(
            ProfileExecutionPlan(
                profile=profile,
                profile_index=index,
                resolution_type=resolution_type,
                attack_roll_mode=AttackRollMode(profile.attack_roll_mode),
                successful_save_damage=SuccessfulSaveDamage(
                    profile.successful_save_damage
                ),
                active_rounds=parse_active_rounds(profile.active_rounds),
                compiled_damage_expression=parse_damage_expression(
                    profile.damage_dice.strip()
                ),
                damage_features=frozenset(feature.value for feature in attack_features),
                attack_features=attack_features,
                trigger_type=trigger_type,
                trigger_frequency=_normalized_trigger_frequency(
                    profile.trigger_frequency
                ),
                trigger_source_index=source_index,
                trigger_chance_percent=profile.trigger_chance_percent,
                resource_costs=tuple(
                    CompiledResourceCost(
                        resource_index=resource_indexes[cost.resource_id],
                        amount=cost.amount,
                    )
                    for cost in profile.resource_costs
                ),
                stop_on_miss=AttackFeature.STOP_ON_MISS in attack_features,
            )
        )
    return tuple(plans)


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


def _validate_build(
    build: BuildConfig, *, label: str, resources: tuple[ManagedResource, ...] = ()
) -> None:
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
    _validate_resource_costs(profiles, resources, label=label)


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
    _validate_managed_resources(scenario.managed_resources)


def _determine_profile_execution_count(
    *,
    plan: ProfileExecutionPlan,
    trigger_state: CombatTriggerState,
    rng: RandomNumberGenerator,
) -> tuple[int, int]:
    if plan.trigger_type is TriggerType.SOMETIMES:
        return (
            int(rng.randint(1, 100) <= (plan.trigger_chance_percent or 0)),
            0,
        )
    if plan.trigger_type is TriggerType.ALWAYS:
        return plan.profile.attacks_per_round, plan.profile.attacks_per_round

    source_index = plan.trigger_source_index
    assert source_index is not None
    if plan.trigger_type is TriggerType.AFTER_SUCCESS:
        qualifying_resolutions = trigger_state.successful_resolutions_by_profile[
            source_index
        ]
    elif plan.trigger_type is TriggerType.AFTER_FAILURE:
        qualifying_resolutions = trigger_state.failed_resolutions_by_profile[
            source_index
        ]
    else:
        qualifying_resolutions = trigger_state.critical_resolutions_by_profile[
            source_index
        ]

    if plan.trigger_frequency is TriggerFrequency.PER_SUCCESS:
        return qualifying_resolutions, 0
    if plan.trigger_frequency is TriggerFrequency.ONCE_PER_ROUND:
        return int(qualifying_resolutions > 0), 0

    already_triggered = trigger_state.triggered_once_by_profile[plan.profile_index]
    execution_count = int(qualifying_resolutions > 0 and not already_triggered)
    if execution_count:
        trigger_state.triggered_once_by_profile[plan.profile_index] = True
    return execution_count, 0


def _record_target_resolution(
    *,
    overall: OverallAccumulator,
    profile_stat: ProfileAccumulator,
    round_stat: RoundAccumulator,
    damage: int,
) -> None:
    overall.target_resolutions += 1
    profile_stat.target_resolutions += 1
    round_stat.target_resolutions += 1
    if damage > 0:
        profile_stat.damaging_resolutions += 1
        round_stat.damaging_resolutions += 1


def _has_available_resources(
    costs: tuple[CompiledResourceCost, ...], remaining_resources: list[int]
) -> int | None:
    return next(
        (
            cost.resource_index
            for cost in costs
            if remaining_resources[cost.resource_index] < cost.amount
        ),
        None,
    )


def _consume_resources(
    costs: tuple[CompiledResourceCost, ...],
    remaining_resources: list[int],
    resource_consumed_totals: list[int],
) -> None:
    for cost in costs:
        remaining_resources[cost.resource_index] -= cost.amount
        resource_consumed_totals[cost.resource_index] += cost.amount


def _resolve_attack_roll_profile_execution(
    *,
    plan: ProfileExecutionPlan,
    target_armor_class: int,
    rng: RandomNumberGenerator,
) -> tuple[int, bool, bool]:
    attack = resolve_compiled_weapon_attack(
        attack_bonus=plan.profile.attack_bonus or 0,
        target_armor_class=target_armor_class,
        damage_expression=plan.compiled_damage_expression,
        attack_roll_mode=plan.attack_roll_mode,
        rng=rng,
        features=plan.attack_features,
        damage_features=plan.damage_features,
    )
    return attack.damage_dealt, attack.hit, attack.critical_hit


def _resolve_saving_throw_profile_execution(
    *,
    plan: ProfileExecutionPlan,
    enemy_save_bonus: int,
    rng: RandomNumberGenerator,
) -> tuple[int, bool, bool]:
    save = resolve_compiled_saving_throw_damage(
        save_dc=plan.profile.save_dc or 0,
        enemy_save_bonus=enemy_save_bonus,
        damage_expression=plan.compiled_damage_expression,
        successful_save_damage=plan.successful_save_damage,
        rng=rng,
        features=plan.attack_features,
        damage_features=plan.damage_features,
    )
    return save.damage_dealt, save.failed_save, save.successful_save


def _resolve_automatic_damage_profile_execution(
    *, plan: ProfileExecutionPlan, rng: RandomNumberGenerator
) -> int:
    return roll_compiled_damage_expression(
        plan.compiled_damage_expression, rng=rng, features=plan.damage_features
    )


def _finalize_profile_results(
    *,
    profiles: tuple[AttackProfile, ...],
    profile_stats: list[ProfileAccumulator],
    simulations: int,
    total_rounds: int,
) -> tuple[AttackProfileResult, ...]:
    return tuple(
        AttackProfileResult(
            attack_profile=profile,
            total_attacks_made=stat.attacks,
            average_total_damage_per_simulation=stat.damage_total / simulations,
            average_damage_per_round=stat.damage_total / total_rounds,
            average_damage_per_use=(
                stat.damage_total / stat.attacks if stat.attacks else 0
            ),
            total_profile_uses=stat.attacks,
            hit_rate=(stat.hits / stat.attack_roll_resolutions)
            if stat.attack_roll_resolutions
            else 0,
            critical_hit_rate=(stat.critical_hits / stat.attack_roll_resolutions)
            if stat.attack_roll_resolutions
            else 0,
            failed_save_rate=(stat.failed_saves / stat.saving_throw_resolutions)
            if stat.saving_throw_resolutions
            else 0,
            successful_save_rate=(stat.successful_saves / stat.saving_throw_resolutions)
            if stat.saving_throw_resolutions
            else 0,
            total_target_resolutions=stat.target_resolutions,
            total_targets_affected=stat.damaging_resolutions,
            average_damage_per_target_per_round=(
                stat.damage_total / stat.target_resolutions
                if stat.target_resolutions
                else 0
            ),
            automatic_damage_applications=stat.automatic_damage_applications,
            total_skipped_profile_uses=stat.skipped_attacks,
            average_skipped_profile_uses_per_simulation=(
                stat.skipped_attacks / simulations
            ),
            configured_profile_uses=stat.configured_uses,
            triggered_profile_uses=stat.triggered_uses,
            average_triggered_profile_uses_per_simulation=(
                stat.triggered_uses / simulations
            ),
            average_executions_per_combat=stat.attacks / simulations,
            average_executions_per_round=stat.attacks / total_rounds
            if total_rounds
            else 0,
            average_automatic_damage_per_application=(
                stat.automatic_damage_total / stat.automatic_damage_applications
                if stat.automatic_damage_applications
                else 0
            ),
        )
        for profile, stat in zip(profiles, profile_stats, strict=True)
    )


def _finalize_round_results(
    *, round_stats: list[RoundAccumulator], simulations: int
) -> tuple[RoundResult, ...]:
    return tuple(
        RoundResult(
            round_number=round_number,
            average_damage=stat.damage_total / simulations,
            average_attacks=stat.attacks / simulations,
            average_targets_affected=stat.damaging_resolutions / simulations,
            average_damage_per_target_resolution=(
                stat.damage_total / stat.target_resolutions
                if stat.target_resolutions
                else 0
            ),
            hit_rate=(stat.hits / stat.attack_roll_resolutions)
            if stat.attack_roll_resolutions
            else 0,
            critical_hit_rate=(stat.critical_hits / stat.attack_roll_resolutions)
            if stat.attack_roll_resolutions
            else 0,
            failed_save_rate=(stat.failed_saves / stat.saving_throw_resolutions)
            if stat.saving_throw_resolutions
            else 0,
            successful_save_rate=(stat.successful_saves / stat.saving_throw_resolutions)
            if stat.saving_throw_resolutions
            else 0,
        )
        for round_number, stat in enumerate(round_stats, start=1)
    )


def _finalize_resource_results(
    *,
    managed_resources: tuple[ManagedResource, ...],
    used_resource_indexes: set[int],
    resource_consumed_totals: list[int],
    resource_remaining_totals: list[int],
    resource_ended_at_zero_combats: list[int],
    resource_skipped_totals: list[int],
    simulations: int,
) -> tuple[ResourceUsageResult, ...]:
    return tuple(
        ResourceUsageResult(
            resource=resource,
            average_consumed_per_combat=resource_consumed_totals[index] / simulations,
            average_remaining_per_combat=resource_remaining_totals[index] / simulations,
            exhausted_combat_rate=resource_ended_at_zero_combats[index] / simulations,
            average_skipped_executions_per_combat=resource_skipped_totals[index]
            / simulations,
        )
        for index, resource in enumerate(managed_resources)
        if index in used_resource_indexes
    )


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
    managed_resources: tuple[ManagedResource, ...] = (),
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
    _validate_managed_resources(managed_resources)
    _validate_resource_costs(profiles, managed_resources, label="Attack profiles")
    execution_plan = _build_execution_plan(profiles, managed_resources)

    random_number_generator = rng if rng is not None else Random()
    total_rounds = rounds * simulations
    overall = OverallAccumulator()
    profile_stats = [ProfileAccumulator() for _ in profiles]
    round_stats = [RoundAccumulator() for _ in range(rounds)]
    minimum_total_damage: int | None = None
    maximum_total_damage: int | None = None
    used_resource_indexes = {
        cost.resource_index for plan in execution_plan for cost in plan.resource_costs
    }
    resource_consumed_totals = [0 for _ in managed_resources]
    resource_remaining_totals = [0 for _ in managed_resources]
    resource_ended_at_zero_combats = [0 for _ in managed_resources]
    resource_skipped_totals = [0 for _ in managed_resources]

    for _ in range(simulations):
        simulation_damage = 0
        remaining_resources = [
            resource.starting_value for resource in managed_resources
        ]
        combat_trigger_state = CombatTriggerState(
            successful_resolutions_by_profile=[0 for _ in profiles],
            failed_resolutions_by_profile=[0 for _ in profiles],
            critical_resolutions_by_profile=[0 for _ in profiles],
            triggered_once_by_profile=[False for _ in profiles],
        )
        for round_number in range(1, rounds + 1):
            for profile_index in range(len(profiles)):
                combat_trigger_state.successful_resolutions_by_profile[
                    profile_index
                ] = 0
                combat_trigger_state.failed_resolutions_by_profile[profile_index] = 0
                combat_trigger_state.critical_resolutions_by_profile[profile_index] = 0
            for plan in execution_plan:
                profile_index = plan.profile_index
                profile = plan.profile
                active_round_set = plan.active_rounds
                if (
                    active_round_set is not None
                    and round_number not in active_round_set
                ):
                    continue
                execution_count, configured_uses = _determine_profile_execution_count(
                    plan=plan,
                    trigger_state=combat_trigger_state,
                    rng=random_number_generator,
                )
                trigger_type = plan.trigger_type
                profile_stats[profile_index].configured_uses += configured_uses
                if trigger_type is not TriggerType.ALWAYS:
                    profile_stats[profile_index].triggered_uses += execution_count
                stop_profile_after_miss = False
                for attack_index in range(execution_count):
                    if stop_profile_after_miss:
                        skipped = execution_count - attack_index
                        overall.skipped_attacks += skipped
                        profile_stats[profile_index].skipped_attacks += skipped
                        break
                    unavailable_resource_index = _has_available_resources(
                        plan.resource_costs, remaining_resources
                    )
                    if unavailable_resource_index is not None:
                        overall.skipped_attacks += 1
                        profile_stats[profile_index].skipped_attacks += 1
                        resource_skipped_totals[unavailable_resource_index] += 1
                        continue
                    _consume_resources(
                        plan.resource_costs,
                        remaining_resources,
                        resource_consumed_totals,
                    )
                    overall.attacks += 1
                    round_stats[round_number - 1].attacks += 1
                    profile_stats[profile_index].attacks += 1
                    if plan.resolution_type is ResolutionType.ATTACK_ROLL:
                        for _target_index in range(profile.affected_targets):
                            damage, hit, critical_hit = (
                                _resolve_attack_roll_profile_execution(
                                    plan=plan,
                                    target_armor_class=target_armor_class,
                                    rng=random_number_generator,
                                )
                            )
                            simulation_damage += damage
                            round_stats[round_number - 1].damage_total += damage
                            profile_stats[profile_index].damage_total += damage
                            _record_target_resolution(
                                overall=overall,
                                profile_stat=profile_stats[profile_index],
                                round_stat=round_stats[round_number - 1],
                                damage=damage,
                            )
                            overall.attack_roll_resolutions += 1
                            profile_stats[profile_index].attack_roll_resolutions += 1
                            round_stats[round_number - 1].attack_roll_resolutions += 1
                            overall.hits += int(hit)
                            round_stats[round_number - 1].hits += int(hit)
                            profile_stats[profile_index].hits += int(hit)
                            combat_trigger_state.successful_resolutions_by_profile[
                                profile_index
                            ] += int(hit)
                            combat_trigger_state.failed_resolutions_by_profile[
                                profile_index
                            ] += int(not hit)
                            combat_trigger_state.critical_resolutions_by_profile[
                                profile_index
                            ] += int(critical_hit)
                            overall.critical_hits += int(critical_hit)
                            round_stats[round_number - 1].critical_hits += int(
                                critical_hit
                            )
                            profile_stats[profile_index].critical_hits += int(
                                critical_hit
                            )
                            if plan.stop_on_miss and not hit:
                                stop_profile_after_miss = True
                    elif plan.resolution_type is ResolutionType.SAVING_THROW:
                        if profile.affected_targets == 1:
                            damage, failed_save, successful_save = (
                                _resolve_saving_throw_profile_execution(
                                    plan=plan,
                                    enemy_save_bonus=enemy_save_bonus,
                                    rng=random_number_generator,
                                )
                            )
                            simulation_damage += damage
                            round_stats[round_number - 1].damage_total += damage
                            profile_stats[profile_index].damage_total += damage
                            _record_target_resolution(
                                overall=overall,
                                profile_stat=profile_stats[profile_index],
                                round_stat=round_stats[round_number - 1],
                                damage=damage,
                            )
                            overall.saving_throw_resolutions += 1
                            profile_stats[profile_index].saving_throw_resolutions += 1
                            round_stats[round_number - 1].saving_throw_resolutions += 1
                            overall.failed_saves += int(failed_save)
                            round_stats[round_number - 1].failed_saves += int(
                                failed_save
                            )
                            profile_stats[profile_index].failed_saves += int(
                                failed_save
                            )
                            combat_trigger_state.successful_resolutions_by_profile[
                                profile_index
                            ] += int(failed_save)
                            combat_trigger_state.failed_resolutions_by_profile[
                                profile_index
                            ] += int(successful_save)
                            overall.successful_saves += int(successful_save)
                            round_stats[round_number - 1].successful_saves += int(
                                successful_save
                            )
                            profile_stats[profile_index].successful_saves += int(
                                successful_save
                            )
                            continue
                        shared_damage = roll_compiled_damage_expression(
                            plan.compiled_damage_expression,
                            rng=random_number_generator,
                            features=plan.damage_features,
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
                                plan.successful_save_damage
                                is SuccessfulSaveDamage.HALF_DAMAGE
                                or AttackFeature.POTENT_CANTRIP in plan.attack_features
                            ):
                                damage = shared_damage // 2
                            else:
                                damage = 0
                            simulation_damage += damage
                            round_stats[round_number - 1].damage_total += damage
                            profile_stats[profile_index].damage_total += damage
                            _record_target_resolution(
                                overall=overall,
                                profile_stat=profile_stats[profile_index],
                                round_stat=round_stats[round_number - 1],
                                damage=damage,
                            )
                            overall.saving_throw_resolutions += 1
                            profile_stats[profile_index].saving_throw_resolutions += 1
                            round_stats[round_number - 1].saving_throw_resolutions += 1
                            overall.failed_saves += int(failed_save)
                            round_stats[round_number - 1].failed_saves += int(
                                failed_save
                            )
                            profile_stats[profile_index].failed_saves += int(
                                failed_save
                            )
                            combat_trigger_state.successful_resolutions_by_profile[
                                profile_index
                            ] += int(failed_save)
                            combat_trigger_state.failed_resolutions_by_profile[
                                profile_index
                            ] += int(successful_save)
                            overall.successful_saves += int(successful_save)
                            round_stats[round_number - 1].successful_saves += int(
                                successful_save
                            )
                            profile_stats[profile_index].successful_saves += int(
                                successful_save
                            )

                    else:
                        for _target_index in range(profile.affected_targets):
                            damage = _resolve_automatic_damage_profile_execution(
                                plan=plan, rng=random_number_generator
                            )
                            simulation_damage += damage
                            round_stats[round_number - 1].damage_total += damage
                            profile_stats[profile_index].damage_total += damage
                            _record_target_resolution(
                                overall=overall,
                                profile_stat=profile_stats[profile_index],
                                round_stat=round_stats[round_number - 1],
                                damage=damage,
                            )
                            overall.automatic_damage_applications += 1
                            overall.automatic_damage += damage
                            profile_stats[
                                profile_index
                            ].automatic_damage_applications += 1
                            profile_stats[
                                profile_index
                            ].automatic_damage_total += damage
                            combat_trigger_state.successful_resolutions_by_profile[
                                profile_index
                            ] += 1

        for resource_index, remaining in enumerate(remaining_resources):
            resource_remaining_totals[resource_index] += remaining
            resource_ended_at_zero_combats[resource_index] += int(remaining == 0)
        overall.damage_all_simulations += simulation_damage
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

    profile_results = _finalize_profile_results(
        profiles=profiles,
        profile_stats=profile_stats,
        simulations=simulations,
        total_rounds=total_rounds,
    )
    round_results = _finalize_round_results(
        round_stats=round_stats, simulations=simulations
    )
    first_round_burst = round_results[0].average_damage
    average_after_round_1 = (
        sum(result.average_damage for result in round_results[1:]) / (rounds - 1)
        if rounds > 1
        else 0
    )
    highest = max(round_results, key=lambda result: result.average_damage)

    resource_usage_results = _finalize_resource_results(
        managed_resources=managed_resources,
        used_resource_indexes=used_resource_indexes,
        resource_consumed_totals=resource_consumed_totals,
        resource_remaining_totals=resource_remaining_totals,
        resource_ended_at_zero_combats=resource_ended_at_zero_combats,
        resource_skipped_totals=resource_skipped_totals,
        simulations=simulations,
    )

    return SimulationResult(
        simulations_run=simulations,
        rounds_per_simulation=rounds,
        attacks_per_round=int(
            round(sum(result.average_attacks for result in round_results) / rounds)
        ),
        attack_roll_mode=profiles[0].attack_roll_mode,
        total_attacks_made=overall.attacks,
        average_total_damage_per_simulation=overall.damage_all_simulations
        / simulations,
        average_damage_per_round=overall.damage_all_simulations / total_rounds,
        hit_rate=(
            overall.hits / overall.attack_roll_resolutions
            if overall.attack_roll_resolutions
            else 0
        ),
        critical_hit_rate=(
            overall.critical_hits / overall.attack_roll_resolutions
            if overall.attack_roll_resolutions
            else 0
        ),
        minimum_total_damage_in_simulation=minimum_total_damage or 0,
        maximum_total_damage_in_simulation=maximum_total_damage or 0,
        failed_save_rate=(
            overall.failed_saves / overall.saving_throw_resolutions
            if overall.saving_throw_resolutions
            else 0
        ),
        successful_save_rate=(
            overall.successful_saves / overall.saving_throw_resolutions
            if overall.saving_throw_resolutions
            else 0
        ),
        total_target_resolutions=overall.target_resolutions,
        total_targets_affected=sum(stat.damaging_resolutions for stat in profile_stats),
        average_damage_per_target_per_round=(
            overall.damage_all_simulations / overall.target_resolutions
            if overall.target_resolutions
            else 0
        ),
        automatic_damage_applications=overall.automatic_damage_applications,
        average_automatic_damage_per_application=(
            overall.automatic_damage / overall.automatic_damage_applications
            if overall.automatic_damage_applications
            else 0
        ),
        first_round_burst_damage=first_round_burst,
        average_damage_after_round_1=average_after_round_1,
        highest_damage_round=highest.round_number,
        highest_round_average_damage=highest.average_damage,
        average_total_damage=overall.damage_all_simulations / simulations,
        attack_profile_results=profile_results,
        round_results=round_results,
        total_skipped_profile_uses=overall.skipped_attacks,
        average_skipped_profile_uses_per_simulation=overall.skipped_attacks
        / simulations,
        configured_profile_uses=sum(stat.configured_uses for stat in profile_stats),
        triggered_profile_uses=sum(stat.triggered_uses for stat in profile_stats),
        average_triggered_profile_uses_per_simulation=sum(
            stat.triggered_uses for stat in profile_stats
        )
        / simulations,
        resource_usage_results=resource_usage_results,
    )


def simulate_build(
    build: BuildConfig,
    scenario: ScenarioConfig,
    seed: int,
) -> SimulationResult:
    """Validate and simulate one build in one scenario with a deterministic seed."""
    _validate_scenario(scenario)
    _validate_build(
        build, label=build.name.strip() or "Build", resources=scenario.managed_resources
    )
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
        managed_resources=scenario.managed_resources,
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

    first_higher_or_tied = (
        first_result.average_damage_per_round >= second_result.average_damage_per_round
    )
    if first_result.average_damage_per_round > second_result.average_damage_per_round:
        higher_name = first_build.name.strip()
    elif second_result.average_damage_per_round > first_result.average_damage_per_round:
        higher_name = second_build.name.strip()
    else:
        higher_name = None
    higher_result = first_result if first_higher_or_tied else second_result
    lower_result = second_result if first_higher_or_tied else first_result

    return BuildComparisonResult(
        first_build=first_build,
        second_build=second_build,
        scenario=scenario,
        first_result=first_result,
        second_result=second_result,
        difference=ComparisonDifference(
            average_damage_per_round=(
                higher_result.average_damage_per_round
                - lower_result.average_damage_per_round
            ),
            average_total_damage=(
                higher_result.average_total_damage_per_simulation
                - lower_result.average_total_damage_per_simulation
            ),
            hit_rate=abs(first_result.hit_rate - second_result.hit_rate),
            critical_hit_rate=abs(
                first_result.critical_hit_rate - second_result.critical_hit_rate
            ),
            average_damage_per_target_per_round=abs(
                first_result.average_damage_per_target_per_round
                - second_result.average_damage_per_target_per_round
            ),
        ),
        higher_average_damage_build_name=higher_name,
    )
