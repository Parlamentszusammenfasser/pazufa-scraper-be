from datetime import datetime, timedelta
from typing import Any, Self

from .backends.backend import Backend
from .errors import KeyDoesNotExistError, KeyExpiredError, MetadataError, ValueTypeError
from .metadata import Metadata
from .types import Key, Value


def _check_key(key: Any) -> None:  # noqa: ANN401
    if not isinstance(key, Key):
        msg = f"Key has to be of type 'Key', it was '{type(key)}'"
        raise TypeError(msg)


def _check_value(value: object, expected: type[str | bytes | dict | datetime]) -> None:
    if not isinstance(value, expected):
        msg = f"Value was expected to be '{expected}' but got '{type(value)}'."
        raise TypeError(msg)


def _check_expiry(metadata: Metadata) -> None:
    """Check if a metadata entry has expired and raise an error if so."""
    if metadata.is_expired():
        msg = f"Key '{metadata.key}' is expired at: {metadata.expires_at}."
        raise KeyExpiredError(msg)


def _check_value_type(metadata: Metadata, expected_value_type: Value) -> None:
    """Check if stored value type matches expected type and raise an error if not."""
    if metadata.value_type != expected_value_type:
        msg = f"Stored value is '{metadata.value_type.value}'," + f" expected '{expected_value_type.value}'."
        raise ValueTypeError(msg)


