from __future__ import annotations

import ast
import importlib
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from dnd_combat_simulator.build_math import BuildMathDefaults

_FIELD_NAMES = (
    "ability_modifier",
    "proficiency_bonus",
    "attack_bonus_adjustment",
    "damage_bonus_adjustment",
    "save_dc_adjustment",
)

_INVALID_VALUES: tuple[Any, ...] = (3.5, "2", None, True, [], {})


def test_default_values_calculate_current_common_starting_values() -> None:
    defaults = BuildMathDefaults()

    assert defaults.ability_modifier == 3
    assert defaults.proficiency_bonus == 2
    assert defaults.attack_bonus_adjustment == 0
    assert defaults.damage_bonus_adjustment == 0
    assert defaults.save_dc_adjustment == 0

    assert defaults.attack_bonus == 5
    assert defaults.damage_modifier == 3
    assert defaults.save_dc == 13


def test_positive_adjustments_are_included_in_derived_values() -> None:
    defaults = BuildMathDefaults(
        ability_modifier=5,
        proficiency_bonus=4,
        attack_bonus_adjustment=1,
        damage_bonus_adjustment=2,
        save_dc_adjustment=1,
    )

    assert defaults.attack_bonus == 10
    assert defaults.damage_modifier == 7
    assert defaults.save_dc == 18


def test_negative_values_are_valid_and_calculated() -> None:
    defaults = BuildMathDefaults(
        ability_modifier=-1,
        proficiency_bonus=2,
        attack_bonus_adjustment=-3,
        damage_bonus_adjustment=-2,
        save_dc_adjustment=-4,
    )

    assert defaults.attack_bonus == -2
    assert defaults.damage_modifier == -3
    assert defaults.save_dc == 5


def test_zero_values_are_valid_and_calculated() -> None:
    defaults = BuildMathDefaults(
        ability_modifier=0,
        proficiency_bonus=0,
        attack_bonus_adjustment=0,
        damage_bonus_adjustment=0,
        save_dc_adjustment=0,
    )

    assert defaults.attack_bonus == 0
    assert defaults.damage_modifier == 0
    assert defaults.save_dc == 8


def test_build_math_defaults_are_immutable() -> None:
    defaults = BuildMathDefaults()

    with pytest.raises(FrozenInstanceError):
        defaults.ability_modifier = 4  # type: ignore[misc]


def test_equivalent_instances_compare_equal_and_hash_equally() -> None:
    first = BuildMathDefaults(ability_modifier=4, proficiency_bonus=3)
    second = BuildMathDefaults(ability_modifier=4, proficiency_bonus=3)

    assert first == second
    assert hash(first) == hash(second)
    assert {first, second} == {first}
    assert {first: "stored"}[second] == "stored"


@pytest.mark.parametrize("field_name", _FIELD_NAMES)
@pytest.mark.parametrize("invalid_value", _INVALID_VALUES)
def test_invalid_field_types_are_rejected_with_field_name(
    field_name: str,
    invalid_value: Any,
) -> None:
    kwargs = {field_name: invalid_value}

    with pytest.raises(ValueError, match=field_name):
        BuildMathDefaults(**kwargs)


def test_build_math_module_does_not_import_streamlit() -> None:
    source = Path("src/dnd_combat_simulator/build_math.py").read_text()
    tree = ast.parse(source)

    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.append(node.module)

    assert "streamlit" not in imported_modules
    assert all(not module.startswith("streamlit.") for module in imported_modules)


def test_importing_build_math_does_not_touch_streamlit_or_session_state() -> None:
    sys.modules.pop("dnd_combat_simulator.build_math", None)
    sys.modules.pop("streamlit", None)

    module = importlib.import_module("dnd_combat_simulator.build_math")

    assert module.BuildMathDefaults().attack_bonus == 5
    assert "streamlit" not in sys.modules
    assert "session_state" not in vars(module)
