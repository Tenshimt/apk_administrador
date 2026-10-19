import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.base_mixin import UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from models.product import Product


class MovementReason(str, enum.Enum):
    sale = "sale"
    cancel = "cancel"
    purchase = "purchase"
    adjustment = "adjustment"


class StockMovement(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "stock_movements"

    store_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity_change: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[MovementReason] = mapped_column(
        Enum(MovementReason, name="movement_reason"), nullable=False
    )
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    product: Mapped["Product"] = relationship("Product", back_populates="stock_movements")
