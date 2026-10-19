import enum
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.base_mixin import FullMixin, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from models.store import Store
    from models.product import Product


class PurchaseOrderStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    received = "received"
    cancelled = "cancelled"


class Supplier(FullMixin, Base):
    __tablename__ = "suppliers"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    store: Mapped["Store"] = relationship("Store", back_populates="suppliers")
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(
        "PurchaseOrder", back_populates="supplier"
    )

    def __repr__(self) -> str:
        return f"<Supplier {self.name}>"


class PurchaseOrder(FullMixin, Base):
    __tablename__ = "purchase_orders"

    supplier_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ordered_by_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[PurchaseOrderStatus] = mapped_column(
        Enum(PurchaseOrderStatus, name="purchase_order_status"),
        default=PurchaseOrderStatus.draft,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    paid_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    client_generated_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, unique=True, index=True
    )

    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="purchase_orders")
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        "PurchaseOrderItem", back_populates="order", cascade="all, delete-orphan"
    )
    po_payments: Mapped[list["PurchaseOrderPayment"]] = relationship(
        "PurchaseOrderPayment", back_populates="order", cascade="all, delete-orphan"
    )

    @property
    def balance_cents(self) -> int:
        return self.total_cents - self.paid_cents

    def __repr__(self) -> str:
        return f"<PurchaseOrder {self.id[:8]} status={self.status}>"


class PurchaseOrderItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "purchase_order_items"

    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[str] = mapped_column(String(36), nullable=False)

    quantity_ordered: Mapped["Decimal"] = mapped_column(Numeric(12, 3), nullable=False)
    quantity_received: Mapped["Decimal"] = mapped_column(Numeric(12, 3), default=0, nullable=False)
    unit_cost_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="items")
    product: Mapped["Product"] = relationship("Product", back_populates="purchase_order_items")


class PurchaseOrderPayment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "purchase_order_payments"

    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    store_id: Mapped[str] = mapped_column(String(36), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)

    order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="po_payments")
