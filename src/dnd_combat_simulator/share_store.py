"""Storage abstractions for short shared-configuration links."""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from typing import Any, Protocol, Self

from dnd_combat_simulator.sharing import (
    SharedConfiguration,
    SharedConfigurationError,
    deserialize_shared_configuration,
    serialize_shared_configuration,
)

DEFAULT_SHARE_ID_BYTES = 9
DEFAULT_COLLISION_RETRIES = 5
DEFAULT_SUPABASE_SHARE_TABLE = "shared_configurations"
_POSTGRES_UNIQUE_VIOLATION_CODE = "23505"
_SHARE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+")


class ShareStoreError(Exception):
    """Base error raised by shared-configuration stores."""


class ShareNotFoundError(ShareStoreError):
    """Raised when a requested shared configuration does not exist."""


class InvalidShareIdError(ShareStoreError):
    """Raised when a share ID is empty or contains unsupported characters."""


class StoredShareConfigurationError(ShareStoreError):
    """Raised when a stored shared-configuration token cannot be restored."""


class ShareStore(Protocol):
    """Storage interface for short shared-configuration links."""

    def save(self, configuration: SharedConfiguration) -> str:
        """Persist a shared configuration and return its share ID."""

    def load(self, share_id: str) -> SharedConfiguration:
        """Restore a shared configuration by share ID."""


def _validate_token_bytes(token_bytes: int) -> None:
    if token_bytes < 1:
        raise ValueError("Share ID token byte count must be positive.")


def _validate_collision_retries(collision_retries: int) -> None:
    if collision_retries < 1:
        raise ValueError("Share ID collision retry count must be positive.")


def _validate_share_id(share_id: str) -> None:
    if not isinstance(share_id, str) or not share_id:
        raise InvalidShareIdError("Share ID is required.")
    if not _SHARE_ID_PATTERN.fullmatch(share_id):
        raise InvalidShareIdError("Share ID must contain only URL-safe characters.")


def _generate_share_id(id_generator: Callable[[int], str], token_bytes: int) -> str:
    share_id = id_generator(token_bytes)
    _validate_share_id(share_id)
    return share_id


def _is_unique_violation(error: BaseException) -> bool:
    return str(getattr(error, "code", "")) == _POSTGRES_UNIQUE_VIOLATION_CODE


def _database_error(
    message: str, error: BaseException, *, sensitive_values: tuple[str, ...] = ()
) -> ShareStoreError:
    error_message = str(error)
    for value in sensitive_values:
        if value:
            error_message = error_message.replace(value, "[redacted]")
    return ShareStoreError(f"{message}: {error_message}")


class InMemoryShareStore:
    """In-memory ``ShareStore`` implementation for saved shared configurations."""

    def __init__(
        self,
        *,
        token_bytes: int = DEFAULT_SHARE_ID_BYTES,
        id_generator: Callable[[int], str] | None = None,
    ) -> None:
        _validate_token_bytes(token_bytes)
        self._token_bytes = token_bytes
        self._id_generator = id_generator or secrets.token_urlsafe
        self._tokens_by_id: dict[str, str] = {}

    def save(self, configuration: SharedConfiguration) -> str:
        """Validate and store ``configuration``, returning a short URL-safe ID."""
        token = serialize_shared_configuration(configuration)
        share_id = self._new_share_id()
        self._tokens_by_id[share_id] = token
        return share_id

    def load(self, share_id: str) -> SharedConfiguration:
        """Load, decode, and validate the configuration stored for ``share_id``."""
        _validate_share_id(share_id)
        try:
            token = self._tokens_by_id[share_id]
        except KeyError as error:
            raise ShareNotFoundError(
                f"Shared configuration not found for ID: {share_id}."
            ) from error
        try:
            return deserialize_shared_configuration(token)
        except SharedConfigurationError as error:
            raise StoredShareConfigurationError(
                f"Stored shared configuration for ID {share_id} is invalid: {error}"
            ) from error

    def _new_share_id(self) -> str:
        while True:
            share_id = _generate_share_id(self._id_generator, self._token_bytes)
            if share_id not in self._tokens_by_id:
                return share_id


