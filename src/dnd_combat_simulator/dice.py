"""Dice notation parsing and rolling utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from random import Random
from typing import Protocol


class RandomNumberGenerator(Protocol):
    """Protocol for injectable random number generators."""

    def randint(self, a: int, b: int) -> int:
        """Return a random integer N such that a <= N <= b."""


MAX_EXPLOSION_CHAIN_ROLLS = 1_000
MAX_REROLL_ATTEMPTS = 1_000


class ExplosionMode(StrEnum):
    """Supported exploding-dice trigger modes."""

    MAXIMUM = "maximum"
    EXACT = "exact"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"


class PoolSelectionMode(StrEnum):
    """Supported keep/drop operations for dice pools."""

    KEEP_HIGHEST = "keep_highest"
    KEEP_LOWEST = "keep_lowest"
    DROP_HIGHEST = "drop_highest"
    DROP_LOWEST = "drop_lowest"


class RerollMode(StrEnum):
    """Supported reroll condition modes."""

    EXACT = "exact"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"


@dataclass(frozen=True)
class RerollCondition:
    """One reroll condition for a die face."""

    mode: RerollMode
    threshold: int


@dataclass(frozen=True)
class DiceNotation:
    """Parsed representation of a damage dice formula."""

    count: int
    sides: int
    modifier: int = 0
    explosion_mode: ExplosionMode | None = None
    explosion_threshold: int | None = None
    selection_mode: PoolSelectionMode | None = None
    selection_count: int | None = None
    reroll_conditions: tuple[RerollCondition, ...] = field(default_factory=tuple)


_BASE_PATTERN = re.compile(r"(?P<count>[1-9]\d*)d(?P<sides>[1-9]\d*)")
_INT_PATTERN = re.compile(r"\d+")
_MODIFIER_PATTERN = re.compile(r"[+-]\d+$")
_SELECTION_PATTERN = re.compile(r"(kh|kl|dh|dl|k|d)(\d+)")
_REROLL_PATTERN = re.compile(r"r(?P<op>[<>]?)(?P<threshold>\d+)")
_EXPLOSION_PATTERN = re.compile(r"!(?:(?P<op>[<>]?)(?P<threshold>\d+))?")


def parse_dice_notation(notation: str) -> DiceNotation:
    """Parse a damage dice formula into immutable dice metadata."""
    text = notation.strip()
    base = _BASE_PATTERN.match(text)
    if base is None:
        msg = f"Invalid dice notation {notation!r}. Expected a formula such as '1d8+4'."
        raise ValueError(msg)
    count = int(base.group("count"))
    sides = int(base.group("sides"))
    if count < 1:
        raise ValueError(
            "Invalid dice notation: dice count must be a positive integer."
        )
    if sides < 1:
        raise ValueError("Invalid dice notation: die size must be a positive integer.")

    rest = text[base.end() :]
    modifier = 0
    modifier_match = _MODIFIER_PATTERN.search(rest)
    if modifier_match is not None:
        modifier = int(modifier_match.group(0))
        rest = rest[: modifier_match.start()]
    elif "+" in rest or "-" in rest:
        raise ValueError(
            "Invalid dice notation: malformed damage modifier. "
            "Use '+N' or '-N' at the end."
        )

    rerolls: list[RerollCondition] = []
    while rest.startswith("r"):
        match = _REROLL_PATTERN.match(rest)
        if match is None:
            raise ValueError("Malformed reroll clause. Use rN, r<N, or r>N.")
        op = match.group("op")
        threshold = int(match.group("threshold"))
        mode = (
            RerollMode.LESS_THAN_OR_EQUAL
            if op == "<"
            else RerollMode.GREATER_THAN_OR_EQUAL
            if op == ">"
            else RerollMode.EXACT
        )
        rerolls.append(RerollCondition(mode, threshold))
        rest = rest[match.end() :]

    explosion_mode: ExplosionMode | None = None
    explosion_threshold: int | None = None
    if rest.startswith("!"):
        match = _EXPLOSION_PATTERN.match(rest)
        if match is None:
            raise ValueError("Malformed explosion clause. Use !, !N, !>N, or !<N.")
        op = match.group("op")
        threshold_text = match.group("threshold")
        if threshold_text is None:
            explosion_mode = ExplosionMode.MAXIMUM
            explosion_threshold = sides
        else:
            explosion_threshold = int(threshold_text)
            explosion_mode = (
                ExplosionMode.LESS_THAN_OR_EQUAL
                if op == "<"
                else ExplosionMode.GREATER_THAN_OR_EQUAL
                if op == ">"
                else ExplosionMode.EXACT
            )
        rest = rest[match.end() :]

    selection_mode: PoolSelectionMode | None = None
    selection_count: int | None = None
    if rest:
        match = _SELECTION_PATTERN.match(rest)
        if match is not None:
            op, count_text = match.groups()
            selection_count = int(count_text)
            selection_mode = {
                "k": PoolSelectionMode.KEEP_HIGHEST,
                "kh": PoolSelectionMode.KEEP_HIGHEST,
                "kl": PoolSelectionMode.KEEP_LOWEST,
                "d": PoolSelectionMode.DROP_LOWEST,
                "dl": PoolSelectionMode.DROP_LOWEST,
                "dh": PoolSelectionMode.DROP_HIGHEST,
            }[op]
            rest = rest[match.end() :]
    if rest:
        raise ValueError(
            "Invalid dice notation: unsupported trailing text "
            f"in dice notation: {rest!r}."
        )

    dice = DiceNotation(
        count=count,
        sides=sides,
        modifier=modifier,
        explosion_mode=explosion_mode,
        explosion_threshold=explosion_threshold,
        selection_mode=selection_mode,
        selection_count=selection_count,
        reroll_conditions=tuple(rerolls),
    )
    _validate_dice(dice)
    return dice


def _validate_dice(dice: DiceNotation) -> None:
    if dice.selection_count is not None:
        if dice.selection_count < 1:
            raise ValueError("Keep/drop count must be a positive integer.")
        if dice.selection_count > dice.count:
            raise ValueError(
                "Keep/drop count cannot exceed the number of initial dice."
            )
    for condition in dice.reroll_conditions:
        if not 1 <= condition.threshold <= dice.sides:
            raise ValueError(
                "Reroll values and thresholds must be within the die face range."
            )
    if dice.reroll_conditions and all(
        _matches_reroll(face, dice.reroll_conditions)
        for face in range(1, dice.sides + 1)
    ):
        raise ValueError("Reroll conditions cannot match every possible die face.")
    if dice.explosion_mode is not None:
        assert dice.explosion_threshold is not None
        if dice.sides == 1:
            raise ValueError("Exploding d1 expressions are not supported.")
        if not 1 <= dice.explosion_threshold <= dice.sides:
            raise ValueError("Explosion threshold must be within the die face range.")
        if all(_matches_explosion(face, dice) for face in range(1, dice.sides + 1)):
            raise ValueError(
                "Explosion rule cannot trigger on every possible die face."
            )


def _matches_reroll(face: int, conditions: tuple[RerollCondition, ...]) -> bool:
    return any(
        (condition.mode is RerollMode.EXACT and face == condition.threshold)
        or (
            condition.mode is RerollMode.GREATER_THAN_OR_EQUAL
            and face >= condition.threshold
        )
        or (
            condition.mode is RerollMode.LESS_THAN_OR_EQUAL
            and face <= condition.threshold
        )
        for condition in conditions
    )


def _matches_explosion(face: int, dice: DiceNotation) -> bool:
    if dice.explosion_mode is None:
        return False
    threshold = dice.explosion_threshold or dice.sides
    return (
        (dice.explosion_mode is ExplosionMode.MAXIMUM and face == dice.sides)
        or (dice.explosion_mode is ExplosionMode.EXACT and face == threshold)
        or (
            dice.explosion_mode is ExplosionMode.GREATER_THAN_OR_EQUAL
            and face >= threshold
        )
        or (
            dice.explosion_mode is ExplosionMode.LESS_THAN_OR_EQUAL
            and face <= threshold
        )
    )


def _roll_accepted_face(dice: DiceNotation, rng: RandomNumberGenerator) -> int:
    attempts = 0
    while True:
        face = rng.randint(1, dice.sides)
        if not _matches_reroll(face, dice.reroll_conditions):
            return face
        attempts += 1
        if attempts > MAX_REROLL_ATTEMPTS:
            raise ValueError(
                f"Maximum reroll attempt limit ({MAX_REROLL_ATTEMPTS}) exceeded."
            )


def roll_dice_pool(dice: DiceNotation, rng: RandomNumberGenerator) -> int:
    """Evaluate one dice-pool portion before applying the flat modifier."""
    chains: list[int] = []
    for _ in range(dice.count):
        face = _roll_accepted_face(dice, rng)
        chain_total = face
        additional = 0
        while _matches_explosion(face, dice):
            additional += 1
            if additional > MAX_EXPLOSION_CHAIN_ROLLS:
                raise ValueError(
                    "Maximum explosion chain limit "
                    f"({MAX_EXPLOSION_CHAIN_ROLLS}) exceeded."
                )
            face = _roll_accepted_face(dice, rng)
            chain_total += face
        chains.append(chain_total)

    values = sorted(chains)
    if dice.selection_mode is PoolSelectionMode.KEEP_HIGHEST:
        values = values[-(dice.selection_count or 0) :]
    elif dice.selection_mode is PoolSelectionMode.KEEP_LOWEST:
        values = values[: dice.selection_count or 0]
    elif dice.selection_mode is PoolSelectionMode.DROP_HIGHEST:
        values = values[: len(values) - (dice.selection_count or 0)]
    elif dice.selection_mode is PoolSelectionMode.DROP_LOWEST:
        values = values[dice.selection_count or 0 :]
    return sum(values)


def roll_damage_formula(
    notation: str, *, critical: bool = False, rng: RandomNumberGenerator | None = None
) -> int:
    """Roll a full damage formula, applying the modifier once after pool rolls."""
    dice = parse_dice_notation(notation)
    random_number_generator = rng if rng is not None else Random()
    total = roll_dice_pool(dice, random_number_generator)
    if critical:
        total += roll_dice_pool(dice, random_number_generator)
    return max(0, total + dice.modifier)


def roll_dice(notation: str, rng: RandomNumberGenerator | None = None) -> int:
    """Roll a full damage formula and return nonnegative damage."""
    return roll_damage_formula(notation, rng=rng)
