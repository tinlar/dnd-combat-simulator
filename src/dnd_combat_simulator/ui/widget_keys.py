"""Focused UI helpers moved from the Streamlit entry point."""

from __future__ import annotations

from dnd_combat_simulator.ui.monolith import (
    ATTACK_DELETE_CONFIRMATION_KEY,
    ATTACK_IDS_KEY_SUFFIX,
    COMPARE_WIDGET_KEY,
    MANAGED_RESOURCE_COUNT_KEY,
    MANAGED_RESOURCE_EXPANDED_KEY,
    MANAGED_RESOURCE_IDS_KEY,
    RESOURCE_DELETE_CONFIRMATION_KEY,
    SCENARIO_WIDGET_KEYS,
    TRIGGER_EXPANDED_KEY_SUFFIX,
    attack_widget_prefix,
    build_attack_ids_key,
    feature_widget_key,
    managed_resource_widget_key,
    profile_prefix,
    profile_widget_key,
    trigger_expanded_state_key,
)

__all__ = [
    "SCENARIO_WIDGET_KEYS",
    "COMPARE_WIDGET_KEY",
    "TRIGGER_EXPANDED_KEY_SUFFIX",
    "MANAGED_RESOURCE_COUNT_KEY",
    "MANAGED_RESOURCE_EXPANDED_KEY",
    "ATTACK_DELETE_CONFIRMATION_KEY",
    "RESOURCE_DELETE_CONFIRMATION_KEY",
    "MANAGED_RESOURCE_IDS_KEY",
    "ATTACK_IDS_KEY_SUFFIX",
    "build_attack_ids_key",
    "profile_prefix",
    "attack_widget_prefix",
    "profile_widget_key",
    "feature_widget_key",
    "managed_resource_widget_key",
    "trigger_expanded_state_key",
]
