import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import ClassVar, Self

from pazufa_corelib.llm import LLMConnector, LLMConnectorError, LLMProviderError, LLMQuotaExceededError, LLMRateLimitError, LLMTemporaryProviderError
from pydantic import HttpUrl
from scrapy.exceptions import DropItem

from pazufa_scraper_be.cache import Cache, Key
from pazufa_scraper_be.pardok import AnyGesetzDokument, GesetzVorgang
from pazufa_scraper_be.pipelines._base import CachePipeline, LLMPipeline, StatsPipeline
from pazufa_scraper_be.pipelines.documents.utils import IgnoreStatus, resolve_ignore, set_llm_error_ignore
from pazufa_scraper_be.pipelines.stats_counter import LLMTaskCounters, StatsCounter

logger = logging.getLogger(__name__)


class SkipTaskError(Exception):
    """Raised by ``generate`` when a document can permanently not be processed.

    The reason is stored as (permanent) ignore marker, so the document is not retried.
    """

    def __init__(self: Self, reason: str, counter: StatsCounter | None = None) -> None:
        """Init with the reason to store and an optional counter to increment."""
        super().__init__(reason)
        self.reason = reason
        self.counter = counter


def error_counter(counters: LLMTaskCounters, error: LLMConnectorError) -> StatsCounter:
    """Return the counter matching the given LLM error."""
    match error:
        case LLMTemporaryProviderError():
            return counters.failed_temporary

        case LLMQuotaExceededError():
            return counters.failed_quota

        case LLMRateLimitError():
            return counters.failed_rate_limit

        case LLMProviderError():
            return counters.failed_provider

        case _:
            return counters.failed_validation


class CachedLLMTaskPipeline(CachePipeline, LLMPipeline, StatsPipeline, ABC):
    """Base for pipelines generating one cached LLM result per document URL.

    Handles ignore markers, cache lookup, stats, and LLM error handling. Subclasses define what to
    process (``targets``), how to generate (``generate``), and how to store the result (``store``).
    """

    ignore_key: ClassVar[Key]
    counters: ClassVar[LLMTaskCounters]
    task_name: ClassVar[str]

    @abstractmethod
    def targets(self: Self, vorgang: GesetzVorgang) -> Iterator[tuple[AnyGesetzDokument, HttpUrl]]:
        """Yield the document/URL pairs to process."""

    def has_input(self: Self, cache: Cache) -> bool:  # noqa: ARG002
        """Return whether the cache holds the input required for generation."""
        return True

    @abstractmethod
    def is_cached(self: Self, cache: Cache) -> bool:
        """Return whether a result already exists."""

    def on_cache_hit(self: Self, cache: Cache) -> None:
        """Hook called when a cached result exists."""

    @abstractmethod
    async def generate(self: Self, connector: LLMConnector, dokument: AnyGesetzDokument, cache: Cache) -> str:
        """Generate the result via the LLM.

        Raises:
            SkipTaskError: If the document can permanently not be processed.
            LLMConnectorError: If the LLM call fails.
        """

    @abstractmethod
    def store(self: Self, cache: Cache, result: str) -> None:
        """Store a non-empty result in the cache."""

    async def process_item(self: Self, vorgang: GesetzVorgang) -> GesetzVorgang:
        """Process all targets of the Vorgang."""
        if not isinstance(vorgang, GesetzVorgang):
            msg = f"Expected {GesetzVorgang.__name__} object but got {vorgang.__class__.__name__}."
            raise DropItem(msg)

        if self.llm_connector is None:
            return vorgang

        for dokument, dokument_url in self.targets(vorgang=vorgang):
            cache = self.get_cache(document=dokument, document_url=dokument_url)
            await self._process(connector=self.llm_connector, dokument=dokument, cache=cache)

        return vorgang

    def _is_ignored(self: Self, cache: Cache) -> bool:
        match resolve_ignore(cache=cache, ignore_key=self.ignore_key):
            case IgnoreStatus.EXPIRED:
                self.increment_stats(self.counters.reset_temporary_ignore)
                return False

            case IgnoreStatus.ACTIVE:
                self.increment_stats(self.counters.ignore)
                return True

            case IgnoreStatus.ABSENT:
                return False

    async def _process(self: Self, connector: LLMConnector, dokument: AnyGesetzDokument, cache: Cache) -> None:
        if self._is_ignored(cache=cache) or not self.has_input(cache=cache):
            return

        if self.is_cached(cache=cache):
            self.increment_stats(self.counters.cache_hit)
            self.on_cache_hit(cache=cache)
            return

        self.increment_stats(self.counters.cache_miss)
        self.increment_stats(self.counters.total)
        log_prefix = f"[{dokument.vorgang.id} - {dokument.id}]: {self.task_name}"

        try:
            result = await self.generate(connector=connector, dokument=dokument, cache=cache)

        except SkipTaskError as skip:
            if skip.counter is not None:
                self.increment_stats(skip.counter)

            msg = f"{log_prefix} skipped: {skip.reason}"
            logger.info(msg)
            cache[self.ignore_key] = skip.reason
            return

        except LLMConnectorError as error:
            self.increment_stats(error_counter(counters=self.counters, error=error))
            msg = f"{log_prefix} failed: {error!r}"
            logger.warning(msg)
            set_llm_error_ignore(cache=cache, ignore_key=self.ignore_key, error=error)
            return

        if not result.strip():
            self.increment_stats(self.counters.failed_empty)
            msg = f"{log_prefix} returned an empty result."
            logger.warning(msg)
            return

        self.increment_stats(self.counters.done)
        self.store(cache=cache, result=result)
