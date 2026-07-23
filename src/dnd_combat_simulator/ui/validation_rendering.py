"""Streamlit rendering helpers for structured validation issues."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping

from dnd_combat_simulator.ui.validation import ValidationIssue


def issues_by_widget_key(
    issues: Iterable[ValidationIssue],
) -> dict[str, tuple[ValidationIssue, ...]]:
    grouped: dict[str, list[ValidationIssue]] = defaultdict(list)
    for issue in issues:
        if issue.widget_key:
            grouped[issue.widget_key].append(issue)
    return {key: tuple(value) for key, value in grouped.items()}


def validation_errors_by_key(issues: Iterable[ValidationIssue]) -> dict[str, str]:
    return {
        key: " ".join(issue.message for issue in grouped)
        for key, grouped in issues_by_widget_key(issues).items()
    }


def _render_error(message: str) -> None:
    import streamlit as st

    st.error(message, icon="⚠️")


def render_field_issues(
    issues: Mapping[str, tuple[ValidationIssue, ...]] | Mapping[str, str],
    widget_key: str,
) -> bool:
    if widget_key not in issues:
        return False
    value = issues[widget_key]
    if isinstance(value, str):
        message = value
    else:
        message = " ".join(issue.message for issue in value)
    _render_error(message)
    return True


# Compatibility name for existing input rendering code; validation owns structure,
# this module owns rendering.
def _field_error(
    errors_by_key: Mapping[str, tuple[ValidationIssue, ...]] | Mapping[str, str],
    key: str,
) -> bool:
    return render_field_issues(errors_by_key, key)


__all__ = ["issues_by_widget_key", "render_field_issues", "validation_errors_by_key"]
