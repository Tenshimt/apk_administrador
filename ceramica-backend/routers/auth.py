from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies.auth import get_current_user
from dependencies.rate_limit import auth_rate_limit
from models.user import User
from schemas.auth import LoginRequest, LoginResponse, RefreshRequest, RegisterStoreRequest
from schemas.common import StandardResponse
from services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register-store",
    response_model=StandardResponse[dict],
    status_code=201,
    dependencies=[Depends(auth_rate_limit)],
)
async def register_store(data: RegisterStoreRequest, db: AsyncSession = Depends(get_db)):
    svc = AuthService(db)
    result = await svc.register_store(data)
    return StandardResponse(data=result)


@router.post(
    "/login",
    response_model=StandardResponse[LoginResponse],
    dependencies=[Depends(auth_rate_limit)],
)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    svc = AuthService(db)
    tokens = await svc.login(data)
    return StandardResponse(data=tokens)


@router.post("/refresh", response_model=StandardResponse[LoginResponse])
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    svc = AuthService(db)
    tokens = await svc.refresh(data.refresh_token)
    return StandardResponse(data=tokens)


@router.post("/logout", response_model=StandardResponse[dict])
async def logout(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    svc = AuthService(db)
    await svc.logout(data.refresh_token)
    return StandardResponse(data={"message": "Logged out successfully"})


@router.get("/me", response_model=StandardResponse[dict])
async def me(current_user: User = Depends(get_current_user)):
    return StandardResponse(
        data={
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "role": current_user.role.value,
            "store_id": current_user.store_id,
        }
    )
