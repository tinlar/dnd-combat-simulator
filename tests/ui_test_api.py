"""Test-only namespace for UI helpers imported from owning modules."""

import time

import dnd_combat_simulator.ui.components as _components
import dnd_combat_simulator.ui.page as _page
import dnd_combat_simulator.ui.run_control as _run_control
import dnd_combat_simulator.ui.sharing as _sharing
import dnd_combat_simulator.ui.state as _state
from dnd_combat_simulator.ui.components import (  # noqa: F401
    _SHARE_TOOLBAR_COMPONENT,
    ATTACK_TOOLBAR_CSS,
    CONFIGURATION_TOOLBAR_CSS,
    SHARE_TOOLBAR_CSS,
    SHARE_TOOLBAR_HTML,
    SHARE_TOOLBAR_JS,
)
from dnd_combat_simulator.ui.constants import *  # noqa: F403
from dnd_combat_simulator.ui.inputs import (  # noqa: F401
    _build_inputs,
    _render_simulation_settings,
    _trigger_settings_expander,
    _trigger_source_options,
)
from dnd_combat_simulator.ui.results import *  # noqa: F403
from dnd_combat_simulator.ui.run_control import *  # noqa: F403
from dnd_combat_simulator.ui.run_control import (  # noqa: F401
    _mark_simulation_pending,
)
from dnd_combat_simulator.ui.sharing import *  # noqa: F403
from dnd_combat_simulator.ui.sharing import (  # noqa: F401
    _current_short_shared_configuration_url,
    _share_configuration_fingerprint,
    get_supabase_share_store_from_secrets,
)
from dnd_combat_simulator.ui.state import *  # noqa: F403
from dnd_combat_simulator.ui.state import (  # noqa: F401
    ATTACK_WIDGET_STATE_FIELDS,
    _build_from_state,
    _clear_resource_from_profiles,
    _copy_attack_widget_state,
    _delete_attack_state,
    _duplicate_attack_state,
    _generate_default_seed,
    _resource_usage_profile_keys,
)
from dnd_combat_simulator.ui.validation import *  # noqa: F403
from dnd_combat_simulator.ui.validation_rendering import *  # noqa: F403
from dnd_combat_simulator.ui.widget_keys import *  # noqa: F403

_ORIGINAL_SERIALIZE_SHARED_CONFIGURATION = _sharing.serialize_shared_configuration
_ORIGINAL_SHARE_FINGERPRINT = _sharing._share_configuration_fingerprint
_ORIGINAL_GET_STREAMLIT_SHARE_STORE = _sharing.get_streamlit_share_store
_ORIGINAL_RUN_SINGLE_BUILD_FROM_INPUTS = _run_control.run_single_build_from_inputs
_ORIGINAL_GENERATE_DEFAULT_SEED = _state._generate_default_seed


def _sync_share_patches() -> None:
    _sharing.get_streamlit_share_store = globals().get(
        "get_streamlit_share_store", _ORIGINAL_GET_STREAMLIT_SHARE_STORE
    )
    _sharing.serialize_shared_configuration = globals().get(
        "serialize_shared_configuration", _ORIGINAL_SERIALIZE_SHARED_CONFIGURATION
    )
    _sharing._share_configuration_fingerprint = globals().get(
        "_share_configuration_fingerprint", _ORIGINAL_SHARE_FINGERPRINT
    )
    _components._SHARE_TOOLBAR_COMPONENT = globals().get("_SHARE_TOOLBAR_COMPONENT")


def _render_share_configuration_button() -> None:
    _sync_share_patches()
    try:
        return _sharing._render_share_configuration_button()
    finally:
        _sharing.serialize_shared_configuration = (
            _ORIGINAL_SERIALIZE_SHARED_CONFIGURATION
        )
        _sharing._share_configuration_fingerprint = _ORIGINAL_SHARE_FINGERPRINT
        _sharing.get_streamlit_share_store = _ORIGINAL_GET_STREAMLIT_SHARE_STORE


def load_shared_configuration_from_query() -> None:
    _sync_share_patches()
    try:
        return _sharing.load_shared_configuration_from_query(
            store_factory=globals().get(
                "get_streamlit_share_store", _ORIGINAL_GET_STREAMLIT_SHARE_STORE
            )
        )
    finally:
        _sharing.serialize_shared_configuration = (
            _ORIGINAL_SERIALIZE_SHARED_CONFIGURATION
        )
        _sharing._share_configuration_fingerprint = _ORIGINAL_SHARE_FINGERPRINT
        _sharing.get_streamlit_share_store = _ORIGINAL_GET_STREAMLIT_SHARE_STORE


def _run_single_build_with_feedback(inputs):
    _run_control.time = time
    _run_control.run_single_build_from_inputs = globals().get(
        "run_single_build_from_inputs", _ORIGINAL_RUN_SINGLE_BUILD_FROM_INPUTS
    )
    try:
        return _run_control._run_single_build_with_feedback(
            inputs,
            execute=globals().get(
                "run_single_build_from_inputs", _ORIGINAL_RUN_SINGLE_BUILD_FROM_INPUTS
            ),
            clock=time.perf_counter,
        )
    finally:
        _run_control.run_single_build_from_inputs = (
            _ORIGINAL_RUN_SINGLE_BUILD_FROM_INPUTS
        )


def ensure_session_random_seed(state):
    return _state.ensure_session_random_seed(
        state,
        seed_factory=globals().get(
            "_generate_default_seed", _ORIGINAL_GENERATE_DEFAULT_SEED
        ),
    )


def main() -> None:
    _run_control.run_single_build_from_inputs = globals().get(
        "run_single_build_from_inputs", _ORIGINAL_RUN_SINGLE_BUILD_FROM_INPUTS
    )
    try:
        return _page.main()
    finally:
        _run_control.run_single_build_from_inputs = (
            _ORIGINAL_RUN_SINGLE_BUILD_FROM_INPUTS
        )
