import asyncio
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pazufa_corelib.llm import (
    KurztitelResult,
    LLMProviderError,
    LLMQuotaExceededError,
    LLMRateLimitError,
    LLMTemporaryProviderError,
    LLMValidationError,
)
from scrapy.crawler import Crawler
from scrapy.exceptions import DropItem

from pazufa_scraper_be.cache import Cache, Key
from pazufa_scraper_be.pardok import GesetzVorgang
from pazufa_scraper_be.pipelines.documents.create_short_titel import CreateShortTitel
from pazufa_scraper_be.pipelines.stats_counter import LLMCounter, ShortTitelCounter
from tests.unit.pazufa_scraper_be.pipelines.documents.conftest import LLM_MODEL_NAME, force_expire, stat


@pytest.fixture
def pipeline(crawler: Crawler, connector: AsyncMock) -> CreateShortTitel:
    """Return a CreateShortTitel pipeline using the fake connector."""
    pipeline = CreateShortTitel(crawler=crawler)
    pipeline.llm_connector = connector
    pipeline.llm_model_name = LLM_MODEL_NAME
    connector.extract.return_value = KurztitelResult(kurztitel="Kurz")
    return pipeline


def _run(pipeline: CreateShortTitel, vorgang: GesetzVorgang) -> GesetzVorgang:
    return asyncio.run(pipeline.process_item(vorgang=vorgang))


def _cache(pipeline: CreateShortTitel, vorgang: GesetzVorgang, index: int = 0) -> Cache:
    dokument = vorgang.dokumente[index]
    assert dokument.lok_url is not None
    return pipeline.get_cache(document=dokument, document_url=dokument.lok_url)


def test__drops_non_vorgang_items(pipeline: CreateShortTitel) -> None:
    """Items that are not a GesetzVorgang are dropped."""
    with pytest.raises(DropItem):
        _run(pipeline=pipeline, vorgang="not a vorgang")  # ty: ignore[invalid-argument-type]


def test__without_connector_does_nothing(
    pipeline: CreateShortTitel, connector: AsyncMock, build_vorgang: Callable[..., GesetzVorgang], drs_data: dict[str, Any]
) -> None:
    """Without LLM connector the Vorgang is passed through untouched."""
    pipeline.llm_connector = None
    vorgang = build_vorgang(drs_data)

    assert _run(pipeline=pipeline, vorgang=vorgang) is vorgang
    connector.extract.assert_not_called()


@pytest.mark.parametrize("dok_fixture", ["drs_data", "gvbl_data"])
def test__stores_short_titel(
    pipeline: CreateShortTitel,
    crawler: Crawler,
    connector: AsyncMock,
    build_vorgang: Callable[..., GesetzVorgang],
    dok_fixture: str,
    request: pytest.FixtureRequest,
) -> None:
    """A short title is created and cached for Drs and GVBl documents."""
    vorgang = build_vorgang(request.getfixturevalue(dok_fixture))

    _run(pipeline=pipeline, vorgang=vorgang)

    assert _cache(pipeline=pipeline, vorgang=vorgang).get_text(Key.SHORT_TITEL) == "Kurz"
    connector.extract.assert_awaited_once()
    assert stat(crawler=crawler, counter=ShortTitelCounter.CACHE_MISS) == 1
    assert stat(crawler=crawler, counter=LLMCounter.SHORT_TITEL_TOTAL) == 1
    assert stat(crawler=crawler, counter=LLMCounter.SHORT_TITEL_DONE) == 1


def test__skips_protokoll_and_untitled_documents(
    pipeline: CreateShortTitel,
    connector: AsyncMock,
    build_vorgang: Callable[..., GesetzVorgang],
    plpr_data: dict[str, Any],
    drs_data: dict[str, Any],
) -> None:
    """Protokolle and documents without title get no short title."""
    vorgang = build_vorgang(plpr_data, {**drs_data, "Titel": None})

    _run(pipeline=pipeline, vorgang=vorgang)

    connector.extract.assert_not_called()


def test__cache_hit_skips_llm(
    pipeline: CreateShortTitel, crawler: Crawler, connector: AsyncMock, build_vorgang: Callable[..., GesetzVorgang], drs_data: dict[str, Any]
) -> None:
    """An existing short title is not regenerated."""
    vorgang = build_vorgang(drs_data)
    _cache(pipeline=pipeline, vorgang=vorgang)[Key.SHORT_TITEL] = "Existing"

    _run(pipeline=pipeline, vorgang=vorgang)

    connector.extract.assert_not_called()
    assert stat(crawler=crawler, counter=ShortTitelCounter.CACHE_HIT) == 1


