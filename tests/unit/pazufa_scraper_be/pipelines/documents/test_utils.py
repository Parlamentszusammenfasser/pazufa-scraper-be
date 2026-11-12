import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pazufa_corelib.llm import LLMProviderError, LLMQuotaExceededError, LLMRateLimitError, LLMTemporaryProviderError

from pazufa_scraper_be.cache import Cache, Key
from pazufa_scraper_be.pipelines.documents.utils import IgnoreStatus, resolve_ignore, set_llm_error_ignore


def _force_expire(cache: Cache, key: Key) -> None:
    """Rewrite metadata to make an entry appear expired."""
    meta_file = cache.backend.directory / f".{key}.metadata"
    data = json.loads(meta_file.read_text())
    data["expires_at"] = "2020-01-01T00:00:00+00:00"
    meta_file.write_text(json.dumps(data))


class TestResolveIgnore:
    """Tests for resolve_ignore."""

    def test_absent_when_key_missing(self, tmp_path: Path) -> None:
        """Returns 'absent' when the key does not exist in cache."""
        cache = Cache(base_dir=tmp_path, name="test")
        assert resolve_ignore(cache, Key.SUMMARY_IGNORE) is IgnoreStatus.ABSENT

    def test_active_when_key_present_and_not_expired(self, tmp_path: Path) -> None:
        """Returns 'active' and preserves the entry when not expired."""
        cache = Cache(base_dir=tmp_path, name="test")
        cache.set_text(key=Key.SUMMARY_IGNORE, value="err", ttl=timedelta(hours=12))

        assert resolve_ignore(cache, Key.SUMMARY_IGNORE) is IgnoreStatus.ACTIVE
        assert Key.SUMMARY_IGNORE in cache

    def test_expired_when_key_present_and_expired(self, tmp_path: Path) -> None:
        """Returns 'expired' and deletes the entry when expired."""
        cache = Cache(base_dir=tmp_path, name="test")
        cache.set_text(key=Key.SUMMARY_IGNORE, value="err", ttl=timedelta(hours=1))
        _force_expire(cache, Key.SUMMARY_IGNORE)

        assert resolve_ignore(cache, Key.SUMMARY_IGNORE) is IgnoreStatus.EXPIRED
        assert Key.SUMMARY_IGNORE not in cache


class TestSetLLMErrorIgnore:
    """Tests for set_llm_error_ignore."""

    @pytest.mark.parametrize(
        ("error_cls", "expected_hours"),
        [
            (LLMTemporaryProviderError, 12),
            (LLMQuotaExceededError, 6),
            (LLMRateLimitError, 1),
        ],
    )
    def test_ttl_for_specific_errors(self, tmp_path: Path, error_cls: type[LLMProviderError], expected_hours: int) -> None:
        """Sets a TTL matching the error type severity."""
        before = datetime.now(UTC)
        cache = Cache(base_dir=tmp_path, name="test")
        error = error_cls("test error")

        set_llm_error_ignore(cache, Key.SUMMARY_IGNORE, error)

        metadata = cache.get_metadata(Key.SUMMARY_IGNORE)
        assert metadata.expires_at is not None
        lower = before + timedelta(hours=expected_hours)
        upper = lower + timedelta(seconds=5)
        assert lower <= metadata.expires_at <= upper
        assert cache.get_text(key=Key.SUMMARY_IGNORE) == repr(error)

    def test_no_ttl_for_base_provider_error(self, tmp_path: Path) -> None:
        """Sets no expiration for the generic base error."""
        cache = Cache(base_dir=tmp_path, name="test")
        error = LLMProviderError("base error")

        set_llm_error_ignore(cache, Key.SUMMARY_IGNORE, error)

        metadata = cache.get_metadata(Key.SUMMARY_IGNORE)
        assert metadata.expires_at is None
        assert cache.get_text(key=Key.SUMMARY_IGNORE) == repr(error)

    def test_stores_repr_as_value(self, tmp_path: Path) -> None:
        """Stores the repr of the error as the cache text value."""
        cache = Cache(base_dir=tmp_path, name="test")
        error = LLMRateLimitError("rate limited")

        set_llm_error_ignore(cache, Key.SUMMARY_IGNORE, error)

        assert cache.get_text(key=Key.SUMMARY_IGNORE) == repr(error)
