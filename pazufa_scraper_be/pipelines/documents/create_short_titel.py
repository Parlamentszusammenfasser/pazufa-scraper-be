import logging
from datetime import timedelta
from typing import Self

from pazufa_corelib.llm import KURZTITEL_PROMPT, KurztitelResult, LLMProviderError, LLMQuotaExceededError, LLMRateLimitError, LLMTemporaryProviderError
from scrapy.exceptions import DropItem

from pazufa_scraper_be.cache import Key
from pazufa_scraper_be.pardok import DrsDokument, GesetzVorgang, GVBlDokument
from pazufa_scraper_be.pipelines._base import CachePipeline, LLMPipeline, StatsPipeline
from pazufa_scraper_be.pipelines.stats_counter import LLMCounter, ShortTitelCounter

logger = logging.getLogger(__name__)


class CreateShortTitel(CachePipeline, LLMPipeline, StatsPipeline):
    """Pipeline that create Kurztitel via an LLM."""

    async def process_item(self: Self, vorgang: GesetzVorgang) -> GesetzVorgang:  # noqa: C901, PLR0912
        """Create Kurztitel for Gesetz- und Verordnungsblatt (GVBl) and Drucksachen documents in the Vorgang and cache the result."""
        if not isinstance(vorgang, GesetzVorgang):
            msg = f"Expected {GesetzVorgang.__name__} object but got {vorgang.__class__.__name__}."
            raise DropItem(msg)

        if self.llm_connector is None:
            return vorgang

        for dokument in vorgang.dokumente:
            if isinstance(dokument, (GVBlDokument, DrsDokument)) and isinstance(dokument.titel, str) and dokument.lok_url:
                cache = self.get_cache(document=dokument, document_url=dokument.lok_url)

                if Key.SHORT_TITEL_IGNORE in cache:
                    if cache.is_expired(Key.SHORT_TITEL_IGNORE):
                        cache.delete_entry(key=Key.SHORT_TITEL_IGNORE)
                        self.increment_stats(ShortTitelCounter.RESET_TEMPORARY_IGNORE)

                    else:
                        self.increment_stats(ShortTitelCounter.IGNORE)
                        continue

                if Key.SHORT_TITEL in cache:
                    self.increment_stats(ShortTitelCounter.CACHE_HIT)
                    continue

                try:
                    self.increment_stats(ShortTitelCounter.CACHE_MISS)
                    self.increment_stats(LLMCounter.SHORT_TITEL_TOTAL)
                    abstract = "<Leider ist kein Abstract verfügbar. Nutze nur den Titel oben.>"
                    prompt = KURZTITEL_PROMPT.format(titel=dokument.titel, abstract=abstract)
                    result = await self.llm_connector.extract(prompt, KurztitelResult)

                except LLMTemporaryProviderError as error:
                    self.increment_stats(LLMCounter.SHORT_TITEL_FAILED_TEMPORARY)
                    msg = f"[{vorgang.id} - {dokument.id}]: LLM creation of short title failed due to temporary provider problem."
                    logger.warning(msg)

                    cache.set_text(key=Key.SHORT_TITEL_IGNORE, value=repr(error), ttl=timedelta(hours=12))

                except LLMQuotaExceededError as error:
                    self.increment_stats(LLMCounter.SHORT_TITEL_FAILED_QUOTA)
                    msg = f"[{vorgang.id} - {dokument.id}]: LLM creation of short title failed due to quota exceeded."
                    logger.warning(msg)

                    cache.set_text(key=Key.SHORT_TITEL_IGNORE, value=repr(error), ttl=timedelta(hours=24))

                except LLMRateLimitError as error:
                    self.increment_stats(LLMCounter.SHORT_TITEL_FAILED_RATE_LIMIT)
                    msg = f"[{vorgang.id} - {dokument.id}]: LLM creation of short title failed due to rate limit."
                    logger.warning(msg)

                    cache.set_text(key=Key.SHORT_TITEL_IGNORE, value=repr(error), ttl=timedelta(hours=1))

                except LLMProviderError as error:
                    self.increment_stats(LLMCounter.SHORT_TITEL_FAILED_PROVIDER)
                    msg = f"[{vorgang.id} - {dokument.id}]: LLM creation of short title failed due to provider problem."
                    logger.warning(msg)

                    cache[Key.SHORT_TITEL_IGNORE] = repr(error)

                else:
                    self.increment_stats(LLMCounter.SHORT_TITEL_DONE)
                    cache[Key.SHORT_TITEL] = result.kurztitel

        return vorgang
