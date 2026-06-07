from datetime import UTC, datetime, timedelta
from typing import Self, cast

import pytest
from pydantic import ValidationError

from pazufa_scraper_be.cache_lib.errors import MetadataError
from pazufa_scraper_be.cache_lib.metadata import Metadata, _compute_expires_at
from pazufa_scraper_be.cache_lib.types import Key, Value


class TestComputeExpiresAt:
    """Tests for _compute_expires_at helper function."""

    @pytest.mark.parametrize(
        ("ttl", "expected_is_none"),
        [
            (timedelta(hours=5), False),
            (timedelta(days=1), False),
            (5, False),
            (1, False),
            (None, True),
        ],
    )
    def test_valid_ttl_returns_expected(self: Self, ttl: timedelta | int | None, expected_is_none: bool) -> None:
        """Verify valid TTL values return expected result."""
        result = _compute_expires_at(ttl)
        if expected_is_none:
            assert result is None
        else:
            assert result is not None
            assert isinstance(result, datetime)
            assert result > datetime.now(UTC)

    @pytest.mark.parametrize(
        ("ttl", "expected_msg"),
        [
            (timedelta(0), r"TTL must be positive."),
            (timedelta(hours=-1), r"TTL must be positive."),
            ("string", r"TTL must be timedelta, int, or None"),
        ],
    )
    def test_invalid_ttl_raises(self: Self, ttl: timedelta | int | None, expected_msg: str) -> None:
        """Verify invalid TTL values raise ValueError with appropriate message."""
        with pytest.raises(ValueError, match=expected_msg):
            _compute_expires_at(ttl)


class TestMetadataNew:
    """Tests for Metadata.new() factory method."""

    def test_with_ttl_sets_expires_at(self: Self) -> None:
        """Verify TTL sets expires_at to a future datetime."""
        metadata = Metadata.new(key=Key("test"), value_type=Value.TEXT, ttl=5)
        assert metadata.expires_at is not None
        assert metadata.expires_at > datetime.now(UTC)

    def test_without_ttl_expires_at_none(self: Self) -> None:
        """Verify None TTL leaves expires_at as None."""
        metadata = Metadata.new(key=Key("test"), value_type=Value.TEXT, ttl=None)
        assert metadata.expires_at is None

    def test_sets_created_at(self: Self) -> None:
        """Verify created_at is set to current time."""
        before = datetime.now(UTC)
        metadata = Metadata.new(key=Key("test"), value_type=Value.TEXT, ttl=None)
        after = datetime.now(UTC)
        assert metadata.created_at is not None
        assert before <= metadata.created_at <= after


class TestMetadataIsExpired:
    """Tests for is_expired() method."""

    @pytest.mark.parametrize(
        ("offset", "expected"),
        [
            (timedelta(hours=1), False),
            (timedelta(days=-1), True),
        ],
    )
    def test_expired_based_on_time(self: Self, offset: timedelta, expected: bool) -> None:
        """Verify expiration based on expires_at vs current time."""
        metadata = Metadata(
            key=Key("test"),
            value_type=Value.TEXT,
            expires_at=datetime.now(UTC) + offset,
        )
        assert metadata.is_expired() == expected

    def test_none_expires_at_returns_false(self: Self) -> None:
        """Verify None expires_at means not expired."""
        metadata = Metadata(key=Key("test"), value_type=Value.TEXT)
        assert metadata.is_expired() is False


class TestMetadataRequireTz:
    """Tests for _require_tz validator."""

    def test_aware_datetime_passes(self: Self) -> None:
        """Verify timezone-aware datetime doesn't raise."""
        metadata = Metadata.new(key=Key("test"), value_type=Value.TEXT, ttl=None)
        assert metadata.created_at is not None
        assert metadata.created_at.tzinfo is not None

    def test_naive_datetime_raises(self: Self) -> None:
        """Verify naive datetime raises MetadataError."""
        with pytest.raises(MetadataError, match="Timestamps must be timezone-aware"):
            Metadata(
                key=Key("test"),
                value_type=Value.TEXT,
                created_at=datetime.now(),
            )


class TestMetadataModel:
    """Tests for Metadata model validation."""

    def test_model_validation(self: Self) -> None:
        """Verify Metadata can be created with valid args."""
        metadata = Metadata(key=Key("test"), value_type=Value.TEXT)
        assert metadata.key == Key("test")
        assert metadata.value_type == Value.TEXT
        assert metadata.expires_at is None
        assert metadata.created_at is None

    def test_invalid_key_type_raises(self: Self) -> None:
        """Verify invalid key type raises ValidationError."""
        with pytest.raises(ValidationError):
            Metadata(key=123, value_type=Value.TEXT)
