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


class SequenceRng:
    def __init__(self, rolls: list[int]) -> None:
        self.rolls = rolls

    def randint(self, a: int, b: int) -> int:
        return self.rolls.pop(0)


def test_exploding_keep_drop_and_modifier_order() -> None:
    assert roll_dice("4d6!kh3+2", SequenceRng([6, 3, 2, 5, 1])) == 18


@pytest.mark.parametrize(
    ("formula", "rolls", "expected"),
    [
        ("1d6!", [5], 5),
        ("1d6!", [6, 4], 10),
        ("1d6!", [6, 6, 3], 15),
        ("2d6!", [6, 1, 6, 2], 15),
        ("1d6!3", [3, 4], 7),
        ("1d6!>4", [4, 2], 6),
        ("1d6!<3", [3, 5], 8),
    ],
)
def test_exploding_dice_forms(formula: str, rolls: list[int], expected: int) -> None:
    assert roll_dice(formula, SequenceRng(rolls)) == expected


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("4d6k2", 11),
        ("4d6kh2", 11),
        ("4d6kl2", 3),
        ("4d6d2", 11),
        ("4d6dl2", 11),
        ("4d6dh2", 3),
        ("2d6d2+5", 5),
        ("4d6kh3+2", 15),
    ],
)
def test_keep_drop_forms(formula: str, expected: int) -> None:
    assert roll_dice(formula, SequenceRng([1, 2, 5, 6])) == expected


@pytest.mark.parametrize(
    ("formula", "rolls", "expected"),
    [
        ("2d8r8", [8, 3, 4], 7),
        ("2d8r<2", [1, 2, 3, 4], 7),
        ("2d8r>6", [7, 8, 2, 3], 5),
        ("2d8r1r3r5r7", [1, 3, 2, 7, 4], 6),
        ("1d6r1!", [1, 6, 1, 4], 10),
        ("4d6r1kh3+2", [1, 6, 2, 3, 4], 15),
    ],
)
def test_reroll_forms(formula: str, rolls: list[int], expected: int) -> None:
    assert roll_dice(formula, SequenceRng(rolls)) == expected


@pytest.mark.parametrize(
    "formula",
    [
        "1d1!",
        "3d6!>1",
        "3d6!<6",
        "3d6!7",
        "8d100k0",
        "8d100k9",
        "8d100k1d1",
        "3d6!!",
        "2d8r",
        "2d8r0",
        "2d8r9",
        "2d8r<8",
        "2d8r>1",
        "1d1r1",
    ],
)
def test_complex_formula_validation(formula: str) -> None:
    with pytest.raises(ValueError):
        parse_dice_notation(formula)
