import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from config import get_settings
from websocket_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])
settings = get_settings()


@router.websocket("/ws/{store_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    store_id: str,
    token: str = Query(...),
):
    """
    WebSocket endpoint. Connect with:
      ws://host/ws/{store_id}?token=<access_token>

    Events received by clients:
      - stock_updated
      - sale_created
      - payment_received
      - low_stock_alert
      - purchase_received
    """
    # Validate JWT before accepting the connection
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        token_store_id = payload.get("store_id")
        if token_store_id != store_id:
            await websocket.close(code=4003)
            return
    except JWTError:
        await websocket.close(code=4001)
        return

    await manager.connect(websocket, store_id)
    try:
        while True:
            # Keep connection alive; clients can send pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, store_id)
        logger.debug("WS disconnected store=%s", store_id)
