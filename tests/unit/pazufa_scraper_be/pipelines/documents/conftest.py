import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from scrapy import Spider
from scrapy.crawler import Crawler
from scrapy.settings import Settings
from scrapy.statscollectors import StatsCollector

from pazufa_scraper_be.cache import Cache, Key
from pazufa_scraper_be.pardok import GesetzVorgang
from tests.unit.pazufa_scraper_be.helpers import build_gesetz_vorgang_data

WAHLPERIODE = 19
LLM_MODEL_NAME = "provider/test-model"


@pytest.fixture
def crawler(tmp_path: Path) -> Crawler:
    """Return a crawler configured with WAHLPERIODE and a temporary cache directory, without LLM token."""
    crawler = Crawler(Spider, Settings({"WAHLPERIODE": WAHLPERIODE, "CACHE_DIR": str(tmp_path)}))
    crawler.stats = StatsCollector(crawler)
    return crawler


@pytest.fixture
def connector() -> AsyncMock:
    """Return a fake LLM connector."""
    return AsyncMock()


@pytest.fixture
def build_vorgang(base_vorgang_data: dict[str, Any]) -> Callable[..., GesetzVorgang]:
    """Return a factory building a GesetzVorgang from document data, giving each document a unique URL."""

    def _build(*dok_datas: dict[str, Any]) -> GesetzVorgang:
        unique_dok_datas = [{**dok_data, "DBID": f"doc{index}", "LokURL": f"https://example.com/doc{index}.pdf"} for index, dok_data in enumerate(dok_datas)]
        data = build_gesetz_vorgang_data(base_vorgang_data=base_vorgang_data, dok_datas=unique_dok_datas, neben_eintrag_data=[])
        return GesetzVorgang(**data)

    return _build


def stat(crawler: Crawler, counter: str) -> int:
    """Return the value of a stats counter, defaulting to 0."""
    return crawler.stats.get_value(str(counter), 0)


def force_expire(cache: Cache, key: Key) -> None:
    """Rewrite metadata to make an entry appear expired."""
    meta_file = cache.backend.directory / f".{key}.metadata"
    data = json.loads(meta_file.read_text())
    data["expires_at"] = "2020-01-01T00:00:00+00:00"
    meta_file.write_text(json.dumps(data))
