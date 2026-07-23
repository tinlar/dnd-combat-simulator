from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dnd_combat_simulator.simulation import AttackProfile, BuildConfig, ScenarioConfig
from dnd_combat_simulator.ui import run_control
from dnd_combat_simulator.ui.run_control import (
    ComparisonInputs,
    SingleBuildInputs,
    canonical_comparison_request,
    canonical_single_build_request,
)


def _build(name: str = "Build", damage: str = "1d8+3") -> BuildConfig:
    profile = AttackProfile(
        name="Strike",
        attack_bonus=5,
        damage_dice=damage,
        attacks_per_round=1,
        attack_id="attack-a",
    )
    return BuildConfig(
        name=name,
        attack_bonus=5,
        damage_dice=damage,
        attacks_per_round=1,
        attack_profiles=(profile,),
    )


def _scenario(simulations: int = 10, armor: int = 15) -> ScenarioConfig:
    return ScenarioConfig(target_armor_class=armor, rounds=2, simulations=simulations)


def test_canonical_request_changes_for_result_affecting_fields() -> None:
    base = canonical_single_build_request(
        SingleBuildInputs(build=_build(), scenario=_scenario(), seed=1)
    )
    assert base == canonical_single_build_request(
        SingleBuildInputs(build=_build(), scenario=_scenario(), seed=1)
    )
    assert base != canonical_single_build_request(
        SingleBuildInputs(build=_build(), scenario=_scenario(), seed=2)
    )
    assert base != canonical_single_build_request(
        SingleBuildInputs(build=_build(), scenario=_scenario(simulations=11), seed=1)
    )
    assert base != canonical_single_build_request(
        SingleBuildInputs(build=_build(), scenario=_scenario(armor=16), seed=1)
    )
    assert base != canonical_single_build_request(
        SingleBuildInputs(build=_build(damage="1d10+3"), scenario=_scenario(), seed=1)
    )


def test_comparison_cache_identity_isolated() -> None:
    first = _build("A", "1d8+3")
    second = _build("B", "1d6+3")
    scenario = _scenario()
    single = canonical_single_build_request(
        SingleBuildInputs(build=first, scenario=scenario, seed=1)
    )
    comparison = canonical_comparison_request(
        ComparisonInputs(
            first_build=first,
            second_build=second,
            scenario=scenario,
            seed=1,
        )
    )
    reversed_comparison = canonical_comparison_request(
        ComparisonInputs(
            first_build=second,
            second_build=first,
            scenario=scenario,
            seed=1,
        )
    )
    assert single != comparison
    assert comparison != reversed_comparison


def test_cache_version_participates_in_request_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = SingleBuildInputs(build=_build(), scenario=_scenario(), seed=1)
    old = canonical_single_build_request(inputs)
    monkeypatch.setattr(run_control, "SIMULATION_CACHE_VERSION", old.cache_version + 1)
    assert canonical_single_build_request(inputs) != old


def test_invalid_request_never_reaches_cached_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fail_if_called(request: run_control.CanonicalSimulationRequest):
        nonlocal called
        called = True
        return run_control._execute_canonical_request_uncached(request)

    monkeypatch.setattr(
        run_control, "_cached_execute_canonical_request", fail_if_called
    )
    request = canonical_single_build_request(
        SingleBuildInputs(build=_build(), scenario=_scenario(simulations=0), seed=1)
    )
    with pytest.raises(ValueError):
        run_control.execute_canonical_request(request)
    assert called is False


def test_stage3_architecture_source_rules() -> None:
    ui_root = Path("src/dnd_combat_simulator/ui")
    for path in ui_root.glob("*.py"):
        source = path.read_text()
        assert "# ruff: noqa" not in source
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "dnd_combat_simulator.app"
                assert not any(alias.name == "*" for alias in node.names)
    assert (
        "streamlit"
        not in Path("src/dnd_combat_simulator/ui/widget_keys.py").read_text()
    )
    assert (
        "import streamlit"
        not in Path("src/dnd_combat_simulator/ui/validation.py").read_text()
    )
    app_source = Path("src/dnd_combat_simulator/app.py").read_text()
    assert "sys.modules" not in app_source
    assert "importlib" not in app_source
    assert "globals()" not in app_source
    assert "_sync_ui_module_globals" not in app_source
    assert '__all__ = ("configure_page", "main")' in app_source


def test_page_has_no_compatibility_facade_or_runtime_module_mutation() -> None:
    import dnd_combat_simulator.app as app
    import dnd_combat_simulator.ui.page as page

    path = Path("src/dnd_combat_simulator/ui/page.py")
    source = path.read_text()
    tree = ast.parse(source)
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child.parent = parent

    assert app.__all__ == ("configure_page", "main")
    assert page.__all__ == ("main",)
    forbidden_text = (
        "_TRANSITIONAL_TEST_SEAMS",
        "transitional test seams",
        "_COMPAT_EXPORTS",
        "module-level __getattr__",
        "importlib.import_module",
        "dynamic compatibility lookup",
        "compatibility wrapper functions",
        "assignment into attributes of another imported module",
        "Legacy test compatibility",
        "_page_mount_unified_share_component",
    )
    for text in forbidden_text:
        assert text not in source

    imported_names: set[str] = set()
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module != "importlib"
            if node.module == "__future__":
                continue
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            assert not any(alias.name == "importlib" for alias in node.names)
            for alias in node.names:
                imported_modules.add((alias.asname or alias.name).split(".")[0])

    loaded_names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    assert imported_names <= loaded_names

    for node in ast.walk(tree):
        assert not (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "__getattr__"
            and isinstance(getattr(node, "parent", None), ast.Module)
        )
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                assert not (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id in imported_modules
                )
