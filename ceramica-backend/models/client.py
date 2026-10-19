import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.base_mixin import FullMixin

if TYPE_CHECKING:
    from models.store import Store
    from models.sale import Sale


class ClientType(str, enum.Enum):
    retail = "retail"
    distributor = "distributor"
    contractor = "contractor"


class Client(FullMixin, Base):
    __tablename__ = "clients"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    debt_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    client_type: Mapped[ClientType] = mapped_column(
        Enum(ClientType, name="client_type"), default=ClientType.retail, nullable=False
    )
    credit_limit_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)

    client_generated_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, unique=True, index=True
    )

    store: Mapped["Store"] = relationship("Store", back_populates="clients")
    sales: Mapped[list["Sale"]] = relationship("Sale", back_populates="client")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Client {self.full_name} debt={self.debt_cents}>"
