import logging
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import HttpUrl
from scrapy import Spider
from scrapy.crawler import Crawler
from scrapy.settings import Settings
from scrapy.statscollectors import StatsCollector

from pazufa_scraper_be.constants import DOK_BASE_URL
from pazufa_scraper_be.pardok import PlPrDokument
from pazufa_scraper_be.pipelines._base import (
    ApiPipeline,
    BasePipeline,
    CacheDirPipeline,
    LLMPipeline,
    StatsPipeline,
)
from pazufa_scraper_be.pipelines.stats_counter import DokumentCounter

WAHLPERIODE = 19


class ConcreteBasePipeline(BasePipeline):
    """Concrete pipeline for testing the abstract base class."""

    def init(self) -> None:
        """Mark the test pipeline as initialized."""
        self.initialized = True


def make_crawler(settings: dict | None = None, stats: StatsCollector | None = None) -> Crawler:
    """Create a minimal crawler double."""
    crawler = Crawler(Spider, Settings(settings or {}))
    crawler.stats = stats
    return crawler


def test__base_pipeline_from_crawler_initializes_pipeline() -> None:
    """from_crawler creates a pipeline and passes through the crawler."""
    crawler = make_crawler({"WAHLPERIODE": WAHLPERIODE})

    pipeline = ConcreteBasePipeline.from_crawler(crawler)

    assert pipeline.crawler is crawler
    assert pipeline.wahlperiode == WAHLPERIODE
    assert pipeline.initialized is True


def test__base_pipeline_uses_scrapy_default_for_missing_wahlperiode() -> None:
    """Construction uses Scrapy's zero default when WAHLPERIODE is missing."""
    pipeline = ConcreteBasePipeline(make_crawler())

    assert pipeline.wahlperiode == 0


def test__base_pipeline_raises_when_wahlperiode_is_none() -> None:
    """Construction fails when the settings object returns None."""
    crawler = make_crawler()
    with patch.object(crawler.settings, "getint", return_value=None), pytest.raises(ValueError, match="Missing WAHLPERIODE"):
        ConcreteBasePipeline(crawler)


def test__stats_pipeline_increments_enum_and_string_counters() -> None:
    """StatsPipeline supports StatsCounter values and literal keys."""
    crawler = make_crawler({"WAHLPERIODE": WAHLPERIODE})
    stats = StatsCollector(crawler)
    crawler.stats = stats
    pipeline = StatsPipeline(crawler)

    with patch.object(StatsCollector, "inc_value") as increment:
        pipeline.increment_stats(DokumentCounter.CACHE_HIT)
        pipeline.increment_stats("custom/key")

    increment.assert_any_call(DokumentCounter.CACHE_HIT.value)
    increment.assert_any_call("custom/key")


def test__stats_pipeline_does_not_increment_without_stats() -> None:
    """StatsPipeline treats a missing stats collector as a no-op."""
    pipeline = StatsPipeline(make_crawler({"WAHLPERIODE": 19}))

    with patch.object(StatsCollector, "inc_value") as increment:
        pipeline.increment_stats("custom/key")

    increment.assert_not_called()


def test__cache_pipeline_builds_document_cache_path_and_creates_directory(tmp_path: Path, plpr_data: dict) -> None:
    """Document cache paths use the document art and URL path."""
    pipeline = CacheDirPipeline(make_crawler({"WAHLPERIODE": 19, "CACHE_DIR": tmp_path / "cache", "ERRORS_DIR": tmp_path / "errors"}))

    document = PlPrDokument.model_validate(
        {
            **plpr_data,
            "LokURL": f"{DOK_BASE_URL}/19/19/123.pdf",
        }
    )
    url = HttpUrl(f"{DOK_BASE_URL}/19/19/123.pdf")

    result = pipeline.get_dokument_cache_dir(document, url)

    assert result == tmp_path / "cache" / "19" / "dokument" / "PlPr" / "123"
    assert result.is_dir()


def test__cache_pipeline_raises_when_cache_dir_is_none(tmp_path: Path) -> None:
    """Initialization fails when cache directory construction returns None."""
    cache_path = MagicMock()
    cache_path.__truediv__.return_value = None
    crawler = make_crawler({"WAHLPERIODE": 19, "CACHE_DIR": tmp_path / "cache", "ERRORS_DIR": tmp_path / "errors"})

    with patch("pazufa_scraper_be.pipelines._base.Path", return_value=cache_path), pytest.raises(ValueError, match="Missing CACHE_DIR"):
        CacheDirPipeline(crawler)


def test__cache_pipeline_raises_when_errors_dir_is_none(tmp_path: Path) -> None:
    """Initialization fails when error directory construction returns None."""
    cache_path = MagicMock()
    errors_path = MagicMock()
    errors_path.__truediv__.return_value = None
    crawler = make_crawler({"WAHLPERIODE": 19, "CACHE_DIR": tmp_path / "cache", "ERRORS_DIR": tmp_path / "errors"})

    with patch("pazufa_scraper_be.pipelines._base.Path", side_effect=[cache_path, errors_path]), pytest.raises(ValueError, match="Missing ERRORS_DIR"):
        CacheDirPipeline(crawler)


