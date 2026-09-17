from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json
import logging
from typing import Dict, Set, Optional

logger = logging.getLogger(__name__)

router = APIRouter()

class ConnectionManager:
    """
    Channel-aware, thread-safe WebSocket connection manager.
    Supports dedicated channels (e.g. 'btc5m', 'markets') and global broadcasting.
    """
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.channels: Dict[str, Set[WebSocket]] = {
            "all": set(),
            "markets": set(),
            "btc5m": set(),
        }
        self._last_btc5m_payloads: Dict[str, dict] = {}

    async def connect(self, websocket: WebSocket, channel: str = "all"):
        await websocket.accept()
        self.active_connections.add(websocket)
        if channel not in self.channels:
            self.channels[channel] = set()
        self.channels[channel].add(websocket)
        self.channels["all"].add(websocket)
        logger.debug(f"[WebSocket] Client connected to channel '{channel}'. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket, channel: str = "all"):
        self.active_connections.discard(websocket)
        if channel in self.channels:
            self.channels[channel].discard(websocket)
        self.channels["all"].discard(websocket)
        logger.debug(f"[WebSocket] Client disconnected from channel '{channel}'. Remaining: {len(self.active_connections)}")

    async def broadcast(self, message: dict, channel: str = "all"):
        """Broadcast JSON message to all clients subscribed to a specific channel."""
        target_connections = list(self.channels.get(channel, self.active_connections))
        if not target_connections:
            return

        payload_str = json.dumps(message)
        dead_connections = []
        for connection in target_connections:
            try:
                await connection.send_text(payload_str)
            except Exception:
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead, channel)

    async def broadcast_btc5m(self, status_data: dict, instance_id: str = "instance_1"):
        """Dedicated high-frequency broadcast for BTC 5M market, price, trade, and signal ticks."""
        self._last_btc5m_payloads[instance_id] = status_data
        message = {
            "type": "btc5m_status",
            "channel": "btc5m",
            "instance_id": instance_id,
            "data": status_data
        }
        await self.broadcast(message, channel="btc5m")

    def get_last_btc5m_payload(self, instance_id: str = "instance_1") -> Optional[dict]:
        return self._last_btc5m_payloads.get(instance_id) or self._last_btc5m_payloads.get("instance_1")

manager = ConnectionManager()

@router.websocket("/live")
async def websocket_endpoint(websocket: WebSocket):
    """Legacy endpoint used by ResearchTerminal for market book updates."""
    await manager.connect(websocket, channel="markets")
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel="markets")
    except Exception as e:
        logger.debug(f"[WebSocket] /live connection error: {e}")
        manager.disconnect(websocket, channel="markets")

@router.websocket("/btc5m")
async def btc5m_websocket_endpoint(websocket: WebSocket):
    """
    Dedicated high-speed WebSocket stream for BTC 5M real-time data:
    - Instant push on connection with latest cached snapshots (<5ms latency)
    - Real-time ticks for BTC Price, Price-to-Beat, Orderbook Mid/Spread per bot instance
    - Immediate event notifications for Trade Entries, Exits, and Parameter Updates
    """
    await manager.connect(websocket, channel="btc5m")
    try:
        # If we have cached status payloads for any instances, send them immediately on connection
        if manager._last_btc5m_payloads:
            for inst_id, last_data in manager._last_btc5m_payloads.items():
                if last_data:
                    await websocket.send_text(json.dumps({
                        "type": "btc5m_status",
                        "channel": "btc5m",
                        "instance_id": inst_id,
                        "data": last_data
                    }))

        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel="btc5m")
    except Exception as e:
        logger.debug(f"[WebSocket] /btc5m connection error: {e}")
        manager.disconnect(websocket, channel="btc5m")
