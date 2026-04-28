from typing import Any, Generic, TypeVar

from pydantic import BaseModel

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
