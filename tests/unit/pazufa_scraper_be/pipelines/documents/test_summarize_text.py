import asyncio
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pazufa_corelib.llm import (
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
from pazufa_scraper_be.pipelines.documents.summarize_text import SummarizeExtractedPDFText, VorgangContext, vorgang_context
from pazufa_scraper_be.pipelines.stats_counter import LLMCounter, SummaryCounter
from tests.unit.pazufa_scraper_be.pipelines.documents.conftest import LLM_MODEL_NAME, force_expire, stat

TEXT = "Extracted text."


@pytest.fixture
def pipeline(crawler: Crawler, connector: AsyncMock) -> SummarizeExtractedPDFText:
    """Return a SummarizeExtractedPDFText pipeline using the fake connector."""
    pipeline = SummarizeExtractedPDFText(crawler=crawler)
    pipeline.llm_connector = connector
    pipeline.llm_model_name = LLM_MODEL_NAME
    connector.summarize_dokument.return_value = "Dokument summary"
    connector.summarize_gesetzentwurf.return_value = "Gesetzentwurf summary"
    connector.extract_relevant_section.return_value = "Relevant section"
    return pipeline


def _run(pipeline: SummarizeExtractedPDFText, vorgang: GesetzVorgang) -> GesetzVorgang:
    return asyncio.run(pipeline.process_item(vorgang=vorgang))


def _cache(pipeline: SummarizeExtractedPDFText, vorgang: GesetzVorgang, index: int = 0, *, text: str | None = TEXT) -> Cache:
    dokument = vorgang.dokumente[index]
    assert dokument.lok_url is not None
    cache = pipeline.get_cache(document=dokument, document_url=dokument.lok_url)

    if text is not None:
        cache[Key.TEXT] = text

    return cache


def test__drops_non_vorgang_items(pipeline: SummarizeExtractedPDFText) -> None:
    """Items that are not a GesetzVorgang are dropped."""
    with pytest.raises(DropItem):
        _run(pipeline=pipeline, vorgang="not a vorgang")  # ty: ignore[invalid-argument-type]


def test__without_connector_does_nothing(
    pipeline: SummarizeExtractedPDFText, connector: AsyncMock, build_vorgang: Callable[..., GesetzVorgang], drs_data: dict[str, Any]
) -> None:
    """Without LLM connector the Vorgang is passed through untouched."""
    pipeline.llm_connector = None
    vorgang = build_vorgang(drs_data)
    _cache(pipeline=pipeline, vorgang=vorgang)

    assert _run(pipeline=pipeline, vorgang=vorgang) is vorgang
    connector.summarize_dokument.assert_not_called()


def test__drs_is_summarized(
    pipeline: SummarizeExtractedPDFText,
    crawler: Crawler,
    connector: AsyncMock,
    build_vorgang: Callable[..., GesetzVorgang],
    drs_data: dict[str, Any],
) -> None:
    """Drucksachen are summarized via summarize_dokument and the result is linked as SUMMARY."""
    vorgang = build_vorgang(drs_data)
    cache = _cache(pipeline=pipeline, vorgang=vorgang)

    _run(pipeline=pipeline, vorgang=vorgang)

    connector.summarize_dokument.assert_awaited_once_with(titel="Title Drs", text=TEXT)
    assert cache.exist_model_specific_summary(llm_model_name=LLM_MODEL_NAME)
    assert cache.get_text(Key.SUMMARY) == "Dokument summary"
    assert stat(crawler=crawler, counter=SummaryCounter.CACHE_MISS) == 1
    assert stat(crawler=crawler, counter=LLMCounter.SUMMARIZE_TOTAL) == 1
    assert stat(crawler=crawler, counter=LLMCounter.SUMMARIZE_DONE) == 1
    assert stat(crawler=crawler, counter=LLMCounter.summarize_art(vorgang.dokumente[0].art_l.lower())) == 1


def test__gvbl_is_summarized_as_gesetzentwurf(
    pipeline: SummarizeExtractedPDFText, connector: AsyncMock, build_vorgang: Callable[..., GesetzVorgang], gvbl_data: dict[str, Any]
) -> None:
    """GVBl documents are summarized via summarize_gesetzentwurf."""
    vorgang = build_vorgang(gvbl_data)
    cache = _cache(pipeline=pipeline, vorgang=vorgang)

    _run(pipeline=pipeline, vorgang=vorgang)

    connector.summarize_gesetzentwurf.assert_awaited_once_with(titel="Title GVBl", text=TEXT)
    assert cache.get_text(Key.SUMMARY) == "Gesetzentwurf summary"


def test__protokoll_summarizes_relevant_section(
    pipeline: SummarizeExtractedPDFText,
    crawler: Crawler,
    connector: AsyncMock,
    build_vorgang: Callable[..., GesetzVorgang],
    drs_data: dict[str, Any],
    plpr_data: dict[str, Any],
) -> None:
    """Protokolle are reduced to the relevant section before summarizing."""
    vorgang = build_vorgang(drs_data, plpr_data)
    cache = _cache(pipeline=pipeline, vorgang=vorgang, index=1)

    _run(pipeline=pipeline, vorgang=vorgang)

    connector.extract_relevant_section.assert_awaited_once_with(text=TEXT, vorgang_titel="Title Drs", vorgang_vnr="123/2024")
    connector.summarize_dokument.assert_awaited_once_with(titel="Title Drs", text="Relevant section")
    assert cache.get_text(Key.SUMMARY) == "Dokument summary"
    assert stat(crawler=crawler, counter=LLMCounter.EXTRACT_RELEVANT_SECTION_DONE) == 1


def test__missing_text_is_skipped(
    pipeline: SummarizeExtractedPDFText, crawler: Crawler, connector: AsyncMock, build_vorgang: Callable[..., GesetzVorgang], drs_data: dict[str, Any]
) -> None:
    """Documents without extracted text are skipped silently."""
    vorgang = build_vorgang(drs_data)
    _cache(pipeline=pipeline, vorgang=vorgang, text=None)

    _run(pipeline=pipeline, vorgang=vorgang)

    connector.summarize_dokument.assert_not_called()
    assert stat(crawler=crawler, counter=SummaryCounter.CACHE_MISS) == 0


def test__cache_hit_links_existing_summary(
    pipeline: SummarizeExtractedPDFText, crawler: Crawler, connector: AsyncMock, build_vorgang: Callable[..., GesetzVorgang], drs_data: dict[str, Any]
) -> None:
    """An existing model specific summary is linked instead of regenerated."""
    vorgang = build_vorgang(drs_data)
    cache = _cache(pipeline=pipeline, vorgang=vorgang)
    cache.set_model_specific_summary(llm_model_name=LLM_MODEL_NAME, summary="Existing")

    _run(pipeline=pipeline, vorgang=vorgang)

    connector.summarize_dokument.assert_not_called()
    assert cache.get_text(Key.SUMMARY) == "Existing"
    assert stat(crawler=crawler, counter=SummaryCounter.CACHE_HIT) == 1


def test__active_ignore_skips_llm(
    pipeline: SummarizeExtractedPDFText, crawler: Crawler, connector: AsyncMock, build_vorgang: Callable[..., GesetzVorgang], drs_data: dict[str, Any]
) -> None:
    """An active ignore marker prevents the LLM call."""
    vorgang = build_vorgang(drs_data)
    _cache(pipeline=pipeline, vorgang=vorgang).set_text(key=Key.SUMMARY_IGNORE, value="err", ttl=timedelta(hours=1))

    _run(pipeline=pipeline, vorgang=vorgang)

    connector.summarize_dokument.assert_not_called()
    assert stat(crawler=crawler, counter=SummaryCounter.IGNORE) == 1


def test__expired_ignore_is_reset(
    pipeline: SummarizeExtractedPDFText, crawler: Crawler, connector: AsyncMock, build_vorgang: Callable[..., GesetzVorgang], drs_data: dict[str, Any]
) -> None:
    """An expired ignore marker is removed and the summary is created."""
    vorgang = build_vorgang(drs_data)
    cache = _cache(pipeline=pipeline, vorgang=vorgang)
    cache.set_text(key=Key.SUMMARY_IGNORE, value="err", ttl=timedelta(hours=1))
    force_expire(cache=cache, key=Key.SUMMARY_IGNORE)

    _run(pipeline=pipeline, vorgang=vorgang)

    connector.summarize_dokument.assert_awaited_once()
    assert stat(crawler=crawler, counter=SummaryCounter.RESET_TEMPORARY_IGNORE) == 1


@pytest.mark.parametrize(
    ("error_cls", "counter", "has_ttl"),
    [
        (LLMTemporaryProviderError, LLMCounter.SUMMARIZE_FAILED_TEMPORARY, True),
        (LLMQuotaExceededError, LLMCounter.SUMMARIZE_FAILED_QUOTA, True),
        (LLMRateLimitError, LLMCounter.SUMMARIZE_FAILED_RATE_LIMIT, True),
        (LLMProviderError, LLMCounter.SUMMARIZE_FAILED_PROVIDER, False),
    ],
)
def test__provider_error_sets_ignore(
    pipeline: SummarizeExtractedPDFText,
    crawler: Crawler,
    connector: AsyncMock,
    build_vorgang: Callable[..., GesetzVorgang],
    drs_data: dict[str, Any],
    error_cls: type[LLMProviderError],
    counter: LLMCounter,
    has_ttl: bool,
) -> None:
    """Provider errors are counted and set an ignore marker with matching TTL."""
    connector.summarize_dokument.side_effect = error_cls("boom")
    vorgang = build_vorgang(drs_data)
    cache = _cache(pipeline=pipeline, vorgang=vorgang)

    _run(pipeline=pipeline, vorgang=vorgang)

    assert Key.SUMMARY not in cache
    assert (cache.get_metadata(Key.SUMMARY_IGNORE).expires_at is not None) is has_ttl
    assert stat(crawler=crawler, counter=counter) == 1


def test__empty_summary_is_not_stored(
    pipeline: SummarizeExtractedPDFText, crawler: Crawler, connector: AsyncMock, build_vorgang: Callable[..., GesetzVorgang], drs_data: dict[str, Any]
) -> None:
    """An empty summary is counted as failure and not cached."""
    connector.summarize_dokument.return_value = ""
    vorgang = build_vorgang(drs_data)
    cache = _cache(pipeline=pipeline, vorgang=vorgang)

    _run(pipeline=pipeline, vorgang=vorgang)

    assert Key.SUMMARY not in cache
    assert stat(crawler=crawler, counter=LLMCounter.SUMMARIZE_FAILED_EMPTY_SUMMARY) == 1


def test__protokoll_without_relevant_section_is_ignored_permanently(
    pipeline: SummarizeExtractedPDFText,
    crawler: Crawler,
    connector: AsyncMock,
    build_vorgang: Callable[..., GesetzVorgang],
    drs_data: dict[str, Any],
    plpr_data: dict[str, Any],
) -> None:
    """A Protokoll without relevant section gets a permanent ignore marker and is counted once."""
    connector.extract_relevant_section.return_value = None
    vorgang = build_vorgang(drs_data, plpr_data)
    cache = _cache(pipeline=pipeline, vorgang=vorgang, index=1)

    _run(pipeline=pipeline, vorgang=vorgang)

    connector.summarize_dokument.assert_not_called()
    assert cache.get_metadata(Key.SUMMARY_IGNORE).expires_at is None
    assert stat(crawler=crawler, counter=LLMCounter.EXTRACT_RELEVANT_SECTION_FAILED) == 1
    assert stat(crawler=crawler, counter=LLMCounter.SUMMARIZE_DONE) == 0


def test__protokoll_extraction_rate_limit_sets_temporary_ignore(
    pipeline: SummarizeExtractedPDFText,
    crawler: Crawler,
    connector: AsyncMock,
    build_vorgang: Callable[..., GesetzVorgang],
    drs_data: dict[str, Any],
    plpr_data: dict[str, Any],
) -> None:
    """A rate limit during section extraction results in a temporary ignore marker."""
    connector.extract_relevant_section.side_effect = LLMRateLimitError("slow down")
    vorgang = build_vorgang(drs_data, plpr_data)
    cache = _cache(pipeline=pipeline, vorgang=vorgang, index=1)

    _run(pipeline=pipeline, vorgang=vorgang)

    assert cache.get_metadata(Key.SUMMARY_IGNORE).expires_at is not None
    assert stat(crawler=crawler, counter=LLMCounter.SUMMARIZE_FAILED_RATE_LIMIT) == 1


def test__validation_error_does_not_crash_item(
    pipeline: SummarizeExtractedPDFText, crawler: Crawler, connector: AsyncMock, build_vorgang: Callable[..., GesetzVorgang], drs_data: dict[str, Any]
) -> None:
    """A validation error for one document does not prevent processing of the next one."""
    connector.summarize_dokument.side_effect = [LLMValidationError("invalid"), "Dokument summary"]
    vorgang = build_vorgang(drs_data, drs_data)
    first = _cache(pipeline=pipeline, vorgang=vorgang, index=0)
    second = _cache(pipeline=pipeline, vorgang=vorgang, index=1)

    _run(pipeline=pipeline, vorgang=vorgang)

    assert Key.SUMMARY_IGNORE in first
    assert stat(crawler=crawler, counter=LLMCounter.SUMMARIZE_FAILED_VALIDATION) == 1
    assert second.get_text(Key.SUMMARY) == "Dokument summary"


def test__vorgang_titel_is_taken_from_first_titled_document(
    pipeline: SummarizeExtractedPDFText,
    connector: AsyncMock,
    build_vorgang: Callable[..., GesetzVorgang],
    drs_data: dict[str, Any],
    plpr_data: dict[str, Any],
) -> None:
    """The Vorgang titel and number come from the first document carrying a titel."""
    vorgang = build_vorgang(plpr_data, {**drs_data, "DokNr": "19/42"})
    _cache(pipeline=pipeline, vorgang=vorgang, index=0)

    _run(pipeline=pipeline, vorgang=vorgang)

    connector.extract_relevant_section.assert_awaited_once_with(text=TEXT, vorgang_titel="Title Drs", vorgang_vnr="19/42")


@pytest.mark.parametrize(("dok_fixture", "overrides"), [("plpr_data", {}), ("drs_data", {"Titel": None})])
def test__vorgang_without_titel_is_ignored(
    pipeline: SummarizeExtractedPDFText,
    connector: AsyncMock,
    build_vorgang: Callable[..., GesetzVorgang],
    dok_fixture: str,
    overrides: dict[str, Any],
    request: pytest.FixtureRequest,
) -> None:
    """Documents of a Vorgang without any titel are ignored instead of calling the LLM."""
    vorgang = build_vorgang({**request.getfixturevalue(dok_fixture), **overrides})
    cache = _cache(pipeline=pipeline, vorgang=vorgang)

    _run(pipeline=pipeline, vorgang=vorgang)

    connector.extract_relevant_section.assert_not_called()
    connector.summarize_dokument.assert_not_called()
    assert cache.get_metadata(Key.SUMMARY_IGNORE).expires_at is None


def test__vorgang_context_uses_first_titled_document(
    build_vorgang: Callable[..., GesetzVorgang], plpr_data: dict[str, Any], drs_data: dict[str, Any], gvbl_data: dict[str, Any]
) -> None:
    """vorgang_context skips documents without titel."""
    vorgang = build_vorgang(plpr_data, {**drs_data, "Titel": None}, {**drs_data, "DokNr": "19/1"}, gvbl_data)

    assert vorgang_context(vorgang=vorgang) == VorgangContext(titel="Title Drs", nr="19/1")


def test__vorgang_context_is_none_without_titel(build_vorgang: Callable[..., GesetzVorgang], plpr_data: dict[str, Any]) -> None:
    """vorgang_context returns None if no document has a titel."""
    assert vorgang_context(vorgang=build_vorgang(plpr_data)) is None
