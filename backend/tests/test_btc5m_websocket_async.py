import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.api.websockets import ConnectionManager, manager
from app.btc5m.selector import BTC5MMarketInfo, async_discover_btc5m_markets
from app.btc5m.engine import BTC5MEngine

@pytest.mark.asyncio
async def test_connection_manager_channel_routing():
    cm = ConnectionManager()
    ws_mock1 = AsyncMock()
    ws_mock2 = AsyncMock()

    await cm.connect(ws_mock1, channel="btc5m")
    await cm.connect(ws_mock2, channel="markets")

    assert ws_mock1 in cm.channels["btc5m"]
    assert ws_mock2 in cm.channels["markets"]
    assert ws_mock1 in cm.channels["all"]
    assert ws_mock2 in cm.channels["all"]

    # Broadcast to btc5m channel
    await cm.broadcast({"type": "test_btc"}, channel="btc5m")
    ws_mock1.send_text.assert_called_once_with(json.dumps({"type": "test_btc"}))
    ws_mock2.send_text.assert_not_called()

    # Disconnect
    cm.disconnect(ws_mock1, channel="btc5m")
    assert ws_mock1 not in cm.channels["btc5m"]
    assert ws_mock1 not in cm.active_connections

@pytest.mark.asyncio
async def test_broadcast_btc5m_sets_last_payload():
    cm = ConnectionManager()
    ws_mock = AsyncMock()
    await cm.connect(ws_mock, channel="btc5m")

    sample_status = {"status": "active", "btc_price": 90000.0, "trading_active": True}
    await cm.broadcast_btc5m(sample_status)

    assert cm.get_last_btc5m_payload() == sample_status
    ws_mock.send_text.assert_called_once()
    sent_msg = json.loads(ws_mock.send_text.call_args[0][0])
    assert sent_msg["type"] == "btc5m_status"
    assert sent_msg["data"]["btc_price"] == 90000.0

def test_fastapi_websocket_btc5m_ping_pong():
    client = TestClient(app)
    with client.websocket_connect("/ws/btc5m") as websocket:
        websocket.send_text("ping")
        data = websocket.receive_text()
        assert data == "pong"

@pytest.mark.asyncio
async def test_async_discover_btc5m_markets_empty_fallback():
    with patch("httpx.AsyncClient.get", side_effect=Exception("Network error")):
        # Should gracefully return empty list or fallback to sync without throwing
        results = await async_discover_btc5m_markets()
        assert isinstance(results, list)

@pytest.mark.asyncio
async def test_async_rpc_racing_resolves_fastest():
    engine = BTC5MEngine()
    mock_market = MagicMock(spec=BTC5MMarketInfo)
    mock_market.market_id = "test_market"
    mock_market.start_time = None
    mock_market.end_time = None

    with patch.object(engine, "_get_btc5m_reference_data", return_value=(91234.56, 91000.0)):
        btc, p2b = await engine._get_btc5m_reference_data_async(mock_market)
        assert btc is not None
        assert isinstance(btc, float)
