from pydantic import BaseModel, Field, field_validator


class ProductBase(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    category: str | None = None
    price_cents: int = Field(..., gt=0)
    cost_cents: int = Field(0, ge=0)
    stock_quantity: int = Field(0, ge=0)
    low_stock_threshold: int = Field(5, ge=0)


class ProductCreate(ProductBase):
    client_generated_id: str | None = None


class ProductUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    category: str | None = None
    price_cents: int | None = Field(None, gt=0)
    cost_cents: int | None = Field(None, ge=0)
    low_stock_threshold: int | None = Field(None, ge=0)


class StockAdjustRequest(BaseModel):
    quantity_delta: int  # positive = add, negative = subtract
    reason: str = Field(..., min_length=1, max_length=500)
    client_generated_id: str | None = None


class ProductOut(ProductBase):
    id: str
    store_id: str
    is_active: bool
    version: int
    client_generated_id: str | None = None

    model_config = {"from_attributes": True}
