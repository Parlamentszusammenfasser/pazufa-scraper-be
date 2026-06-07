from collections.abc import Iterator
from typing import ClassVar, NamedTuple, Self

from pazufa_corelib.llm import LLMConnector
from pydantic import HttpUrl

from pazufa_scraper_be.cache import Cache, Key
from pazufa_scraper_be.pardok import AnyGesetzDokument, GesetzVorgang, GVBlDokument
from pazufa_scraper_be.pardok.dokument import Protokoll
from pazufa_scraper_be.pipelines.documents._llm_task import CachedLLMTaskPipeline, SkipTaskError
from pazufa_scraper_be.pipelines.stats_counter import SUMMARY_COUNTERS, LLMCounter, LLMTaskCounters


class VorgangContext(NamedTuple):
    """Titel and Drucksachen number identifying a Vorgang."""

    titel: str
    nr: str | None


def vorgang_context(vorgang: GesetzVorgang) -> VorgangContext | None:
    """Return titel and number of the first document carrying a titel, or None if no document has one."""
    for dokument in vorgang.dokumente:
        if titel := getattr(dokument, "titel", None):
            return VorgangContext(titel=titel, nr=dokument.nr)

    return None


class SummarizeExtractedPDFText(CachedLLMTaskPipeline):
    """Pipeline that summarizes extracted document text via an LLM."""

    ignore_key: ClassVar[Key] = Key.SUMMARY_IGNORE
    counters: ClassVar[LLMTaskCounters] = SUMMARY_COUNTERS
    task_name: ClassVar[str] = "LLM summarization"

    def targets(self: Self, vorgang: GesetzVorgang) -> Iterator[tuple[AnyGesetzDokument, HttpUrl]]:
        """Yield all URLs of all documents."""
        for dokument in vorgang.dokumente:
            for dokument_url in dokument.all_urls:
                yield dokument, dokument_url

    def has_input(self: Self, cache: Cache) -> bool:
        """Check whether extracted text exists."""
        return Key.TEXT in cache

    def is_cached(self: Self, cache: Cache) -> bool:
        """Check whether a summary of the configured model exists."""
        return cache.exist_model_specific_summary(llm_model_name=self.llm_model_name)

    def on_cache_hit(self: Self, cache: Cache) -> None:
        """Link the existing model specific summary."""
        cache.link_model_specific_summary_file(llm_model_name=self.llm_model_name)

    def store(self: Self, cache: Cache, result: str) -> None:
        """Store and link the model specific summary."""
        cache.set_model_specific_summary(llm_model_name=self.llm_model_name, summary=result)
        cache.link_model_specific_summary_file(llm_model_name=self.llm_model_name)

    async def generate(self: Self, connector: LLMConnector, dokument: AnyGesetzDokument, cache: Cache) -> str:
        """Summarize the extracted text, dispatching by document type."""
        context = vorgang_context(vorgang=dokument.vorgang)

        if context is None:
            raise SkipTaskError(reason="Ignoring because no document of the Vorgang has a titel.")

        text = cache.get_text(Key.TEXT)

        if isinstance(dokument, Protokoll):
            text = await self._extract_relevant_section(connector=connector, text=text, context=context)

        self.increment_stats(LLMCounter.summarize_art(dokument.art_l.lower()))

        if isinstance(dokument, GVBlDokument):
            return await connector.summarize_gesetzentwurf(titel=context.titel, text=text)

        return await connector.summarize_dokument(titel=context.titel, text=text)

    async def _extract_relevant_section(self: Self, connector: LLMConnector, text: str, context: VorgangContext) -> str:
        self.increment_stats(LLMCounter.EXTRACT_RELEVANT_SECTION_TOTAL)
        relevant_section = await connector.extract_relevant_section(text=text, vorgang_titel=context.titel, vorgang_vnr=context.nr)

        if not relevant_section:
            raise SkipTaskError(reason="Ignoring because no relevant section was found.", counter=LLMCounter.EXTRACT_RELEVANT_SECTION_FAILED)

        self.increment_stats(LLMCounter.EXTRACT_RELEVANT_SECTION_DONE)
        return relevant_section
