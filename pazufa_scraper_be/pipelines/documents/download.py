import hashlib
import logging
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Self

from pydantic import HttpUrl
from scrapy import Request
from scrapy.core.engine import ExecutionEngine
from scrapy.exceptions import DropItem
from scrapy.http import Response
from scrapy.http.request import NO_CALLBACK

from pazufa_scraper_be.constants import (
    DOCUMENT_CHECK_MODIFIED_EVERY_DAYS,
    DOK_CACHE_HISTORY_SUB_DIR_NAME,
    DOKUMENT_FILE_NAME,
    DOWNLOAD_TIME_FILE_NAME,
    FILE_BYTE_HASH_FILE_NAME,
    LAST_CHECKED_FILE_NAME,
    LAST_MODIFIED_FILE_NAME,
    URL_FILE_NAME,
)
from pazufa_scraper_be.pardok import GesetzVorgang
from pazufa_scraper_be.pipelines._base import CacheDirPipeline, StatsPipeline
from pazufa_scraper_be.pipelines.stats_counter import DokumentCounter

logger = logging.getLogger(__name__)


def _reset_cache_dir(cache_dir: Path) -> None:
    history_dir = cache_dir / DOK_CACHE_HISTORY_SUB_DIR_NAME
    history_dir.mkdir(parents=True, exist_ok=True)

    existing = [int(p.name) for p in history_dir.iterdir() if p.is_dir() and p.name.isdigit()]
    n = max(existing, default=0) + 1
    version_dir = history_dir / str(n)
    version_dir.mkdir()

    for file in cache_dir.iterdir():
        if file.is_file():
            file.rename(version_dir / file.name)


async def _reset_cache_if_file_got_modified(dokument_cache_dir: Path, dokument_url: HttpUrl, engine: ExecutionEngine) -> bool:
    dokument_download_time_file = dokument_cache_dir / DOWNLOAD_TIME_FILE_NAME
    dokument_last_modified_file = dokument_cache_dir / LAST_MODIFIED_FILE_NAME
    dokument_last_checked_file = dokument_cache_dir / LAST_CHECKED_FILE_NAME

    download_time_from_cache = datetime.fromisoformat(dokument_download_time_file.read_text()).astimezone(UTC)
    last_check_time_from_cache = datetime.fromisoformat(dokument_last_checked_file.read_text()).astimezone(UTC) if dokument_last_checked_file.exists() else None

    check_due = last_check_time_from_cache is None or (datetime.now(UTC) - last_check_time_from_cache) >= timedelta(days=DOCUMENT_CHECK_MODIFIED_EVERY_DAYS)
    download_grace_period_done = (datetime.now(UTC) - download_time_from_cache) >= timedelta(days=DOCUMENT_CHECK_MODIFIED_EVERY_DAYS)

    if not download_grace_period_done or not check_due:
        return False

    # Check if remote file got modified, if so reset cache
    dokument_last_checked_file.write_text(datetime.now(UTC).isoformat())
    last_modified_time_from_cache = datetime.fromisoformat(dokument_last_modified_file.read_text()).astimezone(UTC)

    request = Request(dokument_url.encoded_string(), method="HEAD", callback=NO_CALLBACK)
    response = await engine.download_async(request)
    if last_modified_header_as_byte := response.headers.get("Last-Modified"):
        last_modified_time_from_header = datetime.strptime(last_modified_header_as_byte.decode("utf-8"), "%a, %d %b %Y %H:%M:%S %Z").astimezone(UTC)

        if last_modified_time_from_cache != last_modified_time_from_header:
            _reset_cache_dir(dokument_cache_dir)
            return True

    return False


