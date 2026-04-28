"""Celery tasks for background processing."""

import asyncio
import logging

from background_tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run(coro):
    """Run an async coroutine from a sync Celery task."""
    return asyncio.get_event_loop().run_until_complete(coro)


@celery_app.task(name="background_tasks.tasks.check_low_stock_all_stores")
def check_low_stock_all_stores():
    """Scan all stores for low-stock products and emit WebSocket alerts."""
    async def _check():
        from database import AsyncSessionLocal
        from models.product import Product
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Product).where(
                    Product.is_active.is_(True),
                    Product.stock_quantity <= Product.low_stock_threshold,
                )
            )
            products = result.scalars().all()
            from websocket_manager import manager
            for product in products:
                await manager.broadcast(
                    product.store_id,
                    "low_stock_alert",
                    {
                        "product_id": product.id,
                        "sku": product.sku,
                        "name": product.name,
                        "stock": product.stock_quantity,
                        "threshold": product.low_stock_threshold,
                    },
                )
            logger.info("Low stock check: found %d products", len(products))

    _run(_check())


@celery_app.task(name="background_tasks.tasks.generate_daily_report")
def generate_daily_report(store_id: str):
    """Generate and cache a daily P&L report for a store."""
    logger.info("Generating daily report for store %s", store_id)
    # Hook for future email/notification delivery
