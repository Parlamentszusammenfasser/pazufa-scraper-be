from datetime import UTC, datetime, timedelta
from typing import Self, cast
from unittest.mock import MagicMock

import pytest

from pazufa_scraper_be.cache_lib import Cache, KeyDoesNotExistError
from pazufa_scraper_be.cache_lib.cache import (
    _check_expiry,
    _check_key,
    _check_value,
    _check_value_type,
)
from pazufa_scraper_be.cache_lib.errors import (
    KeyExpiredError,
    ValueTypeError,
)
from pazufa_scraper_be.cache_lib.types import Key, SupportedValueTypes, Value


class TestHelperCheckKey:
    """Tests for _check_key helper function."""

    def test_string_returns_key(self: Self) -> None:
        """Verify string input is converted to Key."""
        result = _check_key("test_key")
        assert result == Key("test_key")

    def test_key_returns_unchanged(self: Self) -> None:
        """Verify Key input is returned unchanged."""
        key = Key("test_key")
        result = _check_key(key)
        assert result is key

    @pytest.mark.parametrize(
        "key",
        [
            123,
            None,
            b"test",
            datetime.now(UTC),
        ],
    )
    def test_invalid_type_raises(self: Self, key: Key | str) -> None:
        """Verify invalid type raises TypeError."""
        with pytest.raises(TypeError, match="Key has to be of type"):
            _check_key(key=key)


class TestHelperCheckValue:
    """Tests for _check_value helper function."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("test", str),
            (b"test", bytes),
            ({}, dict),
            (datetime.now(UTC), datetime),
        ],
    )
    def test_correct_type_does_not_raise(self: Self, value: SupportedValueTypes, expected: type[SupportedValueTypes]) -> None:
        """Verify correct type doesn't raise."""
        assert _check_value(value=value, expected=expected) is None

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("test", bytes),
            (b"test", str),
            ({}, datetime),
            (datetime.now(UTC), dict),
        ],
    )
    def test_incorrect_type_raises(self: Self, value: SupportedValueTypes, expected: type[SupportedValueTypes]) -> None:
        """Verify incorrect type raises TypeError."""
        with pytest.raises(TypeError, match="Value was expected to be"):
            assert _check_value(value=value, expected=expected) is None


class TestHelperCheckExpiry:
    def test_not_expired_does_not_raise(self: Self) -> None:
        """Verify non-expired metadata doesn't raise."""
        metadata = MagicMock()
        metadata.is_expired.return_value = False
        _check_expiry(metadata)

    def test_expired_raises(self: Self) -> None:
        """Verify expired metadata raises KeyExpiredError."""
        metadata = MagicMock()
        metadata.is_expired.return_value = True
        metadata.key = Key("test_key")
        metadata.expires_at = datetime.now(UTC) - timedelta(hours=1)

        with pytest.raises(KeyExpiredError, match=r"Key '.*' is expired at: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"):
            _check_expiry(metadata)


class TestHelperCheckValueType:
    """Tests for _check_value_type helper function."""

    @pytest.mark.parametrize(
        "value_type",
        list(Value),
    )
    def test_matching_type_does_not_raise(self: Self, value_type: Value) -> None:
        """Verify matching value type doesn't raise."""
        metadata = MagicMock()
        metadata.value_type = value_type
        _check_value_type(metadata, value_type)

    @pytest.mark.parametrize(
        ("value_type", "other_type"),
        [(value_type, other_type) for value_type, other_type in zip(Value, reversed(Value), strict=True)],
    )
    def test_mismatching_type_raises(self: Self, value_type: Value, other_type: Value) -> None:
        """Verify mismatching value type raises ValueTypeError."""
        metadata = MagicMock()
        metadata.value_type = value_type

        with pytest.raises(ValueTypeError, match=rf"Stored value is '{value_type.value}'"):
            _check_value_type(metadata, expected_value_type=other_type)


