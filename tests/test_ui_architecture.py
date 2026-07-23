"""Architecture regression tests for the modular Streamlit UI."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

UI_MODULES = (
    "constants",
    "widget_keys",
    "state",
    "validation",
    "components",
    "inputs",
    "results",
    "sharing",
    "run_control",
)


def test_ui_modules_import_successfully() -> None:
    for module_name in UI_MODULES:
        importlib.import_module(f"dnd_combat_simulator.ui.{module_name}")


def test_ui_modules_do_not_import_app() -> None:
    ui_root = Path("src/dnd_combat_simulator/ui")
    for path in ui_root.glob("*.py"):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = {alias.name for alias in node.names}
                assert "dnd_combat_simulator.app" not in imported, path
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "dnd_combat_simulator.app", path


def test_app_main_remains_available() -> None:
    from dnd_combat_simulator import app

    assert callable(app.main)
