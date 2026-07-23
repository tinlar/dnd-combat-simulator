"""Streamlit rendering helpers for structured validation issues."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from dnd_combat_simulator.ui.validation import ValidationIssue


def render_validation_error(message: str) -> None:
    import streamlit as st

    st.error(message, icon="⚠️")


def render_field_validation(
    issues_by_widget_key: Mapping[str, Sequence[ValidationIssue]], widget_key: str
) -> bool:
    issues = tuple(issues_by_widget_key.get(widget_key, ()))
    for issue in issues:
        render_validation_error(issue.message)
    return bool(issues)


def render_field_error(errors_by_key: Mapping[str, str], key: str) -> bool:
    if message := errors_by_key.get(key):
        render_validation_error(message)
        return True
    return False
