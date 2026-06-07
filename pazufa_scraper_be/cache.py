from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from pazufa_scraper_be.cache_lib import DocumentCache as BaseDocumentCache
from pazufa_scraper_be.cache_lib import DocumentKey, Value
from pazufa_scraper_be.cache_lib import Key as BaseKey
from pazufa_scraper_be.cache_lib.backends import FileSystemBackend
from pazufa_scraper_be.constants import DOK_CACHE_HISTORY_SUB_DIR_PATH


class Key(BaseKey):
    """Keys for DocumentCache."""

    URL = "URL"
    LAST_MODIFIED = "LAST_MODIFIED"
    LAST_CHECKED = "LAST_CHECKED"
    SUMMARY_IGNORE = "SUMMARY_IGNORE"


class DocumentCache(BaseDocumentCache[FileSystemBackend]):
    """Container for document cache."""

    def __init__(self: Self, base_dir: Path, name: str) -> None:
        """Init Document Cache using FileSystemBackend."""
        self.name = name
        super().__init__(backend=FileSystemBackend(base_dir=Path(base_dir) / name))

    def update_last_checked(self: Self) -> None:
        """Signal that remote got just checked."""
        return self.write_timestamp(key=Key.LAST_CHECKED, value=datetime.now(UTC))

    def get_last_checked(self: Self) -> datetime | None:
        """Get datetime when last modified happened or None if non."""
        if self.has_entry(key=Key.LAST_CHECKED):
            return self.read_timestamp(key=Key.LAST_CHECKED)

        return None

    def write_url(self: Self, value: str) -> None:
        """Write URL value."""
        return self.write_text(key=Key.URL, value=value)

    def exist_last_modified(self: Self) -> bool:
        """Check if last modified exists."""
        return self.has_entry(key=Key.LAST_MODIFIED)

    def get_last_modified(self: Self) -> datetime:
        """Read last modified value."""
        return self.read_timestamp(key=Key.LAST_MODIFIED)

    def set_last_modified(self: Self, value: datetime) -> None:
        """Write last modified value."""
        return self.write_timestamp(key=Key.LAST_MODIFIED, value=value)

    def exist_summary_ignore(self: Self) -> bool:
        """Check if summary ignore exists."""
        return self.has_entry(key=Key.SUMMARY_IGNORE)

    def set_summary_ignore(self: Self, value: str) -> None:
        """Write summary ignore value."""
        return self.write_text(key=Key.SUMMARY_IGNORE, value=value)

    def _get_model_specific_summary_file_path(self: Self, llm_model_name: str) -> Path:
        summary_file = self.backend.get_file_path(key=DocumentKey.SUMMARY, value_type=Value.TEXT)
        return self.backend.directory / str(summary_file.stem + "_" + llm_model_name.replace("/", "__") + summary_file.suffix)

    def exist_model_specific_summary(self: Self, llm_model_name: str) -> bool:
        """Check if model specific summary exists."""
        return self._get_model_specific_summary_file_path(llm_model_name=llm_model_name).exists()

    def set_model_specific_summary(self: Self, llm_model_name: str, summary: str) -> None:
        """Write to model specific summary."""
        self._get_model_specific_summary_file_path(llm_model_name=llm_model_name).write_text(summary)

    def link_model_specific_summary_file(self: Self, llm_model_name: str) -> None:
        """Create a symlink from summary_file pointing to the model-specific summary file."""
        key = DocumentKey.SUMMARY

        summary_file = self.backend.get_file_path(key=key, value_type=Value.TEXT)
        model_specific_summary_file = self._get_model_specific_summary_file_path(llm_model_name=llm_model_name)

        summary_file.unlink(missing_ok=True)
        summary_file.symlink_to(model_specific_summary_file.relative_to(summary_file.parent))
        self.backend.write_metadata(key=key, value_type=Value.TEXT, ttl=None)

    def reset(self: Self) -> None:
        """Reset DocumentCache."""
        history_dir = self.backend.directory / DOK_CACHE_HISTORY_SUB_DIR_PATH
        history_dir.mkdir(parents=True, exist_ok=True)

        existing = [int(p.name) for p in history_dir.iterdir() if p.is_dir() and p.name.isdigit()]
        n = max(existing, default=0) + 1
        version_dir = history_dir / str(n)
        version_dir.mkdir()

        for file in self.backend.directory.iterdir():
            if file.is_file():
                file.rename(version_dir / file.name)
