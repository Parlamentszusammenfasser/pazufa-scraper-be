from datetime import datetime, timedelta

from .cache import Cache
from .types import DocumentKey


class DocumentCacheMixin:
    """Convenience cache Mixin.

    Offers convenience methods for working common documents in the PaZuFa project.
    """

    def document_exists(self: Cache) -> bool:
        """Check if document exists in the cache.

        Returns:
            True if the document exists, False otherwise.
        """
        return self.has_entry(key=DocumentKey.DOCUMENT)

    def document_read(self: Cache) -> bytes:
        """Read document from the cache.

        Returns:
            The stored document bytes.

        Raises:
            KeyDoesNotExistError: If document does not exist.
            KeyExpiredError: If document has expired.
            ValueTypeError: If stored document value is not bytes.
        """
        return self.read_bytes(key=DocumentKey.DOCUMENT)

    def document_write(self: Cache, value: bytes, ttl: timedelta | None = None) -> None:
        """Write document to the cache.

        Args:
            value: The document bytes to store.
            ttl: Optional time-to-live for the entry.
        """
        self.write_bytes(key=DocumentKey.DOCUMENT, value=value, ttl=ttl)

    def text_exists(self: Cache) -> bool:
        """Check if the text exists in the cache.

        Returns:
            True if the text exists, False otherwise.
        """
        return self.has_entry(key=DocumentKey.TEXT)

    def text_read(self: Cache) -> str:
        """Read the text from the cache.

        Returns:
            The stored text.

        Raises:
            KeyDoesNotExistError: If the text not exist.
            KeyExpiredError: If the text has expired.
            ValueTypeError: If the text is not text.
        """
        return self.read_text(key=DocumentKey.TEXT)

    def text_write(self: Cache, value: str, ttl: timedelta | None = None) -> None:
        """Write the text to the cache.

        Args:
            value: The text to store.
            ttl: Optional time-to-live for the entry.
        """
        self.write_text(key=DocumentKey.TEXT, value=value, ttl=ttl)

    def summary_exists(self: Cache) -> bool:
        """Check if summary exists in the cache.

        Returns:
            True if summary, False otherwise.
        """
        return self.has_entry(key=DocumentKey.SUMMARY)

    def summary_read(self: Cache) -> str:
        """Read summary from the cache.

        Returns:
            The stored summary.

        Raises:
            KeyDoesNotExistError: If summary does not exist.
            KeyExpiredError: If summary has expired.
            ValueTypeError: If summary is not text.
        """
        return self.read_text(key=DocumentKey.SUMMARY)

    def summary_write(self: Cache, value: str, ttl: timedelta | None = None) -> None:
        """Write summary to the cache.

        Args:
            value: Summary to store.
            ttl: Optional time-to-live for the entry.
        """
        self.write_text(key=DocumentKey.SUMMARY, value=value, ttl=ttl)

    def download_time_read(self: Cache) -> datetime:
        """Read the download time from the cache.

        Returns:
            The download time timestamp.

        Raises:
            KeyDoesNotExistError: If the download time does not exist.
            KeyExpiredError: If the download time has expired.
            ValueTypeError: If the stored download time is not a timestamp.
        """
        return self.read_timestamp(key=DocumentKey.DOWNLOAD_TIME)

    def download_time_write(self: Cache, value: datetime, ttl: timedelta | None = None) -> None:
        """Write the download time to the cache.

        Args:
            value: The download time to store.
            ttl: Optional time-to-live for the entry.

        Raises:
            ValueTypeError: If the timestamp is not timezone-aware.
        """
        self.write_timestamp(key=DocumentKey.DOWNLOAD_TIME, value=value, ttl=ttl)

    def download_time_exists(self: Cache) -> bool:
        """Check if download time exists in the cache.

        Returns:
            True if the download time exists, False otherwise.
        """
        return self.has_entry(key=DocumentKey.DOWNLOAD_TIME)
