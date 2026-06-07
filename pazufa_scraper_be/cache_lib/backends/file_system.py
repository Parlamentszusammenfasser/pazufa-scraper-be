import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Self

from ..backends.backend import Backend
from ..metadata import Metadata
from ..types import Key, Value


class FileSystemBackend(Backend):
    """File-system-based cache backend.

    Stores cache entries as individual files in a directory, with metadata
    stored in sidecar files.

    The abstract Backend superclass enforces to implement all low-level primitives.
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
        """Return the metadata file path for a key."""
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
            raise ValueError(f"Given value_type '{value_type}' is not supported.")

        return (self.directory / key).with_suffix(extension)

    def _has_entry(self: Self, key: Key) -> bool:
        return any(self.get_file_path(key=key, value_type=vt).exists() for vt in Value)

    def _read_text(self: Self, key: Key) -> str:
        return self.get_file_path(key=key, value_type=Value.TEXT).read_text()

    def _write_text(self: Self, key: Key, value: str) -> None:
        self.get_file_path(key=key, value_type=Value.TEXT).write_text(data=value)

    def _read_bytes(self: Self, key: Key) -> bytes:
        return self.get_file_path(key=key, value_type=Value.BYTES).read_bytes()

    def _write_bytes(self: Self, key: Key, value: bytes) -> None:
        self.get_file_path(key=key, value_type=Value.BYTES).write_bytes(data=value)

    def _read_timestamp(self: Self, key: Key) -> datetime:
        timestamp_str = self.get_file_path(key=key, value_type=Value.TIMESTAMP).read_text()
        return datetime.fromisoformat(timestamp_str)

    def _write_timestamp(self: Self, key: Key, value: datetime) -> None:
        self.get_file_path(key=key, value_type=Value.TIMESTAMP).write_text(value.isoformat())

    def _read_dict(self: Self, key: Key) -> dict[str, object]:
        dict_str = self.get_file_path(key=key, value_type=Value.DICT).read_text()
        data = json.loads(dict_str)
        return data

    def _write_dict(self: Self, key: Key, value: dict[str, object]) -> None:
        self.get_file_path(key=key, value_type=Value.DICT).write_text(data=json.dumps(value, indent=2))

    def _read_metadata(self: Self, key: Key) -> Metadata:
        metadata_dict = self._get_metadata_path(key=key).read_text()
        metadata = Metadata.model_validate_json(metadata_dict)
        return metadata

    def _write_metadata(self: Self, key: Key, value_type: Value, ttl: timedelta | int | None) -> None:
        metadata = Metadata.new(
            key=key,
            value_type=value_type,
            ttl=ttl,
        )
        self._get_metadata_path(key=key).write_text(metadata.model_dump_json())

    def _delete_key(self: Self, key: Key) -> None:
        for vt in Value:
            self.get_file_path(key=key, value_type=vt).unlink(missing_ok=True)

        self._get_metadata_path(key=key).unlink(missing_ok=True)
