from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from dnd_combat_simulator.build_math import BuildMathDefaults

_FIELD_NAMES = (
    "ability_modifier",
    "proficiency_bonus",
    "attack_bonus_adjustment",
    "save_dc_adjustment",
)

_INVALID_VALUES: tuple[Any, ...] = (3.5, "2", None, True, [], {})


def test_default_values_calculate_current_common_starting_values() -> None:
    defaults = BuildMathDefaults()

    assert defaults.ability_modifier == 3
    assert defaults.proficiency_bonus == 2
    assert defaults.attack_bonus_adjustment == 0
    assert defaults.save_dc_adjustment == 0

    assert defaults.attack_bonus == 5
    assert defaults.save_dc == 13


def test_positive_adjustments_are_included_in_derived_values() -> None:
    defaults = BuildMathDefaults(
        ability_modifier=5,
        proficiency_bonus=4,
        attack_bonus_adjustment=1,
        save_dc_adjustment=1,
    )

    assert defaults.attack_bonus == 10
    assert defaults.save_dc == 18


def test_negative_values_are_valid_and_calculated() -> None:
    defaults = BuildMathDefaults(
        ability_modifier=-1,
        proficiency_bonus=2,
        attack_bonus_adjustment=-3,
        save_dc_adjustment=-4,
    )

    assert defaults.attack_bonus == -2
    assert defaults.save_dc == 5


def test_zero_values_are_valid_and_calculated() -> None:
    defaults = BuildMathDefaults(
        ability_modifier=0,
        proficiency_bonus=0,
        attack_bonus_adjustment=0,
        save_dc_adjustment=0,
    )

    assert defaults.attack_bonus == 0
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


