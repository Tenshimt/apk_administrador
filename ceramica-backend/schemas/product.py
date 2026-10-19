from decimal import Decimal
from pydantic import BaseModel, Field
from models.product import ProductUnit
from schemas.common import DecimalOut, DecimalOutRequired


class ProductBase(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    category: str | None = None
    price_cents: int = Field(..., gt=0)
    cost_cents: int = Field(0, ge=0)
    wholesale_price_cents: int | None = Field(None, gt=0)
    unit: ProductUnit = ProductUnit.unit
    m2_per_box: Decimal | None = Field(None, gt=0)
    stock_quantity: Decimal = Field(Decimal("0"), ge=0)
    low_stock_threshold: Decimal = Field(Decimal("5"), ge=0)


class ProductCreate(ProductBase):
    client_generated_id: str | None = None


class ProductUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    category: str | None = None
    price_cents: int | None = Field(None, gt=0)
    cost_cents: int | None = Field(None, ge=0)
    wholesale_price_cents: int | None = Field(None, gt=0)
    unit: ProductUnit | None = None
    m2_per_box: Decimal | None = Field(None, gt=0)
    low_stock_threshold: Decimal | None = Field(None, ge=0)


class StockAdjustRequest(BaseModel):
    quantity_delta: Decimal
    reason: str = Field(..., min_length=1, max_length=500)
    client_generated_id: str | None = None


class ProductOut(BaseModel):
    id: str
    store_id: str
    sku: str
    name: str
    description: str | None = None
    category: str | None = None
    price_cents: int
    cost_cents: int
    wholesale_price_cents: int | None = None
    unit: ProductUnit = ProductUnit.unit
    m2_per_box: DecimalOut = None
    stock_quantity: DecimalOutRequired
    low_stock_threshold: DecimalOutRequired
    is_active: bool
    version: int
    client_generated_id: str | None = None

    model_config = {"from_attributes": True}


class StockMovementOut(BaseModel):
    id: str
    product_id: str
    store_id: str
    quantity_change: DecimalOutRequired
    reason: str
    reference_id: str | None
    user_id: str | None
    created_at: str

    model_config = {"from_attributes": True}