class DownloadAndCacheDocuments(CacheDirPipeline, StatsPipeline):
    """Pipeline that downloads and caches PDF documents for each Vorgang."""

    # TODO(anyone): refactor to reduce complexity
    async def process_item(self: Self, vorgang: GesetzVorgang) -> GesetzVorgang:  # noqa: C901, PLR0912, PLR0915
        """Download and cache all document PDFs for the given Vorgang."""
        if not isinstance(vorgang, GesetzVorgang):
            msg = f"Expected {GesetzVorgang.__name__} object but got {vorgang.__class__.__name__}."
            raise DropItem(msg)

        if self.crawler.engine is None:
            msg = "crawler.engine is None. The crawler seems improperly initialized."
            raise ValueError(msg)

        for dokument in vorgang.dokumente:
            if dokument.wp != self.wahlperiode:
                msg = (
                    f"[{vorgang.id} - {dokument.id}]: Wahlperiode from scraping run ('{self.wahlperiode}') "
                    + f"differs from this document's metadata: '{dokument.wp}'"
                )
                logger.warning(msg)
                continue

            for dokument_url in dokument.all_urls:
                dokument_cache_dir = self.get_dokument_cache_dir(dokument=dokument, url=dokument_url)
                if dokument_cache_dir is None:
                    msg = f"[{vorgang.id} - {dokument.id}]: Did not get cache dir for additional URL: {dokument_url}"
                    logger.warning(msg)
                    continue

                dokument_file = dokument_cache_dir / DOKUMENT_FILE_NAME
                dokument_url_file = dokument_cache_dir / URL_FILE_NAME
                dokument_download_time_file = dokument_cache_dir / DOWNLOAD_TIME_FILE_NAME
                dokument_last_modified_file = dokument_cache_dir / LAST_MODIFIED_FILE_NAME
                dokument_file_byte_hash_file = dokument_cache_dir / FILE_BYTE_HASH_FILE_NAME

                # TODO(anyone): https://codeberg.org/PaZuFa/pazufa-scraper-be/issues/30
                if dokument_file.exists():
                    self.increment_stats(DokumentCounter.CACHE_HIT)
                    continue

                if dokument_file.exists():
                    if await _reset_cache_if_file_got_modified(dokument_cache_dir=dokument_cache_dir, dokument_url=dokument_url, engine=self.crawler.engine):
                        self.increment_stats(DokumentCounter.CACHE_RESET)

                    else:
                        self.increment_stats(DokumentCounter.CACHE_HIT)
                        continue
                else:
                    self.increment_stats(DokumentCounter.CACHE_MISS)

                download_time = datetime.now(tz=UTC)
                request = Request(dokument_url.encoded_string(), callback=NO_CALLBACK)
                response = await self.crawler.engine.download_async(request)

                if not isinstance(response, Response):
                    self.increment_stats(DokumentCounter.DOWNLOAD_FAILED_INCORRECT_RESPONSE)
                    msg = f"[{vorgang.id} - {dokument.id}]: Expected 'scrapy.Response' but got '{type(response)}'"
                    logger.warning(msg)
                    continue

                if response.status != HTTPStatus.OK:
                    self.increment_stats(DokumentCounter.DOWNLOAD_FAILED_INCORRECT_STATUS)
                    msg = f"[{vorgang.id} - {dokument.id}]: Got {response.status} status code for URL: {response.url}"
                    logger.warning(msg)
                    continue

                if last_modified_header_as_byte := response.headers.get("Last-Modified"):
                    last_modified_as_iso = (
                        datetime.strptime(last_modified_header_as_byte.decode("utf-8"), "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=UTC).isoformat()
                    )
                    dokument_last_modified_file.write_text(last_modified_as_iso)

                dokument_file_byte_hash = hashlib.sha256(response.body).hexdigest()
                dokument_file_byte_hash_file.write_text(dokument_file_byte_hash)

                self.increment_stats(DokumentCounter.DOWNLOAD_DONE)
                dokument_url_file.write_text(response.url)
                dokument_download_time_file.write_text(download_time.isoformat())
                dokument_file.write_bytes(response.body)

        return vorgang
