# ruff: noqa
"""Shared imports for Streamlit UI modules."""

from __future__ import annotations

import logging
import time
from contextlib import nullcontext
from dataclasses import dataclass
from secrets import randbelow
from textwrap import dedent
from uuid import uuid4

from dnd_combat_simulator import APP_TITLE
from dnd_combat_simulator.combat import (
    AttackFeature,
    AttackRollMode,
    ResolutionType,
    SuccessfulSaveDamage,
    available_features,
    is_feature_available,
    validate_feature_resolution_combination,
)
from dnd_combat_simulator.share_store import (
    InvalidShareIdError,
    ShareNotFoundError,
    ShareStore,
    ShareStoreError,
    StoredShareConfigurationError,
    SupabaseShareStore,
)
from dnd_combat_simulator.sharing import (
    SharedBuildConfiguration,
    SharedConfiguration,
    SharedConfigurationError,
    build_share_url,
    build_short_share_url,
    deserialize_shared_configuration,
    migrate_shared_build_attack_ids,
    serialize_shared_configuration,
    shared_configuration_from_configs,
)
from dnd_combat_simulator.simulation import (
    AttackProfile,
    AttackProfileResult,
    BuildComparisonResult,
    BuildConfig,
    ManagedResource,
    ResourceCost,
    ScenarioConfig,
    SimulationResult,
    TriggerFrequency,
    TriggerType,
    compare_builds,
    run_damage_simulations,
    simulate_build,
)
