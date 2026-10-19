from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies.auth import require_roles
from dependencies.store import get_store_id
from models.user import User, UserRole
from schemas.common import PaginatedResponse, PaginationMeta, StandardResponse
from schemas.user import UserCreate, UserOut, UserUpdate
from services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])

_owner_only = Depends(require_roles(UserRole.owner))
_owner_or_admin = Depends(require_roles(UserRole.owner, UserRole.admin))


def _svc(
    db: AsyncSession = Depends(get_db),
    store_id: str = Depends(get_store_id),
) -> UserService:
    return UserService(db, store_id)


@router.get("", response_model=PaginatedResponse[UserOut], dependencies=[_owner_or_admin])
async def list_users(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    svc: UserService = Depends(_svc),
):
    users, total = await svc.list_users(limit=limit, offset=offset)
    return PaginatedResponse(
        data=[UserOut.model_validate(u) for u in users],
        meta=PaginationMeta(total=total, limit=limit, offset=offset, has_more=offset + limit < total),
    )


@router.post("", response_model=StandardResponse[UserOut], status_code=201, dependencies=[_owner_only])
async def create_user(data: UserCreate, svc: UserService = Depends(_svc)):
    user = await svc.create(data)
    return StandardResponse(data=UserOut.model_validate(user))


@router.get("/{user_id}", response_model=StandardResponse[UserOut], dependencies=[_owner_or_admin])
async def get_user(user_id: str, svc: UserService = Depends(_svc)):
    user = await svc.get_or_404(user_id)
    return StandardResponse(data=UserOut.model_validate(user))


@router.patch("/{user_id}", response_model=StandardResponse[UserOut], dependencies=[_owner_only])
async def update_user(user_id: str, data: UserUpdate, svc: UserService = Depends(_svc)):
    user = await svc.update(user_id, data)
    return StandardResponse(data=UserOut.model_validate(user))
