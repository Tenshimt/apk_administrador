from models.supplier import PurchaseOrderStatus
from pydantic import BaseModel, EmailStr, Field


class SupplierBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    contact_name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    notes: str | None = None


class SupplierCreate(SupplierBase):
    pass


class SupplierOut(SupplierBase):
    id: str
    store_id: str
    is_active: bool

    model_config = {"from_attributes": True}


class PurchaseOrderItemCreate(BaseModel):
    product_id: str
    quantity_ordered: int = Field(..., gt=0)
    unit_cost_cents: int = Field(..., gt=0)


class PurchaseOrderItemOut(BaseModel):
    id: str
    product_id: str
    quantity_ordered: int
    quantity_received: int
    unit_cost_cents: int
    total_cents: int

    model_config = {"from_attributes": True}


class PurchaseOrderCreate(BaseModel):
    supplier_id: str
    items: list[PurchaseOrderItemCreate] = Field(..., min_length=1)
    notes: str | None = None
    client_generated_id: str | None = None


class PurchaseOrderReceive(BaseModel):
    items: list[dict]
    notes: str | None = None


class PurchaseOrderPaymentCreate(BaseModel):
    amount_cents: int = Field(..., gt=0)
    notes: str | None = None


class PurchaseOrderOut(BaseModel):
    id: str
    store_id: str
    supplier_id: str
    status: PurchaseOrderStatus
    total_cents: int
    paid_cents: int = 0
    notes: str | None
    items: list[PurchaseOrderItemOut] = []

    model_config = {"from_attributes": True}
