"""Dice notation parsing and rolling utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass
from random import Random
from typing import Protocol


class RandomNumberGenerator(Protocol):
    """Protocol for injectable random number generators."""

    def randint(self, a: int, b: int) -> int:
        """Return a random integer N such that a <= N <= b."""


_DICE_NOTATION_PATTERN = re.compile(
    r"^(?P<count>[1-9]\d*)d(?P<sides>[1-9]\d*)(?P<modifier>[+-]\d+)?$"
)


@dataclass(frozen=True)
class DiceNotation:
    """Parsed representation of simple dice notation."""

    count: int
    sides: int
    modifier: int = 0


def parse_dice_notation(notation: str) -> DiceNotation:
    """Parse simple dice notation into dice count, side count, and modifier.

    Supported notation uses the form ``XdY`` with an optional integer modifier,
    such as ``1d6``, ``2d6-1``, or ``1d10+4``.

    Raises:
        ValueError: If the notation is not a supported dice expression.
    """
    match = _DICE_NOTATION_PATTERN.fullmatch(notation.strip())
    if match is None:
        msg = (
            f"Invalid dice notation {notation!r}. Expected format 'XdY' with an "
            "optional '+N' or '-N' modifier, such as '1d6' or '2d6-1'."
        )
        raise ValueError(msg)

    return DiceNotation(
        count=int(match.group("count")),
        sides=int(match.group("sides")),
        modifier=int(match.group("modifier") or 0),
    )


def roll_dice(notation: str, rng: RandomNumberGenerator | None = None) -> int:
    """Roll dice described by simple notation and return the total.

    Args:
        notation: Dice notation in the form ``XdY`` with an optional modifier.
        rng: Optional random number generator. It must provide ``randint`` and is
            injectable so tests can make rolls deterministic.

    Raises:
        ValueError: If the notation is not supported.
    """
    dice = parse_dice_notation(notation)
    random_number_generator = rng if rng is not None else Random()
    total = sum(
        random_number_generator.randint(1, dice.sides) for _ in range(dice.count)
    )
    return total + dice.modifier
