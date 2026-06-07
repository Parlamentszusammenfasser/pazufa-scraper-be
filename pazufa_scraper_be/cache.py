from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from pazufa_scraper_be.cache_lib import DocumentCache as BaseDocumentCache
from pazufa_scraper_be.cache_lib import DocumentKey, Value
from pazufa_scraper_be.cache_lib import Key as BaseKey
from pazufa_scraper_be.cache_lib.backends import FileSystemBackend
from pazufa_scraper_be.constants import DOK_CACHE_HISTORY_SUB_DIR_PATH


class Key(BaseKey):
    URL = "URL"
    LAST_MODIFIED = "LAST_MODIFIED"
    LAST_CHECKED = "LAST_CHECKED"
    SUMMARY_IGNORE = "SUMMARY_IGNORE"


class DocumentCache(BaseDocumentCache[FileSystemBackend]):
    """Container for document cache."""

    def __init__(self: Self, base_dir: Path, name: str) -> None:
        self.name = name
        super().__init__(backend=FileSystemBackend(base_dir=Path(base_dir) / name))

    def checked_remote(self: Self) -> None:
        return self.write_timestamp(key=Key.LAST_CHECKED, value=datetime.now(UTC))

    def last_remote_check(self: Self) -> datetime | None:
        if self.has_entry(key=Key.LAST_CHECKED):
            return self.read_timestamp(key=Key.LAST_CHECKED)

        return None

    def url_read(self: Self) -> str:
        return self.read_text(key=Key.URL)

    def url_write(self: Self, value: str) -> None:
        return self.write_text(key=Key.URL, value=value)

    def last_modified_exists(self: Self) -> bool:
        return self.has_entry(key=Key.LAST_MODIFIED)

    def last_modified_read(self: Self) -> datetime:
        return self.read_timestamp(key=Key.LAST_MODIFIED)

    def last_modified_write(self: Self, value: datetime) -> None:
        return self.write_timestamp(key=Key.LAST_MODIFIED, value=value)

    def summary_ignore_exists(self: Self) -> bool:
        return self.has_entry(key=Key.SUMMARY_IGNORE)

    def summary_ignore_read(self: Self) -> str:
        return self.read_text(key=Key.SUMMARY_IGNORE)

    def summary_ignore_write(self: Self, value: str) -> None:
        return self.write_text(key=Key.SUMMARY_IGNORE, value=value)

    def _get_model_specific_summary_file_path(self: Self, llm_model_name: str) -> Path:
        summary_file = self.backend.get_file_path(key=DocumentKey.SUMMARY, value_type=Value.TEXT)
        return self.backend.directory / str(summary_file.stem + "_" + llm_model_name.replace("/", "__") + summary_file.suffix)

    def model_specific_summary_exists(self: Self, llm_model_name: str) -> bool:
        return self._get_model_specific_summary_file_path(llm_model_name=llm_model_name).exists()

    def model_specific_summary_write(self: Self, llm_model_name: str, summary: str) -> None:
        self._get_model_specific_summary_file_path(llm_model_name=llm_model_name).write_text(summary)

    def link_model_specific_summary_file(self: Self, llm_model_name: str) -> None:
        """Create a symlink from summary_file pointing to the model-specific summary file."""
        key = DocumentKey.SUMMARY

        summary_file = self.backend.get_file_path(key=key, value_type=Value.TEXT)
        model_specific_summary_file = self._get_model_specific_summary_file_path(llm_model_name=llm_model_name)

        summary_file.unlink(missing_ok=True)
        summary_file.symlink_to(model_specific_summary_file.relative_to(summary_file.parent))
        self.backend._write_metadata(key=key, value_type=Value.TEXT, ttl=None)

    def reset(self: Self) -> None:
        history_dir = self.backend.directory / DOK_CACHE_HISTORY_SUB_DIR_PATH
        history_dir.mkdir(parents=True, exist_ok=True)

        existing = [int(p.name) for p in history_dir.iterdir() if p.is_dir() and p.name.isdigit()]
        n = max(existing, default=0) + 1
        version_dir = history_dir / str(n)
        version_dir.mkdir()

        for file in self.backend.directory.iterdir():
            if file.is_file():
                file.rename(version_dir / file.name)
