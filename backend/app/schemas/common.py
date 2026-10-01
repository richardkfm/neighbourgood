"""Shared Pydantic types."""

import datetime
from typing import Annotated

from pydantic import AfterValidator, PlainSerializer


def _serialize_utc(value: datetime.datetime) -> str:
    """Emit an ISO-8601 string with an explicit UTC marker.

    The database stores naive UTC timestamps. Without a zone marker, browsers
    parse the value as *local* time and show every time shifted by the viewer's
    UTC offset.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    else:
        value = value.astimezone(datetime.timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _to_naive_utc(value: datetime.datetime) -> datetime.datetime:
    """Normalise incoming timezone-aware datetimes to naive UTC (the storage format)."""
    if value.tzinfo is not None:
        value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return value


# Output: naive-UTC datetimes are serialised with a trailing "Z".
UTCDateTime = Annotated[
    datetime.datetime, PlainSerializer(_serialize_utc, return_type=str, when_used="json")
]

# Input: aware datetimes are converted to naive UTC before storage.
InputDateTime = Annotated[datetime.datetime, AfterValidator(_to_naive_utc)]
