from datetime import datetime, timedelta
from typing import Any, Self

from .backends.backend import Backend
from .errors import KeyDoesNotExistError, KeyExpiredError, MetadataError, ValueTypeError
from .metadata import Metadata
from .types import Key, Value


def _check_key(key: Any) -> None:
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
        metadata = self._backend._read_metadata(key=key)
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
        self._backend._delete_key(key=key)

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

        metadata = self._backend._read_metadata(key=key)
        return metadata.is_expired()

    def has_entry(self: Self, key: Key) -> bool:
        """Check if an entry exists in the cache.

        Args:
            key: The entry to check.

        Returns:
            True if the entry exists, False otherwise.
        """
        _check_key(key=key)
        return self._backend._has_entry(key=key)

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

        metadata = self.backend._read_metadata(key=key)
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

        return self._backend._read_text(key=key)

    def write_text(self: Self, key: Key, value: str, ttl: timedelta | None = None) -> None:
        """Write a text value to the cache.

        Args:
            key: The entry to write to.
            value: The text value to store.
            ttl: Optional time-to-live for the entry.
        """
        _check_key(key=key)
        _check_value(value=value, expected=str)

        self._backend._write_text(key=key, value=value)
        self._backend._write_metadata(key=key, value_type=Value.TEXT, ttl=ttl)

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

        return self._backend._read_bytes(key=key)

    def write_bytes(self: Self, key: Key, value: bytes, ttl: timedelta | None = None) -> None:
        """Write a bytes value to the cache.

        Args:
            key: The entry to write to.
            value: The bytes value to store.
            ttl: Optional time-to-live for the entry.
        """
        _check_key(key=key)
        _check_value(value=value, expected=bytes)

        self._backend._write_bytes(key=key, value=value)
        self._backend._write_metadata(key=key, value_type=Value.BYTES, ttl=ttl)

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

        return self._backend._read_dict(key=key)

    def write_dict(self: Self, key: Key, value: dict, ttl: timedelta | None = None) -> None:
        """Write a dictionary value to the cache.

        Args:
            key: The entry to write to.
            value: The dictionary value to store.
            ttl: Optional time-to-live for the entry.
        """
        _check_key(key=key)
        _check_value(value=value, expected=dict)

        self._backend._write_dict(key=key, value=value)
        self._backend._write_metadata(key=key, value_type=Value.DICT, ttl=ttl)

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

        return self._backend._read_timestamp(key=key)

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
            raise ValueError("Timestamps must be timezone-aware.")

        self._backend._write_timestamp(key=key, value=value)
        self._backend._write_metadata(key=key, value_type=Value.TIMESTAMP, ttl=ttl)

    # TODO: which tests are required and double check this here.
    # vll einfach zu den high level methods dispatchen, die kuemmern sich ja..
    def __getitem__(self: Self, key: Key) -> Any:
        """Read a value from the cache by key.

        Args:
            key: The cache key.

        Returns:
            The cached value.

        Raises:
            KeyDoesNotExistError: If the entry does not exist.
            KeyExpiredError: If the entry has expired.
        """
        _check_key(key=key)

        self._check_existence(key=key)
        metadata = self._backend._read_metadata(key=key)
        _check_expiry(metadata=metadata)

        # Dispatch to appropriate read method based on stored type
        match metadata.value_type:
            case Value.TEXT:
                return self._backend._read_text(key=key)

            case Value.BYTES:
                return self._backend._read_bytes(key=key)

            case Value.DICT:
                return self._backend._read_dict(key=key)

            case Value.TIMESTAMP:
                return self._backend._read_timestamp(key=key)

    def __setitem__(self: Self, key: Key, value: Any) -> None:
        """Write a value to the cache, auto-detecting its type.

        Args:
            key: The cache key.
            value: The value to store (str, bytes, dict, or datetime).

        Raises:
            TypeError: If the value type is not supported.
        """
        _check_key(key=key)

        match value:
            case str():
                self.write_text(key=key, value=value)

            case bytes():
                self.write_bytes(key=key, value=value)

            case dict():
                self.write_dict(key=key, value=value)

            case datetime():
                self.write_timestamp(key=key, value=value)

            case _:
                msg = f"Unsupported value type: {type(value).__name__}. " + "Supported types: str, bytes, dict, datetime."
                raise TypeError(msg)
