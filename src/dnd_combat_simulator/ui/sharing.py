"""Focused Streamlit UI helpers."""

from __future__ import annotations

import logging

from dnd_combat_simulator.combat import (
    ResolutionType,
    SuccessfulSaveDamage,
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
    SharedConfiguration,
    SharedConfigurationError,
    build_share_url,
    build_short_share_url,
    deserialize_shared_configuration,
    serialize_shared_configuration,
    shared_configuration_from_configs,
)
from dnd_combat_simulator.simulation import (
    ScenarioConfig,
)
from dnd_combat_simulator.ui.components import _mount_unified_share_component
from dnd_combat_simulator.ui.constants import (
    COMPARE_WIDGET_KEY,
    GENERATED_SHARE_FINGERPRINT_KEY,
    GENERATED_SHARE_URL_KEY,
    INVALID_SHARED_CONFIG_MESSAGE_KEY,
    LOADED_SHARE_ID_KEY,
    LOADED_SHARED_CONFIG_MESSAGE_KEY,
    LOADED_SHARED_CONFIG_TOKEN_KEY,
    SCENARIO_WIDGET_KEYS,
    SHARE_ERROR_MESSAGE_KEY,
)
from dnd_combat_simulator.ui.state import (
    _build_from_state,
    _managed_resources_from_state,
    hydrate_session_state_from_shared_configuration,
)
from dnd_combat_simulator.ui.validation import (
    _validation_errors_for_configuration,
    validate_configuration_for_ui,
)

logger = logging.getLogger(__name__)


def _resolution_type_label(resolution_type: ResolutionType) -> str:
    return {
        ResolutionType.ATTACK_ROLL: "Attack Roll",
        ResolutionType.SAVING_THROW: "Saving Throw",
        ResolutionType.AUTOMATIC_DAMAGE: "Automatic Damage",
    }[resolution_type]


def _successful_save_damage_label(value: SuccessfulSaveDamage) -> str:
    return "Half damage" if value is SuccessfulSaveDamage.HALF_DAMAGE else "No damage"


def share_store_ui_message(error: Exception) -> str:
    """Map share storage exceptions to safe end-user messages."""
    if isinstance(error, ShareNotFoundError):
        return "This shared configuration could not be found."
    if isinstance(error, InvalidShareIdError):
        return "Invalid shared configuration link."
    if isinstance(
        error,
        (ShareStoreError, StoredShareConfigurationError, SharedConfigurationError),
    ):
        return "Shared configurations are temporarily unavailable. Try again later."
    return "Shared configurations are temporarily unavailable. Try again later."


def resolve_shared_query_params(query_params) -> tuple[str, str | None] | None:
    """Return the active share query parameter.

    Short ``?share=`` links take precedence over legacy ``?config=`` links when
    both are present.
    """

    def first_value(name: str) -> str | None:
        value = query_params.get(name) if hasattr(query_params, "get") else None
        if isinstance(value, list):
            value = value[0] if value else None
        return value if isinstance(value, str) and value else None

    share_id = first_value("share")
    if share_id:
        return ("share", share_id)
    token = first_value("config")
    if token:
        return ("config", token)
    return None


def _optional_secret(secrets, key: str) -> object | None:
    """Return an optional Streamlit secret without requiring a secrets file."""
    if not hasattr(secrets, "get"):
        return None
    try:
        return secrets.get(key)
    except Exception:
        return None


