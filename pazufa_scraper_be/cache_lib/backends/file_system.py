import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Self

from pazufa_scraper_be.cache_lib.backends.backend import Backend
from pazufa_scraper_be.cache_lib.metadata import Metadata
from pazufa_scraper_be.cache_lib.types import Key, Value


class FileSystemBackend(Backend):
    """File-system-based cache backend.

    Stores cache entries as individual files in a directory, with metadata
    stored in sidecar files.

    The abstract Backend super class enforces to implement all low-level primitives.
    """

    def __init__(self: Self, base_dir: str | Path) -> None:
        """Initialize the backend with a base directory.

        Args:
            base_dir: Directory path for cache storage; created if missing.
        """
        self._directory = Path(base_dir)
        self._directory.mkdir(parents=True, exist_ok=True)

    @property
    def directory(self: Self) -> Path:
        """The cache directory.

        Returns:
            Path to cache directory.
        """
        return self._directory

    def _get_metadata_path(self: Self, key: Key) -> Path:
        """Return the metadata file path for a key.

        Args:
            key: The entry to check.

        Returns:
            Path to the metadata file.
        """
        return (self.directory / f".{key}").with_suffix(".metadata")

    def get_file_path(self: Self, key: Key, value_type: Value) -> Path:
        """Return the cache file path for a key and value type.

        Args:
            key: Cache entry.
            value_type: Type of the stored value.

        Returns:
            Path to the cache file with the appropriate extension.

        Raises:
            ValueError: If value_type is not supported.
        """
        if value_type == Value.TEXT:
            extension = ".txt"

        elif value_type == Value.BYTES:
            extension = ".pdf"

        elif value_type == Value.DICT:
            extension = ".json"

        elif value_type == Value.TIMESTAMP:
            extension = ".txt"

        else:
            msg = f"Given value_type '{value_type}' is not supported."
            raise ValueError(msg)

        return (self.directory / key).with_suffix(extension)

    def has_entry(self: Self, key: Key) -> bool:
        """Check if a cache entry exists.

        Args:
            key: The entry to check.

        Returns:
            True if any file for the key exists, False otherwise.
        """
        return any(self.get_file_path(key=key, value_type=vt).exists() for vt in Value)

    def read_text(self: Self, key: Key) -> str:
        """Read a text value from cache.

        Args:
            key: The entry to check.

        Returns:
            The stored text value.
        """
        return self.get_file_path(key=key, value_type=Value.TEXT).read_text()

    def write_text(self: Self, key: Key, value: str) -> None:
        """Write a text value to cache.

        Args:
            key: The entry to write to.
            value: Text value to store.
        """
        self.get_file_path(key=key, value_type=Value.TEXT).write_text(data=value)

    def read_bytes(self: Self, key: Key) -> bytes:
        """Read a bytes value from cache.

        Args:
            key: The entry to check.

        Returns:
            The stored bytes value.
        """
        return self.get_file_path(key=key, value_type=Value.BYTES).read_bytes()

    def write_bytes(self: Self, key: Key, value: bytes) -> None:
        """Write a bytes value to cache.

        Args:
            key: The entry to write to.
            value: Bytes value to store.
        """
        self.get_file_path(key=key, value_type=Value.BYTES).write_bytes(data=value)

    def read_timestamp(self: Self, key: Key) -> datetime:
        """Read a timestamp value from cache.

        Args:
            key: The entry to check.

        Returns:
            The stored datetime value.
        """
        timestamp_str = self.get_file_path(key=key, value_type=Value.TIMESTAMP).read_text()
        return datetime.fromisoformat(timestamp_str)

    def write_timestamp(self: Self, key: Key, value: datetime) -> None:
        """Write a timestamp value to cache.

        Args:
            key: The entry to write to.
            value: Datetime value to store.
        """
        self.get_file_path(key=key, value_type=Value.TIMESTAMP).write_text(value.isoformat())

    def read_dict(self: Self, key: Key) -> dict[str, object]:
        """Read a dict value from cache.

        Args:
            key: The entry to check.

        Returns:
            The stored dictionary.
        """
        dict_str = self.get_file_path(key=key, value_type=Value.DICT).read_text()
        return json.loads(dict_str)

    def write_dict(self: Self, key: Key, value: dict[str, object]) -> None:
        """Write a dict value to cache.

        Args:
            key: The entry to write to.
            value: Dictionary to store.
        """
        self.get_file_path(key=key, value_type=Value.DICT).write_text(data=json.dumps(value, indent=2))

    def read_metadata(self: Self, key: Key) -> Metadata:
        """Read metadata for a cache entry.

        Args:
            key: The entry to check.

        Returns:
            The stored metadata.
        """
        metadata_dict = self._get_metadata_path(key=key).read_text()
        return Metadata.model_validate_json(metadata_dict)

    def write_metadata(self: Self, key: Key, value_type: Value, ttl: timedelta | int | None) -> None:
        """Write metadata for a cache entry.

        Args:
            key: The entry to write to.
            value_type: Type of the stored value.
            ttl: Time-to-live for the entry; None to disable expiry.
        """
        metadata = Metadata.new(
            key=key,
            value_type=value_type,
            ttl=ttl,
        )
        self._get_metadata_path(key=key).write_text(metadata.model_dump_json())

    def delete_key(self: Self, key: Key) -> None:
        """Delete all files associated with a cache entry.

        Args:
            key: The entry to delete.
        """
        for vt in Value:
            self.get_file_path(key=key, value_type=vt).unlink(missing_ok=True)

        self._get_metadata_path(key=key).unlink(missing_ok=True)
