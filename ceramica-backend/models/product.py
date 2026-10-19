from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.base_mixin import FullMixin

if TYPE_CHECKING:
    from models.store import Store


class Product(FullMixin, Base):
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wholesale_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)

    stock_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    client_generated_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, unique=True, index=True
    )

    store: Mapped["Store"] = relationship("Store", back_populates="products")
    sale_items: Mapped[list["SaleItem"]] = relationship(  # noqa: F821
        "SaleItem", back_populates="product"
    )
    purchase_order_items: Mapped[list["PurchaseOrderItem"]] = relationship(  # noqa: F821
        "PurchaseOrderItem", back_populates="product"
    )
    stock_movements: Mapped[list["StockMovement"]] = relationship(  # noqa: F821
        "StockMovement", back_populates="product"
    )

    def __repr__(self) -> str:
        return f"<Product {self.sku} qty={self.stock_quantity}>"