def run_build_math_import_probe() -> None:
    script = textwrap.dedent(
        """
        import sys

        assert "streamlit" not in sys.modules

        from dnd_combat_simulator.build_math import BuildMathDefaults

        defaults = BuildMathDefaults()

        assert defaults.attack_bonus == 5
        assert "streamlit" not in sys.modules

        import dnd_combat_simulator.build_math as build_math

        assert "session_state" not in vars(build_math)
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, (
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )


def test_importing_build_math_does_not_touch_streamlit_or_session_state() -> None:
    run_build_math_import_probe()


def test_build_math_import_probe_preserves_parent_modules() -> None:
    __import__("streamlit")

    streamlit_before = sys.modules["streamlit"]
    simulation_before = sys.modules.get("dnd_combat_simulator.simulation")
    run_control_before = sys.modules.get("dnd_combat_simulator.ui.run_control")

    run_build_math_import_probe()

    assert sys.modules["streamlit"] is streamlit_before
    assert sys.modules.get("dnd_combat_simulator.simulation") is simulation_before
    assert sys.modules.get("dnd_combat_simulator.ui.run_control") is run_control_before


def test_build_config_carries_math_defaults_without_changing_legacy_profiles() -> None:
    from dnd_combat_simulator.combat import AttackRollMode
    from dnd_combat_simulator.simulation import BuildConfig

    positional = BuildConfig("Build A", 5, "1d8+3", 1)
    assert positional.math_defaults == BuildMathDefaults()

    profiles = positional.resolved_attack_profiles()
    assert profiles[0].attack_bonus == 5
    assert profiles[0].damage_dice == "1d8+3"
    assert profiles[0].attacks_per_round == 1
    assert profiles[0].attack_roll_mode is AttackRollMode.NORMAL

    custom_defaults = BuildMathDefaults(ability_modifier=9, proficiency_bonus=8)
    custom = BuildConfig(
        name="Build A",
        attack_bonus=5,
        damage_dice="1d8+3",
        attacks_per_round=1,
        math_defaults=custom_defaults,
    )
    assert custom.math_defaults == custom_defaults
    assert custom != positional
    assert hash(custom) != hash(positional)
    assert custom.resolved_attack_profiles()[0].attack_bonus == 5


class _FakeColumn:
    def __init__(self, surface: _FakeStreamlit) -> None:
        self.surface = surface

    def number_input(self, **kwargs: Any) -> int:
        self.surface.number_inputs.append(kwargs)
        key = kwargs["key"]
        return self.surface.session_state.get(key, kwargs.get("value"))

    def metric(self, label: str, value: str) -> None:
        self.surface.metrics.append((label, value))


class _FakeContainer:
    def __enter__(self) -> _FakeContainer:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _FakeStreamlit:
    def __init__(self, session_state: dict[str, Any] | None = None) -> None:
        self.session_state = {} if session_state is None else session_state
        self.number_inputs: list[dict[str, Any]] = []
        self.metrics: list[tuple[str, str]] = []
        self.markdowns: list[str] = []
        self.captions: list[str] = []

    def columns(self, count: int) -> list[_FakeColumn]:
        return [_FakeColumn(self) for _ in range(count)]

    def container(self, **_kwargs: Any) -> _FakeContainer:
        return _FakeContainer()

    def markdown(self, body: str) -> None:
        self.markdowns.append(body)

    def caption(self, body: str) -> None:
        self.captions.append(body)


def _render_build_math_with_fake(
    monkeypatch: pytest.MonkeyPatch,
    state: dict[str, Any] | None = None,
    *,
    prefix: str = "first",
) -> tuple[BuildMathDefaults, _FakeStreamlit]:
    import dnd_combat_simulator.ui.inputs as inputs

    fake = _FakeStreamlit(state)
    monkeypatch.setitem(sys.modules, "streamlit", fake)

    return inputs._build_math_inputs(prefix), fake


def test_build_math_inputs_render_default_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults, fake = _render_build_math_with_fake(monkeypatch)

    assert defaults == BuildMathDefaults()
    assert fake.markdowns == ["##### Build Setup"]
    assert [(entry["label"], entry["value"]) for entry in fake.number_inputs] == [
        ("Ability modifier", 3),
        ("Proficiency bonus", 2),
        ("Other attack bonus", 0),
        ("Other Save DC bonus", 0),
    ]
    assert fake.metrics == [
        ("Attack bonus", "+5"),
        ("Save DC", "13"),
    ]
    assert all(entry["step"] == 1 for entry in fake.number_inputs)
    assert all(entry["format"] == "%d" for entry in fake.number_inputs)


def test_build_math_inputs_use_existing_session_values_without_competing_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dnd_combat_simulator.ui.widget_keys import build_math_state_key

    state = {
        build_math_state_key("first", "ability_modifier"): -1,
        build_math_state_key("first", "proficiency_bonus"): 0,
        build_math_state_key("first", "attack_bonus_adjustment"): 999,
        build_math_state_key("first", "save_dc_adjustment"): 10,
    }

    defaults, fake = _render_build_math_with_fake(monkeypatch, state)

    assert defaults == BuildMathDefaults(
        ability_modifier=-1,
        proficiency_bonus=0,
        attack_bonus_adjustment=999,
        save_dc_adjustment=10,
    )
    assert all("value" not in entry for entry in fake.number_inputs)
    assert fake.metrics == [
        ("Attack bonus", "+998"),
        ("Save DC", "17"),
    ]


def test_build_math_inputs_use_stable_keys_and_isolate_builds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dnd_combat_simulator.ui.widget_keys import build_math_state_key

    state = {
        build_math_state_key("first", "ability_modifier"): 5,
        build_math_state_key("second", "ability_modifier"): -4,
    }

    first, first_fake = _render_build_math_with_fake(monkeypatch, state, prefix="first")
    second, second_fake = _render_build_math_with_fake(
        monkeypatch, state, prefix="second"
    )

    first_keys = {entry["key"] for entry in first_fake.number_inputs}
    second_keys = {entry["key"] for entry in second_fake.number_inputs}
    assert first.ability_modifier == 5
    assert second.ability_modifier == -4
    assert first_keys.isdisjoint(second_keys)
    assert first_keys == {
        build_math_state_key("first", field) for field in _FIELD_NAMES
    }
    assert second_keys == {
        build_math_state_key("second", field) for field in _FIELD_NAMES
    }
