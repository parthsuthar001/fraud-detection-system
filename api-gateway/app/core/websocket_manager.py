from fastapi import WebSocket
from typing import List
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections for broadcasting fraud alerts."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New WebSocket client. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket client left. Total: {len(self.active_connections)}")

    async def broadcast_alert(self, alert: dict):
        """Push a fraud alert to ALL connected dashboard clients."""
        message = json.dumps(alert)
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)
        for conn in dead:
            self.active_connections.remove(conn)
