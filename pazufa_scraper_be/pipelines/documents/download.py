import logging
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Self

from pydantic import HttpUrl
from scrapy import Request
from scrapy.core.engine import ExecutionEngine
from scrapy.exceptions import DropItem
from scrapy.http import Response
from scrapy.http.request import NO_CALLBACK

from pazufa_scraper_be.cache import DocumentCache
from pazufa_scraper_be.constants import DOCUMENT_CHECK_MODIFIED_EVERY_DAYS
from pazufa_scraper_be.pardok import GesetzVorgang
from pazufa_scraper_be.pipelines._base import CacheDirPipeline, StatsPipeline
from pazufa_scraper_be.pipelines.stats_counter import DokumentCounter

logger = logging.getLogger(__name__)

LAST_MODIFIED_TIME_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"


# TODO: refactor
async def _reset_cache_if_file_got_modified(document_cache: DocumentCache, dokument_url: HttpUrl, engine: ExecutionEngine) -> bool:
    download_time_from_cache = document_cache.download_time_read()
    last_check_time_from_cache = document_cache.last_remote_check()

    if not download_time_from_cache:
        return False

    check_due = last_check_time_from_cache is None or (datetime.now(UTC) - last_check_time_from_cache) >= timedelta(days=DOCUMENT_CHECK_MODIFIED_EVERY_DAYS)
    download_grace_period_done = (datetime.now(UTC) - download_time_from_cache) >= timedelta(days=DOCUMENT_CHECK_MODIFIED_EVERY_DAYS)

    if not download_grace_period_done or not check_due:
        return False

    request = Request(dokument_url.encoded_string(), method="HEAD", callback=NO_CALLBACK)
    response = await engine.download_async(request)
    if last_modified_header_as_byte := response.headers.get("Last-Modified"):
        last_modified_time_from_header = datetime.strptime(last_modified_header_as_byte.decode("utf-8"), LAST_MODIFIED_TIME_FORMAT).astimezone(tz=UTC)

        if document_cache.last_modified_read() != last_modified_time_from_header:
            document_cache.reset()
            document_cache.checked_remote()
            return True

    document_cache.checked_remote()
    return False


class DownloadAndCacheDocuments(CacheDirPipeline, StatsPipeline):
    """Pipeline that downloads and caches PDF documents for each Vorgang."""

    # TODO(anyone): refactor to reduce complexity
    async def process_item(self: Self, vorgang: GesetzVorgang) -> GesetzVorgang:  # noqa: C901
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
                document_cache = self.get_document_cache(document=dokument, document_url=dokument_url)

                # TODO
                # if dokument_cache_dir is None:
                #     msg = f"[{vorgang.id} - {dokument.id}]: Did not get cache dir for additional URL: {dokument_url}"
                #     logger.warning(msg)
                #     continue

                if document_cache.document_exists():
                    if await _reset_cache_if_file_got_modified(document_cache, dokument_url, engine=self.crawler.engine):
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
                    document_cache.last_modified_write(
                        datetime.strptime(last_modified_header_as_byte.decode("utf-8"), LAST_MODIFIED_TIME_FORMAT).astimezone(UTC)
                    )

                self.increment_stats(DokumentCounter.DOWNLOAD_DONE)
                document_cache.url_write(response.url)
                document_cache.download_time_write(download_time)
                document_cache.document_write(response.body)

        return vorgang
