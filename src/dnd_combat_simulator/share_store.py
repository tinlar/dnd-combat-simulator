"""Storage abstractions for short shared-configuration links."""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from typing import Protocol

from dnd_combat_simulator.sharing import (
    SharedConfiguration,
    SharedConfigurationError,
    deserialize_shared_configuration,
    serialize_shared_configuration,
)

DEFAULT_SHARE_ID_BYTES = 9
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


class InMemoryShareStore:
    """In-memory ``ShareStore`` implementation for saved shared configurations."""

    def __init__(
        self,
        *,
        token_bytes: int = DEFAULT_SHARE_ID_BYTES,
        id_generator: Callable[[int], str] | None = None,
    ) -> None:
        if token_bytes < 1:
            raise ValueError("Share ID token byte count must be positive.")
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
        self._validate_share_id(share_id)
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
            share_id = self._id_generator(self._token_bytes)
            self._validate_share_id(share_id)
            if share_id not in self._tokens_by_id:
                return share_id

    @staticmethod
    def _validate_share_id(share_id: str) -> None:
        if not isinstance(share_id, str) or not share_id:
            raise InvalidShareIdError("Share ID is required.")
        if not _SHARE_ID_PATTERN.fullmatch(share_id):
            raise InvalidShareIdError("Share ID must contain only URL-safe characters.")
