from collections.abc import Iterator
from typing import ClassVar, Self

from pazufa_corelib.llm import KURZTITEL_PROMPT, KurztitelResult, LLMConnector
from pydantic import HttpUrl

from pazufa_scraper_be.cache import Cache, Key
from pazufa_scraper_be.pardok import AnyGesetzDokument, DrsDokument, GesetzVorgang, GVBlDokument
from pazufa_scraper_be.pipelines.documents._llm_task import CachedLLMTaskPipeline
from pazufa_scraper_be.pipelines.stats_counter import SHORT_TITEL_COUNTERS, LLMTaskCounters

_NO_ABSTRACT = "<Leider ist kein Abstract verfügbar. Nutze nur den Titel oben.>"


class CreateShortTitel(CachedLLMTaskPipeline):
    """Pipeline that creates Kurztitel for titled Gesetz- und Verordnungsblatt (GVBl) and Drucksachen documents via an LLM."""

    ignore_key: ClassVar[Key] = Key.SHORT_TITEL_IGNORE
    counters: ClassVar[LLMTaskCounters] = SHORT_TITEL_COUNTERS
    task_name: ClassVar[str] = "LLM creation of short title"

    def targets(self: Self, vorgang: GesetzVorgang) -> Iterator[tuple[AnyGesetzDokument, HttpUrl]]:
        """Yield the primary URL of GVBl and Drs documents that have a titel."""
        for dokument in vorgang.dokumente:
            if isinstance(dokument, (GVBlDokument, DrsDokument)) and dokument.titel and dokument.lok_url:
                yield dokument, dokument.lok_url

    def is_cached(self: Self, cache: Cache) -> bool:
        """Check whether a short titel exists."""
        return Key.SHORT_TITEL in cache

    async def generate(self: Self, connector: LLMConnector, dokument: AnyGesetzDokument, cache: Cache) -> str:  # noqa: ARG002
        """Create the short titel from the document titel."""
        prompt = KURZTITEL_PROMPT.format(titel=getattr(dokument, "titel", ""), abstract=_NO_ABSTRACT)
        result = await connector.extract(prompt, KurztitelResult)
        return result.kurztitel

    def store(self: Self, cache: Cache, result: str) -> None:
        """Cache the short titel."""
        cache[Key.SHORT_TITEL] = result
