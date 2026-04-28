from fastapi import Depends

from dependencies.auth import get_current_user
from models.user import User


async def get_store_id(current_user: User = Depends(get_current_user)) -> str:
    """Extracts store_id from the authenticated user — enforces multi-tenant isolation."""
    return current_user.store_id
