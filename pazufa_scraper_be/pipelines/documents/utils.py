from datetime import timedelta
from enum import StrEnum

from pazufa_corelib.llm import LLMConnectorError, LLMQuotaExceededError, LLMRateLimitError, LLMTemporaryProviderError

from pazufa_scraper_be.cache import Cache, Key


class IgnoreStatus(StrEnum):
    """Possible states of a cache ignore marker."""

    ACTIVE = "active"
    EXPIRED = "expired"
    ABSENT = "absent"


def resolve_ignore(cache: Cache, ignore_key: Key) -> IgnoreStatus:
    """Check ignore marker state; deletes entry if expired (side effect)."""
    if ignore_key not in cache:
        return IgnoreStatus.ABSENT

    if cache.is_expired(ignore_key):
        cache.delete_entry(ignore_key)
        return IgnoreStatus.EXPIRED

    return IgnoreStatus.ACTIVE


def set_llm_error_ignore(cache: Cache, ignore_key: Key, error: LLMConnectorError) -> None:
    """Set cache ignore marker with TTL based on LLM error type; unknown errors are ignored permanently."""
    if isinstance(error, LLMTemporaryProviderError):
        cache.set_text(key=ignore_key, value=repr(error), ttl=timedelta(hours=12))

    elif isinstance(error, LLMQuotaExceededError):
        cache.set_text(key=ignore_key, value=repr(error), ttl=timedelta(hours=6))

    elif isinstance(error, LLMRateLimitError):
        cache.set_text(key=ignore_key, value=repr(error), ttl=timedelta(hours=1))

    else:
        cache[ignore_key] = repr(error)
