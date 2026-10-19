from pydantic import BaseModel, EmailStr, Field

from models.client import ClientType


class ClientBase(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    phone: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    notes: str | None = None
    client_type: ClientType = ClientType.retail
    credit_limit_cents: int = Field(0, ge=0)


class ClientCreate(ClientBase):
    client_generated_id: str | None = None


class ClientUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=255)
    phone: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    notes: str | None = None
    client_type: ClientType | None = None
    credit_limit_cents: int | None = Field(None, ge=0)


class ClientOut(ClientBase):
    id: str
    store_id: str
    debt_cents: int
    is_active: bool

    model_config = {"from_attributes": True}


class ClientDebtOut(BaseModel):
    client_id: str
    full_name: str
    debt_cents: int
    pending_sales: list[dict] = []


class DebtAgingEntry(BaseModel):
    client_id: str
    full_name: str
    bucket_0_30: int = 0
    bucket_31_60: int = 0
    bucket_61_90: int = 0
    bucket_90_plus: int = 0
    total: int = 0