def test__active_ignore_skips_llm(
    pipeline: CreateShortTitel, crawler: Crawler, connector: AsyncMock, build_vorgang: Callable[..., GesetzVorgang], drs_data: dict[str, Any]
) -> None:
    """An active ignore marker prevents the LLM call."""
    vorgang = build_vorgang(drs_data)
    _cache(pipeline=pipeline, vorgang=vorgang).set_text(key=Key.SHORT_TITEL_IGNORE, value="err", ttl=timedelta(hours=1))

    _run(pipeline=pipeline, vorgang=vorgang)

    connector.extract.assert_not_called()
    assert stat(crawler=crawler, counter=ShortTitelCounter.IGNORE) == 1


def test__expired_ignore_is_reset(
    pipeline: CreateShortTitel, crawler: Crawler, connector: AsyncMock, build_vorgang: Callable[..., GesetzVorgang], drs_data: dict[str, Any]
) -> None:
    """An expired ignore marker is removed and the short title is created."""
    vorgang = build_vorgang(drs_data)
    cache = _cache(pipeline=pipeline, vorgang=vorgang)
    cache.set_text(key=Key.SHORT_TITEL_IGNORE, value="err", ttl=timedelta(hours=1))
    force_expire(cache=cache, key=Key.SHORT_TITEL_IGNORE)

    _run(pipeline=pipeline, vorgang=vorgang)

    connector.extract.assert_awaited_once()
    assert Key.SHORT_TITEL in cache
    assert stat(crawler=crawler, counter=ShortTitelCounter.RESET_TEMPORARY_IGNORE) == 1


@pytest.mark.parametrize(
    ("error_cls", "counter", "has_ttl"),
    [
        (LLMTemporaryProviderError, LLMCounter.SHORT_TITEL_FAILED_TEMPORARY, True),
        (LLMQuotaExceededError, LLMCounter.SHORT_TITEL_FAILED_QUOTA, True),
        (LLMRateLimitError, LLMCounter.SHORT_TITEL_FAILED_RATE_LIMIT, True),
        (LLMProviderError, LLMCounter.SHORT_TITEL_FAILED_PROVIDER, False),
    ],
)
def test__provider_error_sets_ignore(
    pipeline: CreateShortTitel,
    crawler: Crawler,
    connector: AsyncMock,
    build_vorgang: Callable[..., GesetzVorgang],
    drs_data: dict[str, Any],
    error_cls: type[LLMProviderError],
    counter: LLMCounter,
    has_ttl: bool,
) -> None:
    """Provider errors are counted and set an ignore marker with matching TTL."""
    connector.extract.side_effect = error_cls("boom")
    vorgang = build_vorgang(drs_data)

    _run(pipeline=pipeline, vorgang=vorgang)

    cache = _cache(pipeline=pipeline, vorgang=vorgang)
    assert Key.SHORT_TITEL not in cache
    assert (cache.get_metadata(Key.SHORT_TITEL_IGNORE).expires_at is not None) is has_ttl
    assert stat(crawler=crawler, counter=counter) == 1


def test__validation_error_does_not_crash_item(
    pipeline: CreateShortTitel, crawler: Crawler, connector: AsyncMock, build_vorgang: Callable[..., GesetzVorgang], drs_data: dict[str, Any]
) -> None:
    """A validation error for one document does not prevent processing of the next one."""
    connector.extract.side_effect = [LLMValidationError("invalid"), KurztitelResult(kurztitel="Kurz")]
    vorgang = build_vorgang(drs_data, drs_data)

    _run(pipeline=pipeline, vorgang=vorgang)

    assert Key.SHORT_TITEL_IGNORE in _cache(pipeline=pipeline, vorgang=vorgang, index=0)
    assert stat(crawler=crawler, counter=LLMCounter.SHORT_TITEL_FAILED_VALIDATION) == 1
    assert _cache(pipeline=pipeline, vorgang=vorgang, index=1).get_text(Key.SHORT_TITEL) == "Kurz"


def test__blank_short_titel_is_not_stored(
    pipeline: CreateShortTitel, crawler: Crawler, connector: AsyncMock, build_vorgang: Callable[..., GesetzVorgang], drs_data: dict[str, Any]
) -> None:
    """A whitespace-only short title is counted as failure and not cached."""
    connector.extract.return_value = KurztitelResult(kurztitel="   ")
    vorgang = build_vorgang(drs_data)

    _run(pipeline=pipeline, vorgang=vorgang)

    assert Key.SHORT_TITEL not in _cache(pipeline=pipeline, vorgang=vorgang)
    assert stat(crawler=crawler, counter=LLMCounter.SHORT_TITEL_DONE) == 0
    assert stat(crawler=crawler, counter=LLMCounter.SHORT_TITEL_FAILED_EMPTY) == 1
