class CacheError(Exception):
    """Base exception for Cache."""


class KeyError(CacheError):
    """Raised when an error with a key exists."""


class ValueError(CacheError):
    """Raised when an error with a value exists."""


class MetadataError(CacheError):
    """Raised when an error with the metadata exists."""


class ValueTypeError(ValueError):
    """Raised when value can not be parsed into request type."""


class KeyExpiredError(KeyError):
    """Raised when key is expired."""


class KeyDoesNotExistError(KeyError):
    """Raised when a key does not exist."""
