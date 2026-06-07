from .backends import Backend as _Backend
from .backends import FileSystemBackend
from .cache import Cache as _Cache
from .errors import (
    CacheError,
    CacheKeyError,
    CacheValueError,
    KeyDoesNotExistError,
    KeyExpiredError,
    MetadataError,
    ValueTypeError,
)
from .mixin import DocumentCacheMixin as _DocumentCacheMixin
from .types import DocumentKey, Key, Value


class DocumentCache[T: _Backend](_Cache[T], _DocumentCacheMixin):
    """Cache implementation for PaZuFa scrapers.

    Besides the cache primitives to read/write values to a certain key
    with a defined type, it also offers some convenience methods.
    For example `document_read/write/exists` to easily work with PDF documents.
    """


__all__ = [
    "CacheError",
    "CacheKeyError",
    "CacheValueError",
    "DocumentCache",
    "DocumentKey",
    "FileSystemBackend",
    "Key",
    "KeyDoesNotExistError",
    "KeyExpiredError",
    "MetadataError",
    "Value",
    "ValueTypeError",
]
