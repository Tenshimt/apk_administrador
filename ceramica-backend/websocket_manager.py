"""WebSocket connection manager with Redis pub/sub for multi-instance broadcasting."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages per-store WebSocket connections and broadcasts via Redis pub/sub."""

    def __init__(self) -> None:
        # store_id → set of active WebSocket connections
        self._connections: dict[str, set[WebSocket]] = {}
        self._redis = None
        self._pubsub = None
        self._listener_task: asyncio.Task | None = None

    async def startup(self, redis_url: str) -> None:
        """Called at app startup to initialize Redis pub/sub listener."""
        try:
            import redis.asyncio as aioredis

            self._redis = await aioredis.from_url(redis_url, decode_responses=True)
            self._pubsub = self._redis.pubsub()
            await self._pubsub.subscribe("ceramica:events")
            self._listener_task = asyncio.create_task(self._listen())
            logger.info("WebSocket manager connected to Redis")
        except Exception as exc:
            logger.warning("Redis unavailable — WebSocket broadcasts will be local only: %s", exc)

    async def shutdown(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe()
            except Exception as exc:
                logger.warning("Redis unsubscribe failed during shutdown: %s", exc)
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception as exc:
                logger.warning("Redis close failed during shutdown: %s", exc)

    async def connect(self, websocket: WebSocket, store_id: str) -> None:
        await websocket.accept()
        self._connections.setdefault(store_id, set()).add(websocket)
        logger.debug("WS connected store=%s total=%d", store_id, len(self._connections[store_id]))

    def disconnect(self, websocket: WebSocket, store_id: str) -> None:
        store_conns = self._connections.get(store_id, set())
        store_conns.discard(websocket)
        if not store_conns:
            self._connections.pop(store_id, None)

    async def broadcast(self, store_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """Publish to Redis so all API instances can forward to their WebSocket clients."""
        message = json.dumps({"store_id": store_id, "type": event_type, "payload": payload}, default=str)
        if self._redis:
            try:
                await self._redis.publish("ceramica:events", message)
                return
            except Exception as exc:
                logger.warning("Redis publish failed, falling back to local broadcast: %s", exc)
        # Fallback: deliver only to connections on this process
        await self._local_broadcast(store_id, event_type, payload)

    async def _local_broadcast(
        self, store_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        message = json.dumps({"type": event_type, "payload": payload}, default=str)
        dead: set[WebSocket] = set()
        for ws in self._connections.get(store_id, set()):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.disconnect(ws, store_id)

    async def _listen(self) -> None:
        """Redis pub/sub listener — delivers messages from any API instance."""
        async for message in self._pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
                await self._local_broadcast(
                    data["store_id"], data["type"], data["payload"]
                )
            except Exception as exc:
                logger.error("WS listener error: %s", exc)


manager = ConnectionManager()
