"""Architecture regression tests for the modular Streamlit UI."""

from __future__ import annotations

import ast
import importlib
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

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


def test_managed_resource_delete_is_bottom_aligned_icon_button(monkeypatch) -> None:
    from dnd_combat_simulator.ui.inputs import _render_managed_resources
    from dnd_combat_simulator.ui.widget_keys import build_managed_resource_ids_key

    column_calls = []
    button_calls = []

    class Column:
        def text_input(self, _label, **_kwargs):
            return "Focus"

        def number_input(self, _label, **_kwargs):
            return 1

        def selectbox(self, _label, **kwargs):
            return kwargs["options"][0]

        def button(self, label, **kwargs):
            button_calls.append((label, kwargs))
            return False

    def columns(spec, **kwargs):
        column_calls.append((spec, kwargs))
        return [Column() for _ in spec]

    state = {build_managed_resource_ids_key("first"): ["focus"]}
    fake_streamlit = SimpleNamespace(
        session_state=state,
        expander=lambda *args, **kwargs: nullcontext(),
        container=lambda *args, **kwargs: nullcontext(),
        caption=lambda *args, **kwargs: None,
        columns=columns,
        button=lambda *args, **kwargs: False,
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    _render_managed_resources(build_prefix="first")

    assert column_calls == [([3, 2, 2, 1], {"vertical_alignment": "bottom"})]
    assert button_calls == [
        (
            ":material/delete:",
            {
                "key": "first-managed-resource-focus-delete",
                "help": "Delete Focus. Requires confirmation.",
                "type": "tertiary",
            },
        )
    ]
