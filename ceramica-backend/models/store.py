from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.base_mixin import UUIDMixin, TimestampMixin


class Store(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "stores"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    owner_email: Mapped[str] = mapped_column(String(255), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    users: Mapped[list["User"]] = relationship(  # noqa: F821
        "User", back_populates="store", cascade="all, delete-orphan"
    )
    products: Mapped[list["Product"]] = relationship(  # noqa: F821
        "Product", back_populates="store", cascade="all, delete-orphan"
    )
    clients: Mapped[list["Client"]] = relationship(  # noqa: F821
        "Client", back_populates="store", cascade="all, delete-orphan"
    )
    sales: Mapped[list["Sale"]] = relationship(  # noqa: F821
        "Sale", back_populates="store", cascade="all, delete-orphan"
    )
    suppliers: Mapped[list["Supplier"]] = relationship(  # noqa: F821
        "Supplier", back_populates="store", cascade="all, delete-orphan"
    )
    expenses: Mapped[list["Expense"]] = relationship(  # noqa: F821
        "Expense", back_populates="store", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Store {self.slug}>"