def get_supabase_share_store_from_secrets(secrets) -> ShareStore | None:
    """Construct a Supabase share store from Streamlit secrets if configured."""
    supabase_url = _optional_secret(secrets, "SUPABASE_URL")
    supabase_key = _optional_secret(secrets, "SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        return None
    return SupabaseShareStore.from_url_and_key(str(supabase_url), str(supabase_key))


def get_streamlit_share_store() -> ShareStore | None:
    """Return the cached production share store, or ``None`` if unconfigured."""
    import streamlit as st

    cache_resource = getattr(st, "cache_resource", lambda **_: lambda func: func)

    @cache_resource(show_spinner=False)
    def cached_store(supabase_url: str, supabase_key: str) -> ShareStore:
        return SupabaseShareStore.from_url_and_key(supabase_url, supabase_key)

    secrets = getattr(st, "secrets", {})
    supabase_url = _optional_secret(secrets, "SUPABASE_URL")
    supabase_key = _optional_secret(secrets, "SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        return None
    try:
        return cached_store(str(supabase_url), str(supabase_key))
    except Exception:
        return None


def load_configuration_from_share_store(
    share_store: ShareStore, share_id: str
) -> SharedConfiguration:
    return share_store.load(share_id)


def load_shared_configuration_from_query(
    *, store_factory=get_streamlit_share_store
) -> None:
    """Apply a shared configuration query token once before widgets are created."""
    import streamlit as st

    query_params = getattr(st, "query_params", {})
    resolved = resolve_shared_query_params(query_params)
    if not resolved:
        return
    kind, value = resolved
    if value is None:
        return
    if kind == "share":
        if getattr(st, "session_state", {}).get(LOADED_SHARE_ID_KEY) == value:
            return
        share_store = store_factory()
        if share_store is None:
            st.error(
                "Shared configurations are temporarily unavailable. Try again later."
            )
            return
        try:
            configuration = load_configuration_from_share_store(share_store, value)
        except Exception as error:
            st.error(share_store_ui_message(error))
            return
        loaded_key = LOADED_SHARE_ID_KEY
    else:
        if (
            getattr(st, "session_state", {}).get(LOADED_SHARED_CONFIG_TOKEN_KEY)
            == value
        ):
            return
        try:
            configuration = deserialize_shared_configuration(value, validate=False)
        except SharedConfigurationError as error:
            st.error(f"Invalid shared configuration link: {error}")
            return
        loaded_key = LOADED_SHARED_CONFIG_TOKEN_KEY

    hydrate_session_state_from_shared_configuration(st.session_state, configuration)
    validation_errors = _validation_errors_for_configuration(configuration)
    if validation_errors:
        st.session_state[INVALID_SHARED_CONFIG_MESSAGE_KEY] = (
            "Shared configuration loaded with invalid fields. Fix the highlighted "
            "fields before running calculations."
        )
    st.session_state[loaded_key] = value
    st.session_state[LOADED_SHARED_CONFIG_MESSAGE_KEY] = True


def save_shared_configuration(
    share_store: ShareStore, configuration: SharedConfiguration
) -> str:
    return share_store.save(configuration)


def _current_shared_configuration() -> SharedConfiguration:
    import streamlit as st

    session_state = getattr(st, "session_state", {})
    scenario = ScenarioConfig(
        target_armor_class=int(
            session_state.get(SCENARIO_WIDGET_KEYS["target_armor_class"], 15)
        ),
        enemy_save_bonus=int(
            session_state.get(SCENARIO_WIDGET_KEYS["enemy_save_bonus"], 3)
        ),
        rounds=int(session_state.get(SCENARIO_WIDGET_KEYS["rounds"], 4)),
        simulations=int(session_state.get(SCENARIO_WIDGET_KEYS["simulations"], 10_000)),
        managed_resources=_managed_resources_from_state(),
    )
    return shared_configuration_from_configs(
        compare_enabled=bool(session_state.get(COMPARE_WIDGET_KEY, False)),
        scenario=scenario,
        seed=int(session_state.get(SCENARIO_WIDGET_KEYS["seed"], 20240721)),
        build_a=_build_from_state("first", "Build A"),
        build_b=_build_from_state("second", "Build B"),
    )


def _current_short_shared_configuration_url(share_store: ShareStore) -> str:
    import streamlit as st

    share_id = save_shared_configuration(share_store, _current_shared_configuration())
    return build_short_share_url(
        getattr(getattr(st, "context", None), "url", ""), share_id
    )


def _legacy_current_shared_configuration_url() -> str:
    import streamlit as st

    token = serialize_shared_configuration(_current_shared_configuration())
    return build_share_url(getattr(getattr(st, "context", None), "url", ""), token)


def _current_shared_configuration_url() -> str:
    """Build the legacy long configuration URL for backwards-compatible tests."""
    return _legacy_current_shared_configuration_url()


def _share_configuration_fingerprint(configuration: SharedConfiguration) -> str:
    return serialize_shared_configuration(configuration)


def _render_share_configuration_button() -> None:
    import streamlit as st

    state = getattr(st, "session_state", {})
    base_data: dict[str, object] = {
        "url": "",
        "creating": False,
        "disabled": False,
        "message": state.pop(SHARE_ERROR_MESSAGE_KEY, ""),
    }

    if validate_configuration_for_ui(_current_shared_configuration()):
        state.pop(GENERATED_SHARE_URL_KEY, None)
        state.pop(GENERATED_SHARE_FINGERPRINT_KEY, None)
        base_data.update(
            {"disabled": True, "message": "Fix field errors before sharing."}
        )
        _mount_unified_share_component(base_data, lambda: None)
        return

    share_store = get_streamlit_share_store()
    if share_store is None:
        state.pop(GENERATED_SHARE_URL_KEY, None)
        state.pop(GENERATED_SHARE_FINGERPRINT_KEY, None)
        base_data.update(
            {
                "disabled": True,
                "message": "Share links are not configured for this deployment.",
            }
        )
        _mount_unified_share_component(base_data, lambda: None)
        caption = getattr(st, "caption", None)
        if caption is not None:
            caption("Share links are not configured for this deployment.")
        return

    try:
        configuration = _current_shared_configuration()
        fingerprint = _share_configuration_fingerprint(configuration)
    except SharedConfigurationError:
        state.pop(GENERATED_SHARE_URL_KEY, None)
        state.pop(GENERATED_SHARE_FINGERPRINT_KEY, None)
        base_data.update(
            {"disabled": True, "message": "Fix field errors before sharing."}
        )
        _mount_unified_share_component(base_data, lambda: None)
        return

    stored_fingerprint = state.get(GENERATED_SHARE_FINGERPRINT_KEY)
    if stored_fingerprint is None and state.get(GENERATED_SHARE_URL_KEY):
        state[GENERATED_SHARE_FINGERPRINT_KEY] = fingerprint
    elif stored_fingerprint != fingerprint:
        state.pop(GENERATED_SHARE_URL_KEY, None)
        state[GENERATED_SHARE_FINGERPRINT_KEY] = fingerprint

    share_url = state.get(GENERATED_SHARE_URL_KEY, "")
    base_data["url"] = share_url

    def create_share() -> None:
        try:
            share_id = save_shared_configuration(share_store, configuration)
            state[GENERATED_SHARE_URL_KEY] = build_short_share_url(
                getattr(getattr(st, "context", None), "url", ""), share_id
            )
            state[GENERATED_SHARE_FINGERPRINT_KEY] = fingerprint
            state.pop(SHARE_ERROR_MESSAGE_KEY, None)
        except (SharedConfigurationError, ShareStoreError):
            logger.exception("Failed to create share link from current configuration.")
            state.pop(GENERATED_SHARE_URL_KEY, None)
            state[SHARE_ERROR_MESSAGE_KEY] = (
                "Unable to create a share link right now. Try again later."
            )

    _mount_unified_share_component(base_data, create_share)
