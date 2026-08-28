import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ValidationError

logger = logging.getLogger(__name__)


def parse_german_date(date_or_str: date | datetime | str) -> datetime:
    """Parse a German-format date string (DD.MM.YYYY) or pass through an existing timestamp."""
    if isinstance(date_or_str, datetime):
        return date_or_str.astimezone(UTC)

    if isinstance(date_or_str, date):
        date_ = date_or_str

    elif isinstance(date_or_str, str):
        date_ = datetime.strptime(date_or_str, "%d.%m.%Y").replace(tzinfo=UTC).date()

    else:
        msg = f"Can not parse given type: {type(date_or_str)}"
        raise TypeError(msg)

    return datetime(date_.year, date_.month, date_.day, tzinfo=UTC)


def ensure_list(value: object) -> list:
    """Wrap value in a list if it is not already a list."""
    return value if isinstance(value, list) else [value]


def ignore_invalid_factory(cls: type[BaseModel]) -> Callable[..., list]:
    """Return a function that validates items against cls, dropping invalid ones."""

    def return_function(items: list[Any]) -> list[BaseModel]:
        result = []
        for item in items:
            try:
                result.append(cls.model_validate(item))

            except ValidationError:
                msg = f"Ignoring invalid {cls.__name__}: {item}"
                logger.info(msg)

        return result

    return return_function


GermanDate = Annotated[datetime, BeforeValidator(parse_german_date)]
CoercedStrList = Annotated[list[str], BeforeValidator(ensure_list)]
CoercedIntList = Annotated[list[int], BeforeValidator(ensure_list)]
