from decimal import Decimal
from models.sale import PaymentMethod, SaleStatus
from pydantic import BaseModel, Field
from schemas.common import DecimalOut, DecimalOutRequired


class SaleItemCreate(BaseModel):
    product_id: str
    quantity: Decimal = Field(..., gt=0)
    requested_m2: Decimal | None = Field(None, gt=0)
    unit_price_cents: int | None = Field(default=None, gt=0)
    discount_cents: int = Field(0, ge=0)


class SaleItemOut(BaseModel):
    id: str
    product_id: str
    quantity: DecimalOutRequired
    requested_m2: DecimalOut = None
    unit_price_cents: int
    unit_cost_cents: int | None = None
    discount_cents: int
    total_cents: int

    model_config = {"from_attributes": True}


class SaleCreate(BaseModel):
    client_id: str | None = None
    items: list[SaleItemCreate] = Field(..., min_length=1)
    discount_cents: int = Field(0, ge=0)
    notes: str | None = None
    client_generated_id: str | None = None
    # Optional immediate payment
    payment_method: PaymentMethod | None = None
    payment_amount_cents: int | None = Field(default=None, gt=0)


class PaymentCreate(BaseModel):
    amount_cents: int = Field(..., gt=0)
    method: PaymentMethod
    reference: str | None = None
    notes: str | None = None
    client_generated_id: str | None = None


class PaymentOut(BaseModel):
    id: str
    sale_id: str
    store_id: str
    amount_cents: int
    method: PaymentMethod
    reference: str | None = None

    model_config = {"from_attributes": True}


class SaleOut(BaseModel):
    id: str
    store_id: str
    client_id: str | None
    cashier_id: str | None
    status: SaleStatus
    subtotal_cents: int
    discount_cents: int
    total_cents: int
    paid_cents: int
    balance_cents: int
    notes: str | None
    items: list[SaleItemOut] = []
    payments: list[PaymentOut] = []

    model_config = {"from_attributes": True}
