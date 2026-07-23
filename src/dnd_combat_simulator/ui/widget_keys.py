"""Focused Streamlit UI helpers."""

from __future__ import annotations

from dnd_combat_simulator.combat import (
    AttackFeature,
)
from dnd_combat_simulator.ui.constants import (
    ATTACK_IDS_KEY_SUFFIX,
    TRIGGER_EXPANDED_KEY_SUFFIX,
)


def _looks_like_widget_prefix(build_prefix: str, attack_id: str) -> bool:
    return attack_id.startswith(f"{build_prefix}-primary") or attack_id.startswith(
        f"{build_prefix}-additional-"
    )


def build_attack_ids_key(build_prefix: str) -> str:
    return f"{build_prefix}-{ATTACK_IDS_KEY_SUFFIX}"


def profile_prefix(build_prefix: str, index: int) -> str:
    return (
        f"{build_prefix}-primary"
        if index == 0
        else f"{build_prefix}-additional-{index}"
    )


def attack_widget_prefix(build_prefix: str, attack_id: str) -> str:
    return f"{build_prefix}-{attack_id}"


def _state_widget_prefix(build_prefix: str, attack_id: str) -> str:
    if _looks_like_widget_prefix(build_prefix, attack_id):
        return attack_id
    return attack_widget_prefix(build_prefix, attack_id)


def profile_widget_key(prefix: str, field: str) -> str:
    suffixes = {
        "name": "name",
        "resolution_type": "resolution-type",
        "attack_bonus": "attack-bonus",
        "save_dc": "save-dc",
        "successful_save_damage": "successful-save-damage",
        "attack_roll_mode": "mode",
        "damage_formula": "damage-dice",
        "attacks_per_round": "attacks",
        "affected_targets": "affected-targets",
        "active_rounds": "active-rounds",
        "trigger_type": "trigger-type",
        "trigger_source_attack_id": "trigger-source-attack-id",
        "trigger_frequency": "trigger-frequency",
        "trigger_chance_percent": "trigger-chance-percent",
        "resource_enabled": "resource-enabled",
        "resource_id": "resource-id",
        "resource_amount": "resource-amount",
    }
    return f"{prefix}-{suffixes[field]}"


def feature_widget_key(prefix: str, feature: AttackFeature) -> str:
    return f"{prefix}-feature-{feature.value}"


def trigger_expanded_state_key(profile_id: str) -> str:
    """Return the persistent session key for one trigger editor expansion state."""
    return f"{profile_id}-{TRIGGER_EXPANDED_KEY_SUFFIX}"


def managed_resource_widget_key(resource_id: int | str, field: str) -> str:
    return f"scenario-managed-resource-{resource_id}-{field}"
