from __future__ import annotations

from enum import StrEnum, auto


class Value(StrEnum):
    """Enumeration of types storable in the cache.

    Attributes:
        TEXT: Plain text content.
        BYTES: Raw byte content, e.g. binary files.
        TIMESTAMP: ISO-format datetime string.
        DICT: JSON-serializable dictionary.
    """

    TEXT = auto()
    BYTES = auto()
    TIMESTAMP = auto()
    DICT = auto()


class Key(StrEnum):
    """Base class for cache key namespaces."""


class DocumentKey(Key):
    """Cache key namespace for document-scoped entries.

    Attributes:
        DOCUMENT: The full PDF.
        TEXT: Extracted plain text.
        SUMMARY: LLM-generated summary.
        DOWNLOAD_TIME: Timestamp of initial fetch.
    """

    DOCUMENT = "DOCUMENT"
    TEXT = "TEXT"
    SUMMARY = "SUMMARY"
    DOWNLOAD_TIME = "DOWNLOAD_TIME"
