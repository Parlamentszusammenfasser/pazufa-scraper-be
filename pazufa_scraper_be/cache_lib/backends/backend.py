from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Self

from pazufa_scraper_be.cache_lib.metadata import Metadata
from pazufa_scraper_be.cache_lib.types import Key, Value


class Backend(ABC):
    """Abstract cache backend interface.

    All concrete cache backends must implement every method in this interface.
    Subclasses are responsible for the low-level storage operations (reading,
    writing, deleting) and for handling encoding, serialization, and key
    management at the storage level.
    """

    @abstractmethod
    def get_text(self: Self, key: Key) -> str:
        """Retrieve a raw text value from the underlying storage."""

    @abstractmethod
    def set_text(self: Self, key: Key, value: str) -> None:
        """Store a raw text value in the underlying storage."""

    @abstractmethod
    def get_bytes(self: Self, key: Key) -> bytes:
        """Retrieve a raw bytes value from the underlying storage."""

    @abstractmethod
    def set_bytes(self: Self, key: Key, value: bytes) -> None:
        """Store a raw bytes value in the underlying storage."""

    @abstractmethod
    def get_timestamp(self: Self, key: Key) -> datetime:
        """Deserialize and retrieve a timestamp value from the underlying storage."""

    @abstractmethod
    def set_timestamp(self: Self, key: Key, value: datetime) -> None:
        """Serialize and store a timestamp value in the underlying storage."""

    @abstractmethod
    def get_dict(self: Self, key: Key) -> dict:
        """Deserialize and retrieve a dict value from the underlying storage."""

    @abstractmethod
    def set_dict(self: Self, key: Key, value: dict) -> None:
        """Serialize and store a dict value in the underlying storage."""

    @abstractmethod
    def has_entry(self: Self, key: Key) -> bool:
        """Return True if the key exists in the underlying storage."""

    @abstractmethod
    def delete_entry(self: Self, key: Key) -> None:
        """Remove the entry and its associated data from the underlying storage."""

    @abstractmethod
    def get_metadata(self: Self, key: Key) -> Metadata:
        """Retrieve the Metadata record for a cache entry from storage."""

    @abstractmethod
    def set_metadata(self: Self, key: Key, value_type: Value, ttl: timedelta | int | None) -> None:
        """Store or update the Metadata record for a cache entry in storage."""
