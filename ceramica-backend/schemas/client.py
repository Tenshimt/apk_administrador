from pydantic import BaseModel, EmailStr, Field


class ClientBase(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    phone: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    notes: str | None = None


class ClientCreate(ClientBase):
    client_generated_id: str | None = None


class ClientUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=255)
    phone: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    notes: str | None = None


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