class TestCacheDispatchesToBackend:
    """Tests that Cache dispatches to Backend."""

    @pytest.fixture
    def cache(self: Self) -> Cache:
        """Create a Cache instance with mock backend."""
        backend = MagicMock()
        backend._store = {}
        backend._metadata_store = {}

        mock_metadata = MagicMock()
        mock_metadata.is_expired.return_value = False
        backend.get_metadata.return_value = mock_metadata

        return Cache(backend=backend)

    def test_get_text(self: Self, cache: Cache) -> None:
        value_type = Value.TEXT
        cache.backend.get_metadata.return_value.value_type = value_type

        cache.get_text("test_key")
        cache.backend.get_text.assert_called_once_with(key=Key("test_key"))

    def test_get_bytes(self: Self, cache: Cache) -> None:
        value_type = Value.BYTES
        cache.backend.get_metadata.return_value.value_type = value_type

        cache.get_bytes("test_key")
        cache.backend.get_bytes.assert_called_once_with(key=Key("test_key"))

    def test_get_timestamp(self: Self, cache: Cache) -> None:
        value_type = Value.TIMESTAMP
        cache.backend.get_metadata.return_value.value_type = value_type

        cache.get_timestamp("test_key")
        cache.backend.get_timestamp.assert_called_once_with(key=Key("test_key"))

    def test_get_dict(self: Self, cache: Cache) -> None:
        value_type = Value.DICT
        cache.backend.get_metadata.return_value.value_type = value_type

        cache.get_dict("test_key")
        cache.backend.get_dict.assert_called_once_with(key=Key("test_key"))

    def test_get_metadata(self: Self, cache: Cache) -> None:
        cache.backend.get_metadata.return_value.value_type = Value.DICT
        cache.backend.get_metadata.return_value.key = Key("test_key")

        cache.get_metadata("test_key")
        cache.backend.get_metadata.assert_called_once_with(key=Key("test_key"))

    @pytest.mark.parametrize(
        "ttl",
        [None, 5, timedelta(hours=5)],
    )
    def test_set_text(self: Self, cache: Cache, ttl: timedelta | int | None) -> None:
        key = Key("test_key")
        value = "test_value"
        value_type = Value.TEXT

        return_value = cache.set_text(key=key, value=value, ttl=ttl)
        cache.backend.set_text.assert_called_once_with(key=key, value=value)
        cache.backend.set_metadata.assert_called_once_with(key=key, value_type=value_type, ttl=ttl)
        assert return_value is None

    @pytest.mark.parametrize(
        "ttl",
        [None, 5, timedelta(hours=5)],
    )
    def test_set_bytes(self: Self, cache: Cache, ttl: timedelta | int | None) -> None:
        key = Key("test_key")
        value = b"test_value"
        value_type = Value.BYTES

        return_value = cache.set_bytes(key=key, value=value, ttl=ttl)
        cache.backend.set_bytes.assert_called_once_with(key=key, value=value)
        cache.backend.set_metadata.assert_called_once_with(key=key, value_type=value_type, ttl=ttl)
        assert return_value is None

    @pytest.mark.parametrize(
        "ttl",
        [None, 5, timedelta(hours=5)],
    )
    def test_set_dict(self: Self, cache: Cache, ttl: timedelta | int | None) -> None:
        key = Key("test_key")
        value = {}
        value_type = Value.DICT

        return_value = cache.set_dict(key=key, value=value, ttl=ttl)
        cache.backend.set_dict.assert_called_once_with(key=key, value=value)
        cache.backend.set_metadata.assert_called_once_with(key=key, value_type=value_type, ttl=ttl)
        assert return_value is None

    @pytest.mark.parametrize(
        "ttl",
        [None, 5, timedelta(hours=5)],
    )
    def test_set_timestamp(self: Self, cache: Cache, ttl: timedelta | int | None) -> None:
        key = Key("test_key")
        value = datetime.now(UTC)
        value_type = Value.TIMESTAMP

        return_value = cache.set_timestamp(key=key, value=value, ttl=ttl)
        cache.backend.set_timestamp.assert_called_once_with(key=key, value=value)
        cache.backend.set_metadata.assert_called_once_with(key=key, value_type=value_type, ttl=ttl)
        assert return_value is None

    def test_delete_entry(self: Self, cache: Cache) -> None:
        return_value = cache.delete_entry("test_key")
        cache.backend.delete_entry.assert_called_once_with(key=Key("test_key"))
        assert return_value is None

    def test_has_entry(self: Self, cache: Cache) -> None:
        cache.has_entry("test_key")
        cache.backend.has_entry.assert_called_once_with(key=Key("test_key"))

    def test_is_expired(self: Self, cache: Cache) -> None:
        cache.is_expired("test_key")
        cache.backend.get_metadata.assert_called_once_with(key=Key("test_key"))


