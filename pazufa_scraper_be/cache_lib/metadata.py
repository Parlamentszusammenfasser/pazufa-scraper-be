from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Self

from pydantic import BaseModel, field_validator

from .errors import MetadataError
from .types import Key, Value


def _compute_expires_at(ttl: timedelta | int | None) -> datetime | None:
    """Compute expiration timestamp from a TTL value."""
    if isinstance(ttl, timedelta):
        if ttl.total_seconds() > 0:
            return datetime.now(UTC) + ttl

        msg = "TTL must be positive."
        raise ValueError(msg)

    if isinstance(ttl, int):
        return _compute_expires_at(ttl=timedelta(days=ttl))

    if ttl is None:
        return None

    msg = f"TTL must be timedelta, int, or None. It was '{type(ttl)}'"
    raise ValueError(msg)


class Metadata(BaseModel):
    """Cache entry metadata.

    Used to track expiration and for validation.
    """

    key: Key
    value_type: Value
    expires_at: datetime | None = None
    created_at: datetime | None = None

    @classmethod
    def new(cls, key: Key, value_type: Value, ttl: int | timedelta | None) -> Metadata:
        """Build new Metadata.

        Args:
            key: Cache entry key.
            value_type: Cache entry value type.
            ttl: Optional time-to-live for the entry.

        Returns:
            Metadata for entry.
        """
        return cls(
            key=key,
            value_type=value_type,
            expires_at=_compute_expires_at(ttl=ttl),
            created_at=datetime.now(UTC),
        )

    def is_expired(self: Self) -> bool:
        """Check if the cached value has expired.

        Returns:
            True if expires_at is set and in the past, False otherwise.
        """
        return datetime.now(UTC) > self.expires_at if self.expires_at else False

    @field_validator("key", mode="before")
    @classmethod
    def _coerce_key(cls, v: Any) -> Any:
        """Coerce raw key values to registered Key subclasses.

        This allows to handle round-trip serialization to JSON using subclasses of Key.
        """
        for SubKeyCls in Key.__subclasses__():
            try:
                return SubKeyCls(v)

            except ValueError:
                continue

        raise MetadataError(f"Unknown Key value: {v!r}. Is the Key subclass registered?")

    @field_validator("*")
    @classmethod
    def _require_tz(cls, v: Any) -> Any:
        """Ensure all datetime fields are timezone-aware."""
        if isinstance(v, datetime) and v.tzinfo is None:
            raise MetadataError("Timestamps must be timezone-aware.")

        return v
