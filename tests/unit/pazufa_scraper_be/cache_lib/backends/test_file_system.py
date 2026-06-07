from datetime import UTC, datetime
from pathlib import Path
from typing import Self

import pytest

from pazufa_scraper_be.cache_lib.backends.file_system import FileSystemBackend
from pazufa_scraper_be.cache_lib.types import Key, Value


@pytest.fixture
def backend(tmp_path: Path) -> FileSystemBackend:
    """Create a FileSystemBackend with temporary directory."""
    return FileSystemBackend(base_dir=tmp_path)


class TestFileSystemBackendInit:
    """Tests for FileSystemBackend initialization."""

    def test_creates_directory_if_missing(self: Self, tmp_path: Path) -> None:
        """Verify directory is created if it doesn't exist."""
        new_dir = tmp_path / "new_cache_dir"
        FileSystemBackend(base_dir=new_dir)
        assert new_dir.exists()
        assert new_dir.is_dir()

    def test_directory_property(self: Self, backend: FileSystemBackend, tmp_path: Path) -> None:
        """Verify directory property returns correct path."""
        assert backend.directory == tmp_path

    def test_accepts_string_path(self: Self, backend: FileSystemBackend, tmp_path: Path) -> None:
        """Verify string path is accepted and converted."""
        assert backend.directory == tmp_path


class TestFileSystemBackendPaths:
    """Tests for path generation methods."""

    def test_metadata_path_format(self: Self, backend: FileSystemBackend, tmp_path: Path) -> None:
        """Verify metadata path has correct format."""
        metadata_path = backend._get_metadata_path(Key("test_key"))
        assert metadata_path.name == ".test_key.metadata"
        assert metadata_path.parent == tmp_path

    @pytest.mark.parametrize(
        "value_type",
        list(Value),
    )
    def test_file_path_for_value_type(self: Self, backend: FileSystemBackend, tmp_path: Path, value_type: Value) -> None:
        """Verify file path has correct extension per value type."""
        file_path = backend.get_file_path(Key("test_key"), value_type)
        assert file_path.parent == tmp_path

        expected_ext = {Value.TEXT: ".txt", Value.BYTES: ".pdf", Value.DICT: ".json", Value.TIMESTAMP: ".txt"}
        assert file_path.suffix == expected_ext[value_type]


class TestTextValues:
    """End-to-end tests for text operations."""

    def test_set_and_get_text(self: Self, backend: FileSystemBackend) -> None:
        """Verify text can be stored and retrieved."""
        test_value = "Hello, World!"
        backend.set_text(key=Key("text_key"), value=test_value)
        assert backend.get_text(key=Key("text_key")) == test_value

    def test_set_overwrites_existing(self: Self, backend: FileSystemBackend) -> None:
        """Verify set overwrites existing value."""
        backend.set_text(key=Key("overwrite_key"), value="original")
        backend.set_text(key=Key("overwrite_key"), value="updated")
        assert backend.get_text(key=Key("overwrite_key")) == "updated"

    def test_read_nonexistent_raises(self: Self, backend: FileSystemBackend) -> None:
        """Verify reading non-existent key raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            backend.get_text(key=Key("nonexistent"))


class TestBytesValues:
    """End-to-end tests for bytes operations."""

    def test_set_and_get_bytes(self: Self, backend: FileSystemBackend) -> None:
        """Verify bytes can be stored and retrieved."""
        test_value = b"\x00\x01\x02\xff"
        backend.set_bytes(key=Key("bytes_key"), value=test_value)
        assert backend.get_bytes(key=Key("bytes_key")) == test_value

    def test_empty_bytes(self: Self, backend: FileSystemBackend) -> None:
        """Verify empty bytes can be stored."""
        backend.set_bytes(key=Key("empty_bytes"), value=b"")
        assert backend.get_bytes(key=Key("empty_bytes")) == b""


class TestDictValues:
    """End-to-end tests for dict operations."""

    def test_set_and_get_dict(self: Self, backend: FileSystemBackend) -> None:
        """Verify dict can be stored and retrieved."""
        test_value: dict[str, object] = {"key": "value", "number": 42, "nested": {"a": 1}}
        backend.set_dict(key=Key("dict_key"), value=test_value)
        assert backend.get_dict(key=Key("dict_key")) == test_value

    def test_dict_json_format(self: Self, backend: FileSystemBackend) -> None:
        """Verify dict is stored as formatted JSON."""
        backend.set_dict(key=Key("json_key"), value={"formatted": True})
        file_path = backend.get_file_path(Key("json_key"), Value.DICT)
        content = file_path.read_text()
        assert '"formatted": true' in content


class TestTimestampValues:
    """End-to-end tests for timestamp operations."""

    def test_set_and_get_timestamp(self: Self, backend: FileSystemBackend) -> None:
        """Verify timestamp can be stored and retrieved."""
        test_value = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        backend.set_timestamp(key=Key("ts_key"), value=test_value)
        result = backend.get_timestamp(key=Key("ts_key"))
        assert result == test_value


class TestMetadataValues:
    """End-to-end tests for metadata operations."""

    def test_set_and_get_metadata(self: Self, backend: FileSystemBackend) -> None:
        """Verify metadata can be stored and retrieved."""
        backend.set_metadata(key=Key("meta_key"), value_type=Value.TEXT, ttl=5)
        metadata = backend.get_metadata(key=Key("meta_key"))
        assert metadata.key == Key("meta_key")
        assert metadata.value_type == Value.TEXT
        assert metadata.expires_at is not None

    def test_metadata_without_ttl(self: Self, backend: FileSystemBackend) -> None:
        """Verify metadata without TTL has None expires_at."""
        backend.set_metadata(key=Key("no_ttl_key"), value_type=Value.TEXT, ttl=None)
        metadata = backend.get_metadata(key=Key("no_ttl_key"))
        assert metadata.expires_at is None


class TestHasEntry:
    """Tests for has_entry method."""

    def test_returns_true_when_entry_exists(self: Self, backend: FileSystemBackend) -> None:
        """Verify has_entry returns True for existing entry."""
        backend.set_text(key=Key("exists_key"), value="test")
        assert backend.has_entry(key=Key("exists_key")) is True

    def test_returns_false_when_no_entry(self: Self, backend: FileSystemBackend) -> None:
        """Verify has_entry returns False when no entry exists."""
        assert backend.has_entry(key=Key("not_exists_key")) is False


class TestDeleteEntry:
    """Tests for delete_entry method."""

    @pytest.mark.parametrize(
        "value_type",
        list(Value),
    )
    def test_deletes_value_type_files(self: Self, backend: FileSystemBackend, value_type: Value) -> None:
        """Verify delete removes files for each value type."""
        key = Key("delete_key")

        if value_type == Value.TEXT:
            backend.set_text(key=key, value="text")

        elif value_type == Value.BYTES:
            backend.set_bytes(key=key, value=b"bytes")

        elif value_type == Value.DICT:
            backend.set_dict(key=key, value={"dict": True})

        elif value_type == Value.TIMESTAMP:
            backend.set_timestamp(key=key, value=datetime.now(UTC))

        file_path = backend.get_file_path(key=key, value_type=value_type)
        assert file_path.exists()

        backend.delete_entry(key=key)
        assert not file_path.exists()

    def test_delete_nonexistent_is_idempotent(self: Self, backend: FileSystemBackend) -> None:
        """Verify deleting non-existent entry doesn't raise."""
        backend.delete_entry(key=Key("nonexistent"))