class TestCacheCheckExistence:
    """Tests for _check_existence method."""

    @pytest.fixture
    def cache(self: Self) -> Cache:
        """Create a Cache instance with mock backend."""
        backend = MagicMock()
        backend.has_entry.return_value = True
        return Cache(backend=backend)

    def test_entry_exists_does_not_raise(self: Self, cache: Cache) -> None:
        """Verify existing entry doesn't raise."""
        cache._check_existence("test_key")

    def test_entry_does_not_exist_raises(self: Self, cache: Cache) -> None:
        """Verify non-existent entry raises KeyDoesNotExistError."""
        cache.backend.has_entry.return_value = False
        with pytest.raises(KeyDoesNotExistError, match=r"Key 'test_key' does not exist."):
            cache._check_existence("test_key")

    @pytest.mark.parametrize(
        "key",
        [
            "test_key",
            Key("test_key"),
        ],
    )
    def test_key_handling(self: Self, cache: Cache, key: Key | str) -> None:
        """Verify key is converted to Key before backend call."""
        cache._check_existence(key)
        cache.backend.has_entry.assert_called_once_with(key=Key("test_key"))


class TestCacheGetChecks:
    """Tests for _get_checks method."""

    @pytest.fixture
    def cache(self: Self) -> Cache:
        """Create a Cache instance with mock backend and valid metadata."""
        backend = MagicMock()
        mock_metadata = MagicMock()
        mock_metadata.is_expired.return_value = False
        mock_metadata.value_type = Value.TEXT
        backend.has_entry.return_value = True
        backend.get_metadata.return_value = mock_metadata
        return Cache(backend=backend)

    def test_valid_passes_all_checks(self: Self, cache: Cache) -> None:
        """Verify valid input passes all checks without raising."""
        cache._get_checks("test_key", expected_value_type=Value.TEXT)

    def test_invalid_key_type_raises(self: Self, cache: Cache) -> None:
        """Verify invalid key type raises TypeError."""
        with pytest.raises(TypeError, match="Key has to be of type"):
            cache._get_checks(cast("Key | str", 123), expected_value_type=Value.TEXT)

    def test_entry_exists_passes(self: Self, cache: Cache) -> None:
        """Verify existing entry passes check without raising."""
        cache.backend.has_entry.return_value = True
        cache._get_checks("test_key", expected_value_type=Value.TEXT)

    def test_nonexistent_entry_raises(self: Self, cache: Cache) -> None:
        """Verify non-existent entry raises KeyDoesNotExistError."""
        cache.backend.has_entry.return_value = False
        with pytest.raises(KeyDoesNotExistError, match=r"Key 'test_key' does not exist."):
            cache._get_checks("test_key", expected_value_type=Value.TEXT)

    @pytest.mark.parametrize(
        ("is_expired", "ignore_expiry", "raises"),
        [
            (True, False, True),
            (True, True, False),
            (False, False, False),
            (False, True, False),
        ],
    )
    def test_expiry_behavior(
        self: Self,
        cache: Cache,
        is_expired: bool,
        ignore_expiry: bool,
        raises: bool,
    ) -> None:
        """Verify expiry handling based on configuration."""
        cache.backend.get_metadata.return_value.is_expired.return_value = is_expired
        cache.backend.get_metadata.return_value.key = Key("test_key")
        cache.backend.get_metadata.return_value.expires_at = datetime.now(UTC) - timedelta(hours=1)
        if raises:
            with pytest.raises(KeyExpiredError, match=r"Key 'test_key' is expired at:"):
                cache._get_checks("test_key", expected_value_type=Value.TEXT, ignore_expiry=ignore_expiry)
        else:
            cache._get_checks("test_key", expected_value_type=Value.TEXT, ignore_expiry=ignore_expiry)

    @pytest.mark.parametrize(
        ("stored_type", "expected_type", "raises"),
        [
            (Value.TEXT, Value.TEXT, False),
            (Value.BYTES, Value.TEXT, True),
            (Value.DICT, Value.DICT, False),
            (Value.TIMESTAMP, Value.BYTES, True),
        ],
    )
    def test_value_type_check(
        self: Self,
        cache: Cache,
        stored_type: Value,
        expected_type: Value,
        raises: bool,
    ) -> None:
        """Verify value type validation."""
        cache.backend.get_metadata.return_value.value_type = stored_type
        if raises:
            with pytest.raises(ValueTypeError, match=rf"Stored value is '{stored_type.value}'"):
                cache._get_checks("test_key", expected_value_type=expected_type)
        else:
            cache._get_checks("test_key", expected_value_type=expected_type)


