from __future__ import annotations

from datetime import datetime
from enum import EnumMeta, StrEnum, auto
from typing import TYPE_CHECKING, Any

from pydantic_core import CoreSchema, core_schema

if TYPE_CHECKING:
    from pydantic import GetCoreSchemaHandler

type SupportedValueTypes = str | dict | bytes | datetime


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


class _KeyMeta(EnumMeta):
    def __call__(cls, value: str, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        if cls is Key and not args and not kwargs:
            for subclass in cls.__subclasses__():
                try:
                    return subclass(value)  # ty: ignore[too-many-positional-arguments]

                except ValueError:
                    pass

            return cls._missing_(value)
        return super().__call__(value, *args, **kwargs)


class Key(StrEnum, metaclass=_KeyMeta):
    """Base class for cache key namespaces."""

    @classmethod
    def _missing_(cls, value: object) -> Key:
        if not isinstance(value, str):
            msg = "Only str allowed."
            raise TypeError(msg)

        member = str.__new__(cls, value)
        member._name_ = member._value_ = value
        cls._value2member_map_[value] = member
        return member

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: GetCoreSchemaHandler) -> CoreSchema:  # noqa: ANN401
        """Make sure we can (de)serialize from/to JSON."""
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(),
            serialization=core_schema.to_string_ser_schema(when_used="json"),
        )