def test__cache_pipeline_rejects_unassociated_url(tmp_path: Path, plpr_data: dict) -> None:
    """A URL not belonging to the document is not cached."""
    pipeline = CacheDirPipeline(make_crawler({"WAHLPERIODE": 19, "CACHE_DIR": tmp_path / "cache", "ERRORS_DIR": tmp_path / "errors"}))
    document = PlPrDokument.model_validate(
        {
            **plpr_data,
            "additional_urls": ["https://example.com/additional.pdf"],
        }
    )

    assert pipeline.get_dokument_cache_dir(document, HttpUrl("https://example.com/other.pdf")) is None


def test__cache_pipeline_accepts_additional_url(tmp_path: Path, plpr_data: dict) -> None:
    """Additional document URLs use the same cache path logic."""
    additional_url = HttpUrl(f"{DOK_BASE_URL}/19/19/124.pdf")
    pipeline = CacheDirPipeline(make_crawler({"WAHLPERIODE": 19, "CACHE_DIR": tmp_path / "cache", "ERRORS_DIR": tmp_path / "errors"}))
    document = PlPrDokument.model_validate({**plpr_data, "additional_urls": [str(additional_url)]})

    result = pipeline.get_dokument_cache_dir(document, additional_url)

    assert result == tmp_path / "cache" / "19" / "dokument" / "PlPr" / "124"


def test__cache_pipeline_builds_timestamped_error_directory(tmp_path: Path) -> None:
    """Error directories include the crawler start timestamp."""
    stats = StatsCollector(make_crawler())
    stats.set_value("start_time", datetime(2026, 8, 24, 14, 43, 9, tzinfo=UTC))
    pipeline = CacheDirPipeline(make_crawler({"WAHLPERIODE": 19, "CACHE_DIR": tmp_path / "cache", "ERRORS_DIR": tmp_path / "errors"}, stats=stats))

    result = pipeline.get_errors_dir()

    assert result == tmp_path / "errors" / "19" / "2026-08-24T14:43:09"
    assert result.is_dir()


def test__api_pipeline_requires_scraper_uuid() -> None:
    """ApiPipeline requires the scraper UUID setting."""
    with pytest.raises(ValueError, match="Missing SCRAPER_UUID"):
        ApiPipeline(make_crawler({"WAHLPERIODE": 19}))


def test__api_pipeline_requires_api_url_when_token_is_set() -> None:
    """An API token requires an API URL."""
    with pytest.raises(ValueError, match="API_URL setting is required"):
        ApiPipeline(make_crawler({"WAHLPERIODE": 19, "API_TOKEN": "token", "SCRAPER_UUID": "uuid"}))


def test__api_pipeline_without_token_has_no_client(caplog: pytest.LogCaptureFixture) -> None:
    """Without a token, API submission is disabled."""
    with caplog.at_level(logging.INFO):
        pipeline = ApiPipeline(make_crawler({"WAHLPERIODE": 19, "SCRAPER_UUID": "uuid"}))

    assert pipeline.get_client() is None
    assert "API_TOKEN is not set" in caplog.text


def test__api_pipeline_creates_authenticated_client() -> None:
    """Configured API credentials are passed to AuthenticatedClient."""
    settings = {"WAHLPERIODE": 19, "API_URL": "https://api.example", "API_TOKEN": "test-value", "SCRAPER_UUID": "uuid"}
    with patch("pazufa_scraper_be.pipelines._base.AuthenticatedClient") as client:
        pipeline = ApiPipeline(make_crawler(settings))

        result = pipeline.get_client()

    assert result is client.return_value
    client.assert_called_once()
    assert client.call_args.kwargs == {
        "base_url": "https://api.example",
        "token": "test-value",
        "prefix": "",
        "auth_header_name": "X-API-Key",
    }


def test__llm_pipeline_without_token_skips_connector(caplog: pytest.LogCaptureFixture) -> None:
    """Without an LLM token, summarization is disabled."""
    with caplog.at_level(logging.INFO):
        pipeline = LLMPipeline(make_crawler({"WAHLPERIODE": 19}))

    assert pipeline.llm_connector is None
    assert "LLM_TOKEN is not set" in caplog.text


def test__llm_pipeline_requires_model_when_token_is_set() -> None:
    """An LLM token requires a model name."""
    settings = {"WAHLPERIODE": 19, "LLM_TOKEN": "token"}

    with pytest.raises(ValueError, match="LLM_MODEL setting is required"):
        LLMPipeline(make_crawler(settings))


@pytest.mark.parametrize("timeout", [0, -1])
def test__llm_pipeline_requires_positive_timeout(timeout: int) -> None:
    """LLM timeout must be a positive integer."""
    settings = {"WAHLPERIODE": 19, "LLM_TOKEN": "token", "LLM_MODEL": "model", "LLM_TIMEOUT": timeout}

    with pytest.raises(ValueError, match="Invalid LLM_TIMEOUT"):
        LLMPipeline(make_crawler(settings))


def test__llm_pipeline_creates_connector_and_configures_litellm() -> None:
    """Configured LLM settings are passed to LLMConnector."""
    settings = {"WAHLPERIODE": 19, "LLM_TOKEN": "token", "LLM_MODEL": "model", "LLM_TIMEOUT": 30}
    with patch("pazufa_scraper_be.pipelines._base.LLMConnector") as connector:
        pipeline = LLMPipeline(make_crawler(settings))

    assert pipeline.llm_connector is connector.return_value
    connector.assert_called_once_with(model="model", api_key="token", timeout_seconds=30)
