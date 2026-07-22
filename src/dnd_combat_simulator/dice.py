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
    """Parsed representation of one dice group."""

    count: int
    sides: int
    modifier: int = 0
    explosion_mode: ExplosionMode | None = None
    explosion_threshold: int | None = None
    selection_mode: PoolSelectionMode | None = None
    selection_count: int | None = None
    reroll_conditions: tuple[RerollCondition, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiceTerm:
    """One signed dice group in a damage expression."""

    dice: DiceNotation
    sign: int = 1


@dataclass(frozen=True)
class ConstantTerm:
    """One signed numeric modifier in a damage expression."""

    value: int


DamageTerm = DiceTerm | ConstantTerm


@dataclass(frozen=True)
class DamageExpression:
    """A complete damage expression composed of independent signed terms."""

    terms: tuple[DamageTerm, ...]


@dataclass(frozen=True)
class DieChainRoll:
    """Resolved rolls for one initial die and any explosion-generated dice."""

    rolls: tuple[int, ...]
    total: int
    retained: bool


@dataclass(frozen=True)
class DiceTermRoll:
    """Breakdown for one resolved dice term."""

    term: DiceTerm
    chains: tuple[DieChainRoll, ...]
    subtotal: int


@dataclass(frozen=True)
class ConstantTermRoll:
    """Breakdown for one resolved constant term."""

    term: ConstantTerm
    subtotal: int


@dataclass(frozen=True)
class DamageRollBreakdown:
    """Detailed resolution of a complete damage roll."""

    expression: DamageExpression
    terms: tuple[DiceTermRoll | ConstantTermRoll, ...]
    total: int


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


def _parse_dice_group(group: str, *, original: str) -> DiceNotation:
    dice = parse_dice_notation(group)
    if dice.modifier:
        msg = (
            f"Invalid damage expression {original!r}: numeric modifiers must be "
            "separate terms in compound expressions."
        )
        raise ValueError(msg)
    return dice


def parse_damage_expression(notation: str) -> DamageExpression:
    """Parse a complete damage expression into independent dice and constant terms."""
    text = notation.strip()
    if not text:
        raise ValueError("Invalid damage expression: expression is required.")
    if any(character.isspace() for character in text):
        raise ValueError("Invalid dice notation: spaces are not supported.")
    if re.search(r"[^0-9d+\-!<>rkhld]", text):
        raise ValueError(
            "Invalid damage expression: invalid characters are not supported."
        )
    if re.search(r"[+\-]{2,}", text):
        raise ValueError(
            "Invalid damage expression: consecutive operators are not supported."
        )
    if re.search(r"(?:^|[+\-])d\d+", text):
        raise ValueError("Invalid damage expression: missing dice count.")

    terms: list[DamageTerm] = []
    position = 0
    sign = 1
    expecting_term = True
    while position < len(text):
        character = text[position]
        if character in "+-":
            if expecting_term:
                if position == 0:
                    raise ValueError(
                        "Invalid damage expression: cannot start with a sign."
                    )
                raise ValueError(
                    "Invalid damage expression: missing term between operators."
                )
            sign = 1 if character == "+" else -1
            position += 1
            expecting_term = True
            if position == len(text):
                raise ValueError(
                    "Invalid damage expression: damage expression cannot end "
                    "with an operator."
                )
            continue

        start = position
        while position < len(text) and text[position] not in "+-":
            position += 1
        token = text[start:position]
        if not token:
            raise ValueError("Invalid damage expression: empty term.")
        if "d" in token:
            terms.append(DiceTerm(_parse_dice_group(token, original=notation), sign))
        elif _INT_PATTERN.fullmatch(token):
            terms.append(ConstantTerm(sign * int(token)))
        else:
            if "d" in token.lower() and "d" not in token:
                raise ValueError(
                    "Invalid damage expression: dice separator must be lowercase 'd'."
                )
            raise ValueError(
                f"Invalid damage expression {notation!r}: unsupported dice "
                f"modifiers or malformed modifier syntax in {token!r}."
            )
        expecting_term = False

    if not terms:
        raise ValueError("Invalid damage expression: expression is required.")
    return DamageExpression(tuple(terms))


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


def _damage_contribution(face: int, features: frozenset[str]) -> int:
    if "great_weapon_fighting" in features and face in {1, 2}:
        return 3
    return face


def _roll_feature_adjusted_face(
    dice: DiceNotation, rng: RandomNumberGenerator, features: frozenset[str]
) -> tuple[int, int]:
    face = _roll_accepted_face(dice, rng)
    if "tavern_brawler" in features and face == 1:
        face = rng.randint(1, dice.sides)
    return face, _damage_contribution(face, features)


def _roll_dice_pool_breakdown(
    term: DiceTerm,
    rng: RandomNumberGenerator,
    *,
    features: frozenset[str] = frozenset(),
) -> DiceTermRoll:
    dice = term.dice
    chain_data: list[tuple[tuple[int, ...], int]] = []
    for _ in range(dice.count):
        face, contribution = _roll_feature_adjusted_face(dice, rng, features)
        rolls = [face]
        chain_total = contribution
        additional = 0
        while _matches_explosion(face, dice):
            additional += 1
            if additional > MAX_EXPLOSION_CHAIN_ROLLS:
                raise ValueError(
                    "Maximum explosion chain limit "
                    f"({MAX_EXPLOSION_CHAIN_ROLLS}) exceeded."
                )
            face, contribution = _roll_feature_adjusted_face(dice, rng, features)
            rolls.append(face)
            chain_total += contribution
        chain_data.append((tuple(rolls), chain_total))

    retained_indexes = set(range(len(chain_data)))
    indexed_totals = sorted(enumerate(chain_data), key=lambda item: item[1][1])
    selection_count = dice.selection_count or 0
    if dice.selection_mode is PoolSelectionMode.KEEP_HIGHEST:
        retained_indexes = {index for index, _ in indexed_totals[-selection_count:]}
    elif dice.selection_mode is PoolSelectionMode.KEEP_LOWEST:
        retained_indexes = {index for index, _ in indexed_totals[:selection_count]}
    elif dice.selection_mode is PoolSelectionMode.DROP_HIGHEST:
        retained_indexes = {
            index
            for index, _ in indexed_totals[: len(indexed_totals) - selection_count]
        }
    elif dice.selection_mode is PoolSelectionMode.DROP_LOWEST:
        retained_indexes = {index for index, _ in indexed_totals[selection_count:]}

    chains = tuple(
        DieChainRoll(rolls=rolls, total=total, retained=index in retained_indexes)
        for index, (rolls, total) in enumerate(chain_data)
    )
    subtotal = term.sign * sum(chain.total for chain in chains if chain.retained)
    return DiceTermRoll(term=term, chains=chains, subtotal=subtotal)


def _roll_dice_pool_int(
    term: DiceTerm,
    rng: RandomNumberGenerator,
    *,
    features: frozenset[str] = frozenset(),
) -> int:
    """Evaluate one dice term without allocating detailed roll breakdown objects."""
    dice = term.dice
    chain_totals: list[int] = []
    for _ in range(dice.count):
        face, contribution = _roll_feature_adjusted_face(dice, rng, features)
        chain_total = contribution
        additional = 0
        while _matches_explosion(face, dice):
            additional += 1
            if additional > MAX_EXPLOSION_CHAIN_ROLLS:
                raise ValueError(
                    "Maximum explosion chain limit "
                    f"({MAX_EXPLOSION_CHAIN_ROLLS}) exceeded."
                )
            face, contribution = _roll_feature_adjusted_face(dice, rng, features)
            chain_total += contribution
        chain_totals.append(chain_total)

    retained_indexes = set(range(len(chain_totals)))
    indexed_totals = sorted(enumerate(chain_totals), key=lambda item: item[1])
    selection_count = dice.selection_count or 0
    if dice.selection_mode is PoolSelectionMode.KEEP_HIGHEST:
        retained_indexes = {index for index, _ in indexed_totals[-selection_count:]}
    elif dice.selection_mode is PoolSelectionMode.KEEP_LOWEST:
        retained_indexes = {index for index, _ in indexed_totals[:selection_count]}
    elif dice.selection_mode is PoolSelectionMode.DROP_HIGHEST:
        retained_indexes = {
            index
            for index, _ in indexed_totals[: len(indexed_totals) - selection_count]
        }
    elif dice.selection_mode is PoolSelectionMode.DROP_LOWEST:
        retained_indexes = {index for index, _ in indexed_totals[selection_count:]}

    return term.sign * sum(
        total for index, total in enumerate(chain_totals) if index in retained_indexes
    )


def roll_dice_pool(
    dice: DiceNotation,
    rng: RandomNumberGenerator,
    *,
    features: frozenset[str] = frozenset(),
) -> int:
    """Evaluate one dice-pool portion before applying any flat modifier."""
    return _roll_dice_pool_breakdown(DiceTerm(dice), rng, features=features).subtotal


def roll_compiled_damage_expression(
    expression: DamageExpression,
    *,
    critical: bool = False,
    rng: RandomNumberGenerator | None = None,
    features: frozenset[str] = frozenset(),
) -> int:
    """Roll an already parsed damage expression without building breakdown objects."""
    random_number_generator = rng if rng is not None else Random()
    total = 0
    for term in expression.terms:
        if isinstance(term, ConstantTerm):
            total += term.value
            continue
        total += _roll_dice_pool_int(term, random_number_generator, features=features)
        if critical:
            total += _roll_dice_pool_int(
                term, random_number_generator, features=features
            )
    return max(0, total)


def roll_damage_formula_breakdown(
    notation: str,
    *,
    critical: bool = False,
    rng: RandomNumberGenerator | None = None,
    features: frozenset[str] = frozenset(),
) -> DamageRollBreakdown:
    """Roll a complete damage expression and return a detailed breakdown."""
    expression = parse_damage_expression(notation)
    random_number_generator = rng if rng is not None else Random()
    term_rolls: list[DiceTermRoll | ConstantTermRoll] = []
    total = 0
    for term in expression.terms:
        if isinstance(term, ConstantTerm):
            roll = ConstantTermRoll(term=term, subtotal=term.value)
            term_rolls.append(roll)
            total += roll.subtotal
            continue
        roll = _roll_dice_pool_breakdown(
            term, random_number_generator, features=features
        )
        term_rolls.append(roll)
        total += roll.subtotal
        if critical:
            critical_roll = _roll_dice_pool_breakdown(
                term, random_number_generator, features=features
            )
            term_rolls.append(critical_roll)
            total += critical_roll.subtotal
    return DamageRollBreakdown(
        expression=expression, terms=tuple(term_rolls), total=max(0, total)
    )


def roll_damage_formula(
    notation: str,
    *,
    critical: bool = False,
    rng: RandomNumberGenerator | None = None,
    features: frozenset[str] = frozenset(),
) -> int:
    """Roll a full damage formula, applying constants once after pool rolls."""
    return roll_compiled_damage_expression(
        parse_damage_expression(notation), critical=critical, rng=rng, features=features
    )


def format_damage_roll_breakdown(breakdown: DamageRollBreakdown) -> str:
    """Format a damage roll breakdown for display in UI or logs."""
    parts: list[str] = []
    for roll in breakdown.terms:
        if isinstance(roll, ConstantTermRoll):
            parts.append(f"constant {roll.term.value:+d}")
            continue
        dice = roll.term.dice
        sign = "-" if roll.term.sign < 0 else "+"
        chain_parts = []
        for chain in roll.chains:
            rolls = "+".join(str(face) for face in chain.rolls)
            status = "kept" if chain.retained else "discarded"
            chain_parts.append(f"{rolls}={chain.total} {status}")
        parts.append(
            f"{sign}{dice.count}d{dice.sides}: "
            f"[{'; '.join(chain_parts)}] => {roll.subtotal:+d}"
        )
    return f"{' | '.join(parts)} | total={breakdown.total}"


def roll_dice(notation: str, rng: RandomNumberGenerator | None = None) -> int:
    """Roll a full damage formula and return nonnegative damage."""
    return roll_damage_formula(notation, rng=rng)
