import logging
from pathlib import Path
from typing import Self

import magic
import xberg
from scrapy.exceptions import DropItem
from xberg import ExtractInput, ExtractInputKind, ExtractionConfig, OcrConfig, PageConfig

from pazufa_scraper_be.constants import DOKUMENT_FILE_NAME, TEXT_FILE_NAME
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


async def _extract_text(document_file: Path, *, ocr: bool) -> str:
    extract_input = ExtractInput(kind=ExtractInputKind.URI, uri=str(document_file))
    extraction_result = await xberg.extract(
        input=extract_input,
        config=_get_xberg_config(ocr=ocr),
    )
    extraction_result = extraction_result.results[0]
    text = "\n".join([page.content for page in extraction_result.pages or []])

    # In the few cases, where we could not extract text, apply OCR
    if len(text) == 0 and not ocr:
        return await _extract_text(document_file=document_file, ocr=True)

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
                dokument_cache_dir = self.get_dokument_cache_dir(dokument=dokument, url=dokument_url)
                if dokument_cache_dir is None:
                    msg = f"[{vorgang.id} - {dokument.id}]: Did not get cache dir for additional URL: {dokument_url}"
                    logger.warning(msg)
                    continue

                dokument_file = dokument_cache_dir / DOKUMENT_FILE_NAME
                dokument_text_file = dokument_cache_dir / TEXT_FILE_NAME

                if dokument_file.exists():
                    if dokument_text_file.exists():
                        self.increment_stats(TextCounter.CACHE_HIT)
                        continue

                    self.increment_stats(TextCounter.CACHE_MISS)
                    text = await _extract_text(document_file=dokument_file, ocr=False)

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

                    elif magic.from_buffer(text, mime=True) != "text/plain":
                        error_file = self.get_errors_dir() / f"{dokument.id}.text"
                        error_file.write_text(text)

                        # NOTE: This is a hack, where the mime type of the saved file gets 'text/plain', which is causing issues
                        if magic.from_file(error_file, mime=True) == "text/plain":
                            error_file.rename(dokument_text_file)

                        else:
                            self.increment_stats(TextCounter.EXTRACT_FAILED_NOT_PLAIN_TEXT)
                            msg = f"[{vorgang.id} - {dokument.id}]: Extracted text is not plain text."
                            logger.warning(msg)

                    else:
                        self.increment_stats(TextCounter.EXTRACT_DONE)
                        dokument_text_file.write_text(text)

        return vorgang
