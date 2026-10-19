from routers.auth import router as auth_router
from routers.clients import router as clients_router
from routers.finance import router as finance_router
from routers.products import router as products_router
from routers.sales import router as sales_router
from routers.suppliers import router as suppliers_router
from routers.users import router as users_router
from routers.websocket import router as ws_router

__all__ = [
    "auth_router",
    "clients_router",
    "finance_router",
    "products_router",
    "sales_router",
    "suppliers_router",
    "users_router",
    "ws_router",
]
