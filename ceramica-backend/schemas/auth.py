from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    store_slug: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    store_id: str
    user_id: str
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterStoreRequest(BaseModel):
    store_name: str
    store_slug: str
    owner_email: EmailStr
    owner_password: str
    owner_full_name: str
    currency_code: str = "USD"
    timezone: str = "UTC"


class TokenData(BaseModel):
    user_id: str
    store_id: str
    role: str
    email: str