class Cache[T: Backend]:
    """Generic cache backed by a pluggable storage implementation."""

    def __init__(self: Self, backend: T) -> None:
        """Initializes the cache with the given backend.

        Args:
            backend: The storage backend to use.
        """
        self._backend = backend

    @property
    def backend(self: Self) -> T:
        """The cache backend.

        Returns:
            The storage backend instance.
        """
        return self._backend

    def _check_existence(self: Self, key: Key) -> None:
        """Check if a key exists in the cache and raise an error if not."""
        if not self.has_entry(key=key):
            msg = f"Key '{key}' does not exist."
            raise KeyDoesNotExistError(msg)

    def _read_checks(self: Self, key: Key, expected_value_type: Value) -> None:
        """Run appropriate validation checks before a read operation."""
        self._check_existence(key=key)
        metadata = self._backend.read_metadata(key=key)
        _check_expiry(metadata=metadata)
        _check_value_type(metadata, expected_value_type=expected_value_type)

    # Public API

    def delete_entry(self: Self, key: Key) -> None:
        """Delete an entry from the cache.

        This method is idempotent and can repeated multiple times.
        If this methods returns, the entry will be deleted.

        Args:
            key: The entry to delete.
        """
        _check_key(key=key)
        self._backend.delete_key(key=key)

    def is_expired(self: Self, key: Key) -> bool:
        """Check if an entry has expired.

        Args:
            key: The entry to check.

        Returns:
            True if a entry is expired, False otherwise.

        Raises:
            KeyDoesNotExistError: If the entry does not exist.
        """
        _check_key(key=key)
        self._check_existence(key=key)

        metadata = self._backend.read_metadata(key=key)
        return metadata.is_expired()

    def has_entry(self: Self, key: Key) -> bool:
        """Check if an entry exists in the cache.

        Args:
            key: The entry to check.

        Returns:
            True if the entry exists, False otherwise.
        """
        _check_key(key=key)
        return self._backend.has_entry(key=key)

    def read_metadata(self: Self, key: Key) -> Metadata:
        """Read metadata for entry.

        Args:
            key: The entry to read.

        Returns:
            Metadata for entry.

        Raises:
            MetadataError: If stored key in metadata does not fit given key.
        """
        _check_key(key=key)
        self._check_existence(key=key)

        metadata = self.backend.read_metadata(key=key)
        if metadata.key != key:
            msg = f"Key '{key}' does not fit the metadata key '{metadata.key}'."
            raise MetadataError(msg)

        return metadata

    def read_text(self: Self, key: Key) -> str:
        """Read a text value from the cache.

        Args:
            key: The entry to read.

        Returns:
            The stored text value.

        Raises:
            KeyDoesNotExistError: If the entry does not exist.
            KeyExpiredError: If the entry has expired.
            ValueTypeError: If the stored value is not text.
        """
        _check_key(key=key)
        self._read_checks(key=key, expected_value_type=Value.TEXT)

        return self._backend.read_text(key=key)

    def write_text(self: Self, key: Key, value: str, ttl: timedelta | None = None) -> None:
        """Write a text value to the cache.

        Args:
            key: The entry to write to.
            value: The text value to store.
            ttl: Optional time-to-live for the entry.
        """
        _check_key(key=key)
        _check_value(value=value, expected=str)

        self._backend.write_text(key=key, value=value)
        self._backend.write_metadata(key=key, value_type=Value.TEXT, ttl=ttl)

    def read_bytes(self: Self, key: Key) -> bytes:
        """Read a bytes value from the cache.

        Args:
            key: The entry to read.

        Returns:
            The stored bytes value.

        Raises:
            KeyDoesNotExistError: If the entry does not exist.
            KeyExpiredError: If the entry has expired.
            ValueTypeError: If the stored value is not bytes.
        """
        _check_key(key=key)
        self._read_checks(key=key, expected_value_type=Value.BYTES)

        return self._backend.read_bytes(key=key)

    def write_bytes(self: Self, key: Key, value: bytes, ttl: timedelta | None = None) -> None:
        """Write a bytes value to the cache.

        Args:
            key: The entry to write to.
            value: The bytes value to store.
            ttl: Optional time-to-live for the entry.
        """
        _check_key(key=key)
        _check_value(value=value, expected=bytes)

        self._backend.write_bytes(key=key, value=value)
        self._backend.write_metadata(key=key, value_type=Value.BYTES, ttl=ttl)

    def read_dict(self: Self, key: Key) -> dict:
        """Read a dictionary value from the cache.

        Args:
            key: The entry to read.

        Returns:
            The stored dictionary value.

        Raises:
            KeyDoesNotExistError: If the entry does not exist.
            KeyExpiredError: If the entry has expired.
            ValueTypeError: If the stored value is not a dict.
        """
        _check_key(key=key)
        self._read_checks(key=key, expected_value_type=Value.DICT)

        return self._backend.read_dict(key=key)

    def write_dict(self: Self, key: Key, value: dict, ttl: timedelta | None = None) -> None:
        """Write a dictionary value to the cache.

        Args:
            key: The entry to write to.
            value: The dictionary value to store.
            ttl: Optional time-to-live for the entry.
        """
        _check_key(key=key)
        _check_value(value=value, expected=dict)

        self._backend.write_dict(key=key, value=value)
        self._backend.write_metadata(key=key, value_type=Value.DICT, ttl=ttl)

    def read_timestamp(self: Self, key: Key) -> datetime:
        """Read a timestamp value from the cache.

        Args:
            key: The entry to read.

        Returns:
            The stored timestamp value.

        Raises:
            KeyDoesNotExistError: If the entry does not exist.
            KeyExpiredError: If the entry has expired.
            ValueTypeError: If the stored value is not a timestamp.
        """
        _check_key(key=key)
        self._read_checks(key=key, expected_value_type=Value.TIMESTAMP)

        return self._backend.read_timestamp(key=key)

    def write_timestamp(self: Self, key: Key, value: datetime, ttl: timedelta | None = None) -> None:
        """Write a timestamp value to the cache.

        Args:
            key: The entry to write to.
            value: The timezone-aware datetime to store.
            ttl: Optional time-to-live for the entry.

        Raises:
            ValueError: If the timestamp is not timezone-aware.
        """
        _check_key(key=key)
        _check_value(value=value, expected=datetime)

        if value.tzinfo is None:
            msg = "Timestamps must be timezone-aware."
            raise ValueError(msg)

        self._backend.write_timestamp(key=key, value=value)
        self._backend.write_metadata(key=key, value_type=Value.TIMESTAMP, ttl=ttl)
