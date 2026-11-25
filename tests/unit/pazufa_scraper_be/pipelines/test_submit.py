import asyncio
import json
import uuid
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from scrapy import Spider
from scrapy.crawler import Crawler
from scrapy.settings import Settings
from scrapy.statscollectors import StatsCollector

from pazufa_scraper_be.pipelines import submit
from pazufa_scraper_be.pipelines.submit import SubmitVorgang

from .test_dump import _make_vorgang


def _make_pipeline(tmp_path: Path, *, debug: bool) -> SubmitVorgang:
    settings = {
        "WAHLPERIODE": 19,
        "DEBUG": debug,
        "API_URL": "http://localhost:8080",
        "API_TOKEN": "test-token",
        "SCRAPER_UUID": uuid.uuid4(),
    }
    crawler = Crawler(Spider, Settings(settings))
    crawler.stats = StatsCollector(crawler)
    crawler.stats.set_value("temp_error_directory", tmp_path / "errors")

    return SubmitVorgang(crawler)


@pytest.fixture
def rejecting_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the PaZuFa API reject every submitted Vorgang with 422."""

    async def asyncio_detailed(**_: Any) -> SimpleNamespace:  # noqa: ANN401
        return SimpleNamespace(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, content=b"{}")

    monkeypatch.setattr(submit.vorgang_put, "asyncio_detailed", asyncio_detailed)


@pytest.mark.usefixtures("rejecting_backend")
def test__submit_vorgang__saves_rejected_vorgang_if_debug_is_on(tmp_path: Path) -> None:
    """Test a rejected Vorgang older than the grace period is saved as JSON if DEBUG is set."""
    pipeline = _make_pipeline(tmp_path, debug=True)

    asyncio.run(pipeline.process_item(vorgang=_make_vorgang()))

    error_file = tmp_path / "errors" / str(HTTPStatus.UNPROCESSABLE_ENTITY.value) / "V-457263.json"
    assert json.loads(error_file.read_text(encoding="utf-8"))["titel"] == _make_vorgang().titel


@pytest.mark.usefixtures("rejecting_backend")
def test__submit_vorgang__saves_nothing_if_debug_is_off(tmp_path: Path) -> None:
    """Test a rejected Vorgang is not written to disk if DEBUG is not set."""
    pipeline = _make_pipeline(tmp_path, debug=False)

    asyncio.run(pipeline.process_item(vorgang=_make_vorgang()))

    assert not (tmp_path / "errors").exists()