class TestCacheDunderMethods:
    """Tests for dunder methods __getitem__, __setitem__, __contains__."""

    @pytest.fixture
    def cache(self: Self) -> Cache:
        """Create a Cache instance with mock backend."""
        backend = MagicMock()
        mock_metadata = MagicMock()
        mock_metadata.is_expired.return_value = False
        mock_metadata.key = Key("test_key")
        backend.has_entry.return_value = True
        backend.get_metadata.return_value = mock_metadata
        return Cache(backend=backend)

    @pytest.mark.parametrize(
        "value_type",
        list(Value),
    )
    def test_getitem_returns_correct_type(self: Self, cache: Cache, value_type: Value) -> None:
        """Verify __getitem__ dispatches to correct getter based on value type."""
        cache.backend.get_metadata.return_value.value_type = value_type

        cache["test_key"]
        match value_type:
            case Value.TEXT:
                cache.backend.get_text.assert_called_once_with(key=Key("test_key"))

            case Value.BYTES:
                cache.backend.get_bytes.assert_called_once_with(key=Key("test_key"))

            case Value.DICT:
                cache.backend.get_dict.assert_called_once_with(key=Key("test_key"))

            case Value.TIMESTAMP:
                cache.backend.get_timestamp.assert_called_once_with(key=Key("test_key"))

    @pytest.mark.parametrize(
        "value",
        ["test", b"bytes", {"key": "value"}, datetime.now(UTC)],
    )
    def test_setitem_auto_detects_type(self: Self, cache: Cache, value: SupportedValueTypes) -> None:
        """Verify __setitem__ auto-detects value type and calls correct setter."""
        cache["test_key"] = value
        match value:
            case str():
                cache.backend.set_text.assert_called_once_with(key=Key("test_key"), value=value)

            case bytes():
                cache.backend.set_bytes.assert_called_once_with(key=Key("test_key"), value=value)

            case dict():
                cache.backend.set_dict.assert_called_once_with(key=Key("test_key"), value=value)

            case datetime():
                cache.backend.set_timestamp.assert_called_once_with(key=Key("test_key"), value=value)

    @pytest.mark.parametrize(
        "unsupported_value",
        [123, None, [], set()],
    )
    def test_setitem_unsupported_type_raises(self: Self, cache: Cache, unsupported_value: object) -> None:
        """Verify __setitem__ raises TypeError for unsupported type."""
        with pytest.raises(TypeError, match="Unsupported value type"):
            cache["test_key"] = unsupported_value  # ty: ignore[invalid-assignment]

    def test_contains_returns_true(self: Self, cache: Cache) -> None:
        """Verify __contains__ returns True when entry exists."""
        cache.backend.has_entry.return_value = True
        assert ("test_key" in cache) is True
        cache.backend.has_entry.assert_called_once_with(key=Key("test_key"))

    def test_contains_returns_false(self: Self, cache: Cache) -> None:
        """Verify __contains__ returns False when entry doesn't exist."""
        cache.backend.has_entry.return_value = False
        assert ("test_key" in cache) is False
        cache.backend.has_entry.assert_called_once_with(key=Key("test_key"))
