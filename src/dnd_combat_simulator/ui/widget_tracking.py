"""Track Streamlit widget keys rendered during one app run."""

from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
from typing import Any, Iterator

RENDERED_WIDGET_KEYS_STATE_KEY = "__dnd_rendered_widget_keys"
_WIDGET_METHODS = (
    "button",
    "checkbox",
    "number_input",
    "radio",
    "selectbox",
    "text_input",
    "toggle",
)


def reset_rendered_widget_keys(state: Any) -> set[str]:
    rendered: set[str] = set()
    state[RENDERED_WIDGET_KEYS_STATE_KEY] = rendered
    return rendered


def rendered_widget_keys(state: Any) -> set[str]:
    try:
        value = state[RENDERED_WIDGET_KEYS_STATE_KEY]
    except (KeyError, TypeError):
        return set()
    if isinstance(value, set):
        return {str(key) for key in value}
    return {str(key) for key in value} if isinstance(value, (list, tuple)) else set()


def _record_key(rendered: set[str], args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    key = kwargs.get("key")
    if key is not None:
        rendered.add(str(key))


@contextmanager
def track_streamlit_widget_keys(st: Any) -> Iterator[set[str]]:
    """Record exact widget keys passed to common Streamlit widget calls."""
    rendered = reset_rendered_widget_keys(getattr(st, "session_state", {}))
    patched: list[tuple[Any, str, Any]] = []

    def patch_target(target: Any) -> Any:
        if target is None:
            return target
        for name in _WIDGET_METHODS:
            original = getattr(target, name, None)
            if original is None or getattr(original, "_dnd_tracks_widget_key", False):
                continue

            @wraps(original)
            def wrapper(*args: Any, __original=original, **kwargs: Any) -> Any:
                _record_key(rendered, args, kwargs)
                return __original(*args, **kwargs)

            wrapper._dnd_tracks_widget_key = True  # type: ignore[attr-defined]
            try:
                setattr(target, name, wrapper)
            except (AttributeError, TypeError):
                continue
            patched.append((target, name, original))
        return target

    def patch_factory(name: str) -> None:
        original = getattr(st, name, None)
        if original is None or getattr(original, "_dnd_tracks_widget_key", False):
            return

        @wraps(original)
        def wrapper(*args: Any, __original=original, **kwargs: Any) -> Any:
            result = __original(*args, **kwargs)
            if isinstance(result, (list, tuple)):
                for item in result:
                    patch_target(item)
            else:
                patch_target(result)
            return result

        wrapper._dnd_tracks_widget_key = True  # type: ignore[attr-defined]
        try:
            setattr(st, name, wrapper)
        except (AttributeError, TypeError):
            return
        patched.append((st, name, original))

    patch_target(st)
    for factory in ("columns", "container", "expander", "popover"):
        patch_factory(factory)
    try:
        yield rendered
    finally:
        for target, name, original in reversed(patched):
            try:
                setattr(target, name, original)
            except (AttributeError, TypeError):
                pass
