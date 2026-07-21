"""Repeated combat simulation logic independent from the Streamlit interface."""

from __future__ import annotations

from dataclasses import dataclass
from random import Random

from dnd_combat_simulator.combat import resolve_weapon_attack
from dnd_combat_simulator.dice import RandomNumberGenerator


@dataclass(frozen=True)
class SimulationResult:
    """Summary statistics for repeated weapon-attack simulations."""

    simulations_run: int
    rounds_per_simulation: int
    attacks_per_round: int
    total_attacks_made: int
    average_total_damage_per_simulation: float
    average_damage_per_round: float
    hit_rate: float
    critical_hit_rate: float
    minimum_total_damage_in_simulation: int
    maximum_total_damage_in_simulation: int


def run_damage_simulations(
    *,
    attack_bonus: int,
    target_armor_class: int,
    damage_dice: str,
    damage_modifier: int,
    rounds: int,
    simulations: int,
    attacks_per_round: int = 1,
    rng: RandomNumberGenerator | None = None,
) -> SimulationResult:
    """Run repeated damage simulations with configurable attacks per round.

    Args:
        attack_bonus: Flat modifier added to each natural d20 attack roll.
        target_armor_class: Armor Class each attack must meet or exceed to hit.
        damage_dice: Dice expression for weapon damage, such as ``"1d8"``.
        damage_modifier: Flat modifier added once to hit damage.
        rounds: Number of rounds in each simulation.
        simulations: Number of simulations to run.
        attacks_per_round: Number of separate attacks to resolve each round.
        rng: Optional random number generator for deterministic tests.

    Returns:
        Aggregate damage, hit, and critical-hit statistics.

    Raises:
        ValueError: If ``rounds``, ``simulations``, or ``attacks_per_round`` is
            less than 1, or if the supplied damage dice are rejected by
            weapon-attack resolution.
    """
    if rounds < 1:
        msg = "Number of rounds must be at least 1."
        raise ValueError(msg)
    if simulations < 1:
        msg = "Number of simulations must be at least 1."
        raise ValueError(msg)
    if attacks_per_round < 1:
        msg = "Attacks per round must be at least 1."
        raise ValueError(msg)

    random_number_generator = rng if rng is not None else Random()
    total_rounds = rounds * simulations
    total_attacks = total_rounds * attacks_per_round
    total_damage_all_simulations = 0
    total_hits = 0
    total_critical_hits = 0
    minimum_total_damage: int | None = None
    maximum_total_damage: int | None = None

    for _ in range(simulations):
        simulation_damage = 0
        for _ in range(rounds):
            for _ in range(attacks_per_round):
                attack = resolve_weapon_attack(
                    attack_bonus=attack_bonus,
                    target_armor_class=target_armor_class,
                    damage_dice=damage_dice,
                    damage_modifier=damage_modifier,
                    rng=random_number_generator,
                )
                simulation_damage += attack.damage_dealt
                total_hits += int(attack.hit)
                total_critical_hits += int(attack.critical_hit)

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

    return SimulationResult(
        simulations_run=simulations,
        rounds_per_simulation=rounds,
        attacks_per_round=attacks_per_round,
        total_attacks_made=total_attacks,
        average_total_damage_per_simulation=total_damage_all_simulations / simulations,
        average_damage_per_round=total_damage_all_simulations / total_rounds,
        hit_rate=total_hits / total_attacks,
        critical_hit_rate=total_critical_hits / total_attacks,
        minimum_total_damage_in_simulation=minimum_total_damage or 0,
        maximum_total_damage_in_simulation=maximum_total_damage or 0,
    )
