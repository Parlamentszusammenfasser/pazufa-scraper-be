import asyncio
from collections.abc import Callable, Iterator
from typing import Any, ClassVar, Self
from unittest.mock import AsyncMock

import pytest
from pazufa_corelib.llm import (
    LLMConnector,
    LLMConnectorError,
    LLMProviderError,
    LLMQuotaExceededError,
    LLMRateLimitError,
    LLMTemporaryProviderError,
    LLMValidationError,
)
from pydantic import HttpUrl
from scrapy.crawler import Crawler

from pazufa_scraper_be.cache import Cache, Key
from pazufa_scraper_be.pardok import AnyGesetzDokument, GesetzVorgang
from pazufa_scraper_be.pipelines.documents._llm_task import CachedLLMTaskPipeline, SkipTaskError, error_counter
from pazufa_scraper_be.pipelines.stats_counter import SHORT_TITEL_COUNTERS, LLMCounter, LLMTaskCounters
from tests.unit.pazufa_scraper_be.pipelines.documents.conftest import stat

COUNTERS = SHORT_TITEL_COUNTERS


class FakeTask(CachedLLMTaskPipeline):
    """Minimal concrete task delegating generation to the connector mock."""

    ignore_key: ClassVar[Key] = Key.SHORT_TITEL_IGNORE
    counters: ClassVar[LLMTaskCounters] = COUNTERS
    task_name: ClassVar[str] = "Fake task"
    input_available = True

    def targets(self: Self, vorgang: GesetzVorgang) -> Iterator[tuple[AnyGesetzDokument, HttpUrl]]:
        """Yield the primary URL of every document."""
        for dokument in vorgang.dokumente:
            if dokument.lok_url:
                yield dokument, dokument.lok_url

    def has_input(self: Self, cache: Cache) -> bool:  # noqa: ARG002
        """Return the configured input availability."""
        return self.input_available

    def is_cached(self: Self, cache: Cache) -> bool:
        """Check for an existing result."""
        return Key.SHORT_TITEL in cache

    async def generate(self: Self, connector: LLMConnector, dokument: AnyGesetzDokument, cache: Cache) -> str:  # noqa: ARG002
        """Delegate to the connector mock."""
        return await connector.summarize_dokument(titel="", text="")

    def store(self: Self, cache: Cache, result: str) -> None:
        """Store the result."""
        cache[Key.SHORT_TITEL] = result


@pytest.fixture
def pipeline(crawler: Crawler, connector: AsyncMock) -> FakeTask:
    """Return the fake task pipeline using the fake connector."""
    pipeline = FakeTask(crawler=crawler)
    pipeline.llm_connector = connector
    connector.summarize_dokument.return_value = "result"
    return pipeline


def _cache(pipeline: FakeTask, vorgang: GesetzVorgang) -> Cache:
    dokument = vorgang.dokumente[0]
    assert dokument.lok_url is not None
    return pipeline.get_cache(document=dokument, document_url=dokument.lok_url)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (LLMTemporaryProviderError("x"), COUNTERS.failed_temporary),
        (LLMQuotaExceededError("x"), COUNTERS.failed_quota),
        (LLMRateLimitError("x"), COUNTERS.failed_rate_limit),
        (LLMProviderError("x"), COUNTERS.failed_provider),
        (LLMValidationError("x"), COUNTERS.failed_validation),
        (LLMConnectorError("x"), COUNTERS.failed_validation),
    ],
)
def test__error_counter(error: LLMConnectorError, expected: LLMCounter) -> None:
    """Each LLM error type maps to its counter."""
    assert error_counter(counters=COUNTERS, error=error) == expected


def test__skip_task_sets_permanent_ignore_and_counts(
    pipeline: FakeTask, crawler: Crawler, connector: AsyncMock, build_vorgang: Callable[..., GesetzVorgang], drs_data: dict[str, Any]
) -> None:
    """SkipTaskError stores its reason as permanent ignore marker and increments its counter."""
    connector.summarize_dokument.side_effect = SkipTaskError(reason="nothing to do", counter=LLMCounter.EXTRACT_RELEVANT_SECTION_FAILED)
    vorgang = build_vorgang(drs_data)

    asyncio.run(pipeline.process_item(vorgang=vorgang))

    cache = _cache(pipeline=pipeline, vorgang=vorgang)
    assert cache.get_text(Key.SHORT_TITEL_IGNORE) == "nothing to do"
    assert cache.get_metadata(Key.SHORT_TITEL_IGNORE).expires_at is None
    assert Key.SHORT_TITEL not in cache
    assert stat(crawler=crawler, counter=LLMCounter.EXTRACT_RELEVANT_SECTION_FAILED) == 1
    assert stat(crawler=crawler, counter=COUNTERS.done) == 0


def test__missing_input_skips_silently(
    pipeline: FakeTask, crawler: Crawler, connector: AsyncMock, build_vorgang: Callable[..., GesetzVorgang], drs_data: dict[str, Any]
) -> None:
    """Without input neither the LLM is called nor a cache counter is incremented."""
    pipeline.input_available = False
    vorgang = build_vorgang(drs_data)

    asyncio.run(pipeline.process_item(vorgang=vorgang))

    connector.summarize_dokument.assert_not_called()
    assert stat(crawler=crawler, counter=COUNTERS.cache_miss) == 0
    assert stat(crawler=crawler, counter=COUNTERS.cache_hit) == 0
