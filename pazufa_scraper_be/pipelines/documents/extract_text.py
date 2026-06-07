import logging
from typing import Self

import xberg
from scrapy.exceptions import DropItem
from xberg import ExtractInput, ExtractInputKind, ExtractionConfig, OcrConfig, PageConfig

from pazufa_scraper_be.pardok import GesetzVorgang
from pazufa_scraper_be.pipelines._base import CacheDirPipeline, StatsPipeline
from pazufa_scraper_be.pipelines.stats_counter import TextCounter

logger = logging.getLogger(__name__)


def _get_xberg_config(*, ocr: bool) -> ExtractionConfig:
    page_config = PageConfig(extract_pages=True)

    if ocr:
        ocr_config = OcrConfig(
            backend="tesseract",
            language=["deu"],
        )
        force_ocr = True

    else:
        ocr_config = None
        force_ocr = False

    return ExtractionConfig(enable_quality_processing=True, pages=page_config, use_cache=False, ocr=ocr_config, force_ocr=force_ocr)


async def _extract_text(document_bytes: bytes, *, ocr: bool) -> str:
    extract_input = ExtractInput(kind=ExtractInputKind.BYTES, bytes=document_bytes)
    extraction_result = await xberg.extract(
        input=extract_input,
        config=_get_xberg_config(ocr=ocr),
    )
    extraction_result = extraction_result.results[0]
    text = "\n".join([page.content for page in extraction_result.pages or []])

    # In the few cases, where we could not extract text, apply OCR
    if len(text) == 0 and not ocr:
        return await _extract_text(document_bytes=document_bytes, ocr=True)

    return text


class ExtractTextFromPDF(CacheDirPipeline, StatsPipeline):
    """Pipeline that extracts plain text from cached PDF documents using xberg."""

    async def process_item(self: Self, vorgang: GesetzVorgang) -> GesetzVorgang:
        """Extract text from cached PDFs for each document in the Vorgang."""
        if not isinstance(vorgang, GesetzVorgang):
            msg = f"Expected {GesetzVorgang.__name__} object but got {vorgang.__class__.__name__}."
            raise DropItem(msg)

        for dokument in vorgang.dokumente:
            for dokument_url in dokument.all_urls:
                document_cache = self.get_document_cache(document=dokument, document_url=dokument_url)

                # TODO
                # if dokument_cache_dir is None:
                #     msg = f"[{vorgang.id} - {dokument.id}]: Did not get cache dir for additional URL: {dokument_url}"
                #     logger.warning(msg)
                #     continue

                if document_cache.document_exists():
                    if document_cache.text_exists():
                        self.increment_stats(TextCounter.CACHE_HIT)
                        continue

                    self.increment_stats(TextCounter.CACHE_MISS)
                    text = await _extract_text(document_bytes=document_cache.document_read(), ocr=False)

                    # fmt: off
                    # Some postprocessing that was necessary after eyeballing documents
                    text = (
                        text
                        .strip()                                                      # remove leading/trailing spaces
                        .replace("\x02", "")                                          # hyphens (line-breaks with -)
                        .replace("\x15", "").replace("\x16", "").replace("\x18", "")  # showed up when bold face Drucksache Nummer could not be extracted
                    )
                    # fmt: on

                    if len(text) == 0:
                        self.increment_stats(TextCounter.EXTRACT_FAILED_EMPTY_TEXT)
                        msg = f"[{vorgang.id} - {dokument.id}]: No text extracted."
                        logger.warning(msg)

                    else:
                        self.increment_stats(TextCounter.EXTRACT_DONE)
                        document_cache.text_write(text)

        return vorgang
