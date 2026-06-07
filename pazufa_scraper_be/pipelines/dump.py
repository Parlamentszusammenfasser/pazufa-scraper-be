import json
import logging
import re
from datetime import datetime
from typing import Self

from anyio import Path
from pazufa_corelib.api_client.models.vorgang import Vorgang
from scrapy.exceptions import DropItem

from pazufa_scraper_be.pipelines._base import BasePipeline

logger = logging.getLogger(__name__)

RUN_DIR_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S"


def vorgang_to_json(*, vorgang: Vorgang, include_volltext: bool) -> str:
    """Serialize the payload that would be submitted to the API as deterministic JSON.

    Keys are sorted, so two dumps of the same data can be compared with a plain diff.

    Args:
        vorgang: Vorgang as it would be submitted.
        include_volltext: Whether to keep the (large) ``volltext`` of the Dokumente. The text hash stays part of every Dokument either way.

    Returns:
        JSON string with a trailing newline.
    """
    payload = vorgang.to_dict()

    if not include_volltext:
        for station in payload.get("stationen", []):
            for dokument in station.get("dokumente", []):
                if isinstance(dokument, dict):
                    dokument.pop("volltext", None)

    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def get_dump_file_name(*, vorgang: Vorgang) -> str:
    """Return a file system safe file name for the Vorgang, based on its PARDOK id."""
    id_ = vorgang.ids[0].id if vorgang.ids else str(vorgang.api_id)
    return re.sub(r"[^\w.-]", "_", id_) + ".json"


class DumpVorgang(BasePipeline):
    """Pipeline that saves the Vorgang payload as JSON file, e.g. to inspect or compare end-to-end test runs.

    Does nothing unless the DEBUG setting is true. Files are saved to ``<DEBUG_DIR>/<start of the run>/<Vorgang id>.json``.
    """

    def init(self: Self) -> None:
        """Read DEBUG_DIR and DEBUG_INCLUDE_VOLLTEXT settings."""
        super().init()

        self._debug_dir: Path | None = None
        if self.debug:
            debug_dir = self.crawler.settings.get("DEBUG_DIR", None)
            if debug_dir is None:
                msg = "If DEBUG is set, DEBUG_DIR setting is required."
                raise ValueError(msg)

            self._debug_dir = Path(debug_dir)

        self._include_volltext = self.crawler.settings.getbool("DEBUG_INCLUDE_VOLLTEXT", default=False)
        self._run_dir: Path | None = None

    def _get_run_dir(self: Self) -> Path:
        if self._run_dir is None:
            start_time = self.crawler.stats.get_value("start_time")
            if not isinstance(start_time, datetime):
                msg = f"Expected stats value for 'start_time' to be 'datetime', got {type(start_time)}."
                raise TypeError(msg)

            if self._debug_dir is None:
                msg = "DEBUG is not set."
                raise ValueError(msg)

            self._run_dir = self._debug_dir / start_time.strftime(RUN_DIR_TIMESTAMP_FORMAT)

        return self._run_dir

    async def process_item(self: Self, vorgang: Vorgang) -> Vorgang:
        """Write the Vorgang to a JSON file and pass it on unchanged."""
        if not isinstance(vorgang, Vorgang):
            msg = f"Expected {Vorgang.__name__} object but got {vorgang.__class__.__name__}."
            raise DropItem(msg)

        if not self.debug:
            return vorgang

        run_dir = self._get_run_dir()
        await run_dir.mkdir(parents=True, exist_ok=True)

        dump_file = run_dir / get_dump_file_name(vorgang=vorgang)
        await dump_file.write_text(vorgang_to_json(vorgang=vorgang, include_volltext=self._include_volltext), encoding="utf-8")

        return vorgang
