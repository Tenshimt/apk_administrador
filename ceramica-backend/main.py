import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings
from database import create_tables
from routers import (
    auth_router,
    clients_router,
    finance_router,
    products_router,
    sales_router,
    suppliers_router,
    ws_router,
)
from websocket_manager import manager

settings = get_settings()
logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Ceramica API [%s]", settings.environment)
    if settings.environment == "development":
        await create_tables()
    await manager.startup(settings.redis_url)
    yield
    # Shutdown
    await manager.shutdown()
    logger.info("Ceramica API shutdown complete")


app = FastAPI(
    title="Ceramica Store API",
    description=(
        "Multi-tenant ceramic store management backend. "
        "Serves Android, iOS, Desktop, and Web clients via REST + WebSocket."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Global exception handler ─────────────────────────────────────────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"data": None, "error": "Internal server error", "meta": None},
    )


# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(products_router)
app.include_router(clients_router)
app.include_router(sales_router)
app.include_router(suppliers_router)
app.include_router(finance_router)
app.include_router(ws_router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "environment": settings.environment}


@app.get("/", tags=["health"])
async def root():
    return {
        "name": "Ceramica Store API",
        "version": "1.0.0",
        "docs": "/docs",
        "websocket": "/ws/{store_id}?token=<access_token>",
    }
