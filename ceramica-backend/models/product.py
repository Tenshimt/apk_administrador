import enum
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.base_mixin import FullMixin

if TYPE_CHECKING:
    from models.store import Store


class ProductUnit(str, enum.Enum):
    m2 = "m2"
    box = "box"
    unit = "unit"


class Product(FullMixin, Base):
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wholesale_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)

    unit: Mapped[ProductUnit] = mapped_column(
        Enum(ProductUnit, name="product_unit"), default=ProductUnit.unit, nullable=False
    )
    m2_per_box: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)

    stock_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0, nullable=False)
    low_stock_threshold: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=5, nullable=False)

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
