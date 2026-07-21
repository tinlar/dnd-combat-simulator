import pytest

from dnd_combat_simulator.dice import DiceNotation, parse_dice_notation, roll_dice


class PredictableRng:
    def __init__(self, rolls: list[int]) -> None:
        self.rolls = rolls
        self.calls: list[tuple[int, int]] = []

    def randint(self, a: int, b: int) -> int:
        self.calls.append((a, b))
        return self.rolls.pop(0)


@pytest.mark.parametrize(
    ("notation", "expected"),
    [
        ("1d4", DiceNotation(count=1, sides=4)),
        ("1d6", DiceNotation(count=1, sides=6)),
        ("1d8", DiceNotation(count=1, sides=8)),
        ("1d10+4", DiceNotation(count=1, sides=10, modifier=4)),
        ("1d12", DiceNotation(count=1, sides=12)),
        ("2d6-1", DiceNotation(count=2, sides=6, modifier=-1)),
        ("3d8", DiceNotation(count=3, sides=8)),
    ],
)
def test_parse_dice_notation_supported_examples(
    notation: str, expected: DiceNotation
) -> None:
    assert parse_dice_notation(notation) == expected


def test_parse_dice_notation_strips_surrounding_whitespace() -> None:
    assert parse_dice_notation(" 1d6 ") == DiceNotation(count=1, sides=6)


@pytest.mark.parametrize(
    "notation",
    [
        "",
        "d6",
        "1d",
        "0d6",
        "1d0",
        "01d6",
        "1d06",
        "1D6",
        "1d6 + 1",
        "1d6+",
        "1d6-",
        "1d6+1.5",
        "1d6+0x4",
        "one d six",
    ],
)
def test_parse_dice_notation_rejects_invalid_notation(notation: str) -> None:
    with pytest.raises(ValueError, match="Invalid dice notation"):
        parse_dice_notation(notation)


def test_roll_dice_rolls_once_for_single_die() -> None:
    rng = PredictableRng([4])

    assert roll_dice("1d6", rng=rng) == 4
    assert rng.calls == [(1, 6)]


def test_roll_dice_rolls_each_requested_die_and_adds_modifier() -> None:
    rng = PredictableRng([7, 2, 8])

    assert roll_dice("3d8+4", rng=rng) == 21
    assert rng.calls == [(1, 8), (1, 8), (1, 8)]


def test_roll_dice_rolls_each_requested_die_and_subtracts_modifier() -> None:
    rng = PredictableRng([3, 5])

    assert roll_dice("2d6-1", rng=rng) == 7
    assert rng.calls == [(1, 6), (1, 6)]


def test_roll_dice_rejects_invalid_notation() -> None:
    with pytest.raises(ValueError, match="Invalid dice notation"):
        roll_dice("not dice", rng=PredictableRng([]))
