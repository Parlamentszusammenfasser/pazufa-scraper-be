import logging
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Self

from pazufa_corelib.api_client.api.vorgang import vorgang_put
from pazufa_corelib.api_client.models.vorgang import Vorgang
from scrapy.exceptions import DropItem

from pazufa_scraper_be.constants import SUBMISSION_ERROR_GRACE_PERIOD_DAYS
from pazufa_scraper_be.pipelines._base import ApiPipeline, StatsPipeline
from pazufa_scraper_be.pipelines.stats_counter import VorgangCounter

logger = logging.getLogger(__name__)


class SubmitVorgang(ApiPipeline, StatsPipeline):
    """Pipeline that submits a built Vorgang to the PaZuFa API."""

    async def process_item(self: Self, vorgang: Vorgang) -> None:
        """Submit the Vorgang to the PaZuFa API via HTTP PUT."""
        if not isinstance(vorgang, Vorgang):
            msg = f"Expected {Vorgang.__name__} object but got {vorgang.__class__.__name__}."
            raise DropItem(msg)

        if client := self.get_client():
            async with client:
                self.increment_stats(VorgangCounter.SUBMIT_ATTEMPT)
                response = await vorgang_put.asyncio_detailed(client=client, body=vorgang, x_scraper_id=str(self._scraper_uuid))

            if response.status_code == HTTPStatus.CREATED:
                self.increment_stats(VorgangCounter.SUBMIT_ACCEPTED)

            else:
                id_ = vorgang.ids[0].id if vorgang.ids else vorgang.api_id
                url_part = f"URL: {vorgang.links[0]} " if vorgang.links else ""

                msg = f"[{id_}]: Got {response.status_code} status code when submitting to PaZuFa API. {url_part}Response: {response.content.decode('utf-8')}"

                last_update = vorgang.stationen[-1].zp_start.date()
                days_since_last_update = (datetime.now(UTC).date() - last_update).days
                if days_since_last_update < SUBMISSION_ERROR_GRACE_PERIOD_DAYS:
                    self.increment_stats(VorgangCounter.SUBMIT_ERROR)
                    logger.info(msg)

                else:
                    self.increment_stats(VorgangCounter.submit_rejected_code(response.status_code))
                    logger.warning(msg)
