from decimal import Decimal
from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel
from pydantic.functional_serializers import PlainSerializer

# Decimal field that serializes as a float in JSON output (instead of string)
DecimalOut = Annotated[
    Decimal | None,
    PlainSerializer(lambda x: float(x) if x is not None else None, return_type=float | None),
]
# Non-nullable version
DecimalOutRequired = Annotated[
    Decimal,
    PlainSerializer(lambda x: float(x), return_type=float),
]

T = TypeVar("T")


class StandardResponse(BaseModel, Generic[T]):
    """Every API response follows this envelope."""

    data: T | None = None
    error: str | None = None
    meta: dict[str, Any] | None = None


class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int
    has_more: bool


class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    error: str | None = None
    meta: PaginationMeta
