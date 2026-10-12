from datetime import datetime, timedelta
from typing import Self

from .backends.backend import Backend
from .errors import KeyDoesNotExistError, KeyExpiredError, MetadataError, ValueTypeError
from .metadata import Metadata
from .types import Key, SupportedValueTypes, Value


def _check_key(key: Key | str) -> Key:
    if not isinstance(key, (Key, str)):
        msg = f"Key has to be of type 'Key' or 'str', it was '{type(key)}'"
        raise TypeError(msg)

    return key if isinstance(key, Key) else Key(key)


def _check_value(value: SupportedValueTypes, expected: type[SupportedValueTypes]) -> None:
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

    def _check_existence(self: Self, key: Key | str) -> None:
        """Check if a key exists in the cache and raise an error if not."""
        if not self.has_entry(key=key):
            msg = f"Key '{key}' does not exist."
            raise KeyDoesNotExistError(msg)

    def _get_checks(
        self: Self,
        key: Key | str,
        expected_value_type: Value,
        *,
        ignore_expiry: bool = False,
    ) -> None:
        """Run appropriate validation checks before a read operation."""
        key = _check_key(key=key)
        self._check_existence(key=key)
        metadata = self._backend.get_metadata(key=key)

        if not ignore_expiry:
            _check_expiry(metadata=metadata)

        _check_value_type(metadata, expected_value_type=expected_value_type)

    # Public API

    def delete_entry(self: Self, key: Key | str) -> None:
        """Delete an entry from the cache.

        This method is idempotent and can repeated multiple times.
        If this methods returns, the entry will be deleted.

        Args:
            key: The entry to delete.
        """
        key = _check_key(key=key)
        self._backend.delete_entry(key=key)

    def is_expired(self: Self, key: Key | str) -> bool:
        """Check if an entry has expired.

        Args:
            key: The entry to check.

        Returns:
            True if a entry is expired, False otherwise.
        """
        key = _check_key(key=key)
        self._check_existence(key=key)

        metadata = self._backend.get_metadata(key=key)
        return metadata.is_expired()

    def has_entry(self: Self, key: Key | str) -> bool:
        """Check if an entry exists in the cache.

        Args:
            key: The entry to check.

        Returns:
            True if the entry exists, False otherwise.
        """
        key = _check_key(key=key)
        return self._backend.has_entry(key=key)

    def get_metadata(self: Self, key: Key | str) -> Metadata:
        """Read metadata for entry.

        Args:
            key: The entry to read.

        Returns:
            Metadata for entry.
        """
        key = _check_key(key=key)
        self._check_existence(key=key)

        metadata = self._backend.get_metadata(key=key)
        if metadata.key != key:
            msg = f"Key '{key}' does not fit the metadata key '{metadata.key}'."
            raise MetadataError(msg)

        return metadata

    def get_text(
        self: Self,
        key: Key | str,
        *,
        ignore_expiry: bool = False,
    ) -> str:
        """Read a text value from the cache.

        Args:
            key: The entry to read.
            ignore_expiry: Flag to ignore expiry check. Allows to read expired value. Optional.

        Returns:
            The stored text value.
        """
        key = _check_key(key=key)
        self._get_checks(key=key, expected_value_type=Value.TEXT, ignore_expiry=ignore_expiry)

        return self._backend.get_text(key=key)

    def set_text(self: Self, key: Key | str, value: str, ttl: timedelta | int | None = None) -> None:
        """Write a text value to the cache.

        Args:
            key: The entry to write to.
            value: The text value to store.
            ttl: Optional time-to-live (in days if int) for the entry.
        """
        key = _check_key(key=key)
        _check_value(value=value, expected=str)

        self._backend.set_text(key=key, value=value)
        self._backend.set_metadata(key=key, value_type=Value.TEXT, ttl=ttl)

    def get_bytes(
        self: Self,
        key: Key | str,
        *,
        ignore_expiry: bool = False,
    ) -> bytes:
        """Read a bytes value from the cache.

        Args:
            key: The entry to read.
            ignore_expiry: Flag to ignore expiry check. Allows to read expired value. Optional.

        Returns:
            The stored bytes value.
        """
        key = _check_key(key=key)
        self._get_checks(key=key, expected_value_type=Value.BYTES, ignore_expiry=ignore_expiry)

        return self._backend.get_bytes(key=key)

    def set_bytes(self: Self, key: Key | str, value: bytes, ttl: timedelta | int | None = None) -> None:
        """Write a bytes value to the cache.

        Args:
            key: The entry to write to.
            value: The bytes value to store.
            ttl: Optional time-to-live (in days if int) for the entry.
        """
        key = _check_key(key=key)
        _check_value(value=value, expected=bytes)

        self._backend.set_bytes(key=key, value=value)
        self._backend.set_metadata(key=key, value_type=Value.BYTES, ttl=ttl)

    def get_dict(
        self: Self,
        key: Key | str,
        *,
        ignore_expiry: bool = False,
    ) -> dict:
        """Read a dictionary value from the cache.

        Args:
            key: The entry to read.
            ignore_expiry: Flag to ignore expiry check. Allows to read expired value. Optional.

        Returns:
            The stored dictionary value.
        """
        key = _check_key(key=key)
        self._get_checks(key=key, expected_value_type=Value.DICT, ignore_expiry=ignore_expiry)

        return self._backend.get_dict(key=key)

    def set_dict(self: Self, key: Key | str, value: dict, ttl: timedelta | int | None = None) -> None:
        """Write a dictionary value to the cache.

        Args:
            key: The entry to write to.
            value: The dictionary value to store.
            ttl: Optional time-to-live (in days if int) for the entry.
        """
        key = _check_key(key=key)
        _check_value(value=value, expected=dict)

        self._backend.set_dict(key=key, value=value)
        self._backend.set_metadata(key=key, value_type=Value.DICT, ttl=ttl)

    def get_timestamp(
        self: Self,
        key: Key | str,
        *,
        ignore_expiry: bool = False,
    ) -> datetime:
        """Read a timestamp value from the cache.

        Args:
            key: The entry to read.
            ignore_expiry: Flag to ignore expiry check. Allows to read expired value. Optional.

        Returns:
            The stored timestamp value.
        """
        key = _check_key(key=key)
        self._get_checks(key=key, expected_value_type=Value.TIMESTAMP, ignore_expiry=ignore_expiry)

        return self._backend.get_timestamp(key=key)

    def set_timestamp(self: Self, key: Key | str, value: datetime, ttl: timedelta | int | None = None) -> None:
        """Write a timestamp value to the cache.

        Args:
            key: The entry to write to.
            value: The timezone-aware datetime to store.
            ttl: Optional time-to-live (in days if int) for the entry.
        """
        key = _check_key(key=key)
        _check_value(value=value, expected=datetime)

        if value.tzinfo is None:
            msg = "Timestamps must be timezone-aware."
            raise ValueError(msg)

        self._backend.set_timestamp(key=key, value=value)
        self._backend.set_metadata(key=key, value_type=Value.TIMESTAMP, ttl=ttl)

    def __getitem__(self: Self, key: Key | str) -> SupportedValueTypes:
        """Read a value from the cache by key.

        Args:
            key: The cache key.

        Returns:
            The cached value.
        """
        metadata = self.get_metadata(key=key)

        match metadata.value_type:
            case Value.TEXT:
                return self.get_text(key=key)

            case Value.BYTES:
                return self.get_bytes(key=key)

            case Value.DICT:
                return self.get_dict(key=key)

            case Value.TIMESTAMP:
                return self.get_timestamp(key=key)

    def __setitem__(self: Self, key: Key | str, value: SupportedValueTypes) -> None:
        """Write a value to the cache, auto-detecting its type.

        Args:
            key: The cache key.
            value: The value to store (str, bytes, dict, or datetime).
        """
        match value:
            case str():
                self.set_text(key=key, value=value)

            case bytes():
                self.set_bytes(key=key, value=value)

            case dict():
                self.set_dict(key=key, value=value)

            case datetime():
                self.set_timestamp(key=key, value=value)

            case _:
                msg = f"Unsupported value type: {type(value).__name__}. Supported types: {SupportedValueTypes.__value__}."
                raise TypeError(msg)

    def __contains__(self: Self, key: Key | str) -> bool:
        """Check if an entry exists in the cache.

        Args:
            key: The entry to check.

        Returns:
            True if the entry exists, False otherwise.
        """
        return self.has_entry(key=key)