class SupabaseShareStore:
    """Supabase-backed ``ShareStore`` for production short configuration URLs."""

    def __init__(
        self,
        client: Any,
        *,
        table_name: str = DEFAULT_SUPABASE_SHARE_TABLE,
        token_bytes: int = DEFAULT_SHARE_ID_BYTES,
        id_generator: Callable[[int], str] | None = None,
        collision_retries: int = DEFAULT_COLLISION_RETRIES,
    ) -> None:
        if client is None:
            raise ValueError("Supabase client is required.")
        if not table_name:
            raise ValueError("Supabase share table name is required.")
        _validate_token_bytes(token_bytes)
        _validate_collision_retries(collision_retries)
        self._client = client
        self._table_name = table_name
        self._token_bytes = token_bytes
        self._id_generator = id_generator or secrets.token_urlsafe
        self._collision_retries = collision_retries

    @classmethod
    def from_url_and_key(
        cls,
        supabase_url: str,
        supabase_key: str,
        **kwargs: Any,
    ) -> Self:
        """Create a store with a Supabase client built from URL and secret key."""
        if not supabase_url:
            raise ValueError("Supabase URL is required.")
        if not supabase_key:
            raise ValueError("Supabase key is required.")
        try:
            from supabase import create_client
        except ImportError as error:
            raise ShareStoreError(
                "Supabase Python dependency is not installed."
            ) from error
        try:
            client = create_client(supabase_url, supabase_key)
        except Exception as error:
            raise _database_error(
                "Failed to create Supabase client",
                error,
                sensitive_values=(supabase_key,),
            ) from error
        return cls(client, **kwargs)

    def save(self, configuration: SharedConfiguration) -> str:
        """Validate and store ``configuration``, returning a short URL-safe ID."""
        token = serialize_shared_configuration(configuration)
        last_collision: BaseException | None = None
        for _ in range(self._collision_retries):
            share_id = _generate_share_id(self._id_generator, self._token_bytes)
            try:
                self._client.table(self._table_name).insert(
                    {"id": share_id, "config_token": token}
                ).execute()
            except Exception as error:
                if _is_unique_violation(error):
                    last_collision = error
                    continue
                raise _database_error(
                    "Failed to save shared configuration", error
                ) from error
            return share_id
        raise ShareStoreError(
            "Failed to save shared configuration after repeated share ID collisions."
        ) from last_collision

    def load(self, share_id: str) -> SharedConfiguration:
        """Load, decode, and validate the configuration stored for ``share_id``."""
        _validate_share_id(share_id)
        try:
            response = (
                self._client.table(self._table_name)
                .select("config_token")
                .eq("id", share_id)
                .limit(1)
                .execute()
            )
        except Exception as error:
            raise _database_error(
                "Failed to load shared configuration", error
            ) from error

        rows = getattr(response, "data", None)
        if rows == []:
            raise ShareNotFoundError(
                f"Shared configuration not found for ID: {share_id}."
            )
        if not isinstance(rows, list) or len(rows) != 1:
            raise ShareStoreError(
                "Supabase returned a malformed shared configuration response."
            )
        row = rows[0]
        if not isinstance(row, dict):
            raise ShareStoreError(
                "Supabase returned a malformed shared configuration row."
            )
        token = row.get("config_token")
        if not isinstance(token, str) or not token:
            raise ShareStoreError(
                "Supabase returned a malformed shared configuration token."
            )
        try:
            return deserialize_shared_configuration(token)
        except SharedConfigurationError as error:
            raise StoredShareConfigurationError(
                f"Stored shared configuration for ID {share_id} is invalid: {error}"
            ) from error
