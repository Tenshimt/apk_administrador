import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.base_mixin import FullMixin, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from models.store import Store
    from models.client import Client
    from models.product import Product
    from models.user import User


class SaleStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    cancelled = "cancelled"
    partial = "partial"


class PaymentMethod(str, enum.Enum):
    cash = "cash"
    card = "card"
    transfer = "transfer"
    credit = "credit"


class Sale(FullMixin, Base):
    __tablename__ = "sales"

    client_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cashier_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[SaleStatus] = mapped_column(
        Enum(SaleStatus, name="sale_status"), default=SaleStatus.pending, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    paid_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    client_generated_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, unique=True, index=True
    )

    store: Mapped["Store"] = relationship("Store", back_populates="sales")
    client: Mapped["Client | None"] = relationship("Client", back_populates="sales")
    cashier: Mapped["User | None"] = relationship("User")
    items: Mapped[list["SaleItem"]] = relationship(
        "SaleItem", back_populates="sale", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="sale", cascade="all, delete-orphan"
    )

    @property
    def balance_cents(self) -> int:
        return self.total_cents - self.paid_cents

    def __repr__(self) -> str:
        return f"<Sale {self.id[:8]} status={self.status} total={self.total_cents}>"


class SaleItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "sale_items"

    sale_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[str] = mapped_column(String(36), nullable=False)

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    sale: Mapped["Sale"] = relationship("Sale", back_populates="items")
    product: Mapped["Product"] = relationship("Product", back_populates="sale_items")


class Payment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "payments"

    sale_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True
    )
    store_id: Mapped[str] = mapped_column(String(36), nullable=False)

    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, name="payment_method"), nullable=False
    )
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    client_generated_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, unique=True, index=True
    )

    sale: Mapped["Sale"] = relationship("Sale", back_populates="payments")
