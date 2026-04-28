import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.base_mixin import FullMixin

if TYPE_CHECKING:
    from models.store import Store


class ExpenseCategory(str, enum.Enum):
    rent = "rent"
    utilities = "utilities"
    salaries = "salaries"
    supplies = "supplies"
    shipping = "shipping"
    marketing = "marketing"
    maintenance = "maintenance"
    taxes = "taxes"
    other = "other"


class Expense(FullMixin, Base):
    __tablename__ = "expenses"

    description: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[ExpenseCategory] = mapped_column(
        Enum(ExpenseCategory, name="expense_category"), nullable=False
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    client_generated_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, unique=True, index=True
    )

    store: Mapped["Store"] = relationship("Store", back_populates="expenses")

    def __repr__(self) -> str:
        return f"<Expense {self.category} {self.amount_cents}>"
