class CacheError(Exception):
    """Base exception for Cache."""


class CacheKeyError(CacheError):
    """Raised when an error with a key exists."""


class CacheValueError(CacheError):
    """Raised when an error with a value exists."""


class MetadataError(CacheError):
    """Raised when an error with the metadata exists."""


class ValueTypeError(CacheValueError):
    """Raised when value can not be parsed into request type."""


class KeyExpiredError(CacheKeyError):
    """Raised when key is expired."""


class KeyDoesNotExistError(CacheKeyError):
    """Raised when a key does not exist."""
