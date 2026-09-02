import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Self

from scrapy import Spider, signals
from scrapy.crawler import Crawler

logger = logging.getLogger(__name__)


class TempErrorDirectory:
    """Create a temporary directory which will be used to save rejected Vorgang objects."""

    def __init__(self: Self, crawler: Crawler) -> None:
        """Initialize and connect to spider_closed signal."""
        self.crawler = crawler

        crawler.signals.connect(self._spider_opened, signal=signals.spider_opened)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        """Create a TempErrorDirectory from a Scrapy crawler."""
        return cls(crawler)

    def _spider_opened(self, spider: Spider) -> None:
        start_time = spider.crawler.stats.get_value("start_time")
        if not isinstance(start_time, datetime):
            msg = f"Expected stats value for 'start_time' to be 'datetime', got {type(start_time)}."
            raise TypeError(msg)

        tmp_dir = Path(tempfile.gettempdir()) / f"PaZuFa-{spider.name}" / start_time.isoformat()
        tmp_dir.mkdir(parents=True)

        self.crawler.stats.set_value("temp_error_directory", tmp_dir)
