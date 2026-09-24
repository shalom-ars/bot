"""
Fast 5M Master Engine & Coordinator.
Unifies Real-Time Oracle Feed, Market Discovery, Multi-Factor Scorer,
and Automated Top-Ranked Execution.
"""
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from app.fast5m.oracle import fast_oracle, SUPPORTED_ASSETS
from app.fast5m.discovery import fast_markets
from app.fast5m.scorer import fast_scorer, ScoredAsset
from app.fast5m.executor import fast_executor
from app.fast5m.squad import fast_squad

logger = logging.getLogger(__name__)


class Fast5MEngine:
    def __init__(self):
        self.running: bool = False
        self._broadcast_task: Optional[asyncio.Task] = None

    async def start(self):
        if self.running:
            return
        self.running = True
        logger.info("[Fast5M Engine] Starting master engine for all 7 fast prediction assets...")
        
        # Start child subsystems and background Squad system
        await fast_squad.start()
        await fast_oracle.start()
        await fast_markets.start()
        await fast_executor.start()
        
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        logger.info("[Fast5M Engine] All Fast 5M subsystems and Squad workers active and synchronized.")

    async def stop(self):
        self.running = False
        if self._broadcast_task and not self._broadcast_task.done():
            self._broadcast_task.cancel()
        await fast_executor.stop()
        await fast_markets.stop()
        await fast_oracle.stop()
        await fast_squad.stop()
        logger.info("[Fast5M Engine] Stopped.")

    async def _broadcast_loop(self):
        """Broadcasts real-time state to connected UI WebSocket clients."""
        while self.running:
            try:
                from app.api.websockets import manager
                if manager.active_connections:
                    payload = self.get_board_state()
                    # Broadcast to fast5m topic
                    await manager.broadcast({
                        "type": "fast5m_tick",
                        "data": payload
                    })
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[Fast5M Engine] Broadcast error: {e}")
            await asyncio.sleep(1.0)

    def get_board_state(self) -> Dict[str, Any]:
        """Generate comprehensive live dashboard state for UI board."""
        conf_threshold = float(fast_executor.settings.get("confidence_threshold", 70.0))
        scored = fast_scorer.score_all_assets(conf_threshold)
        
        top_pick: Optional[Dict[str, Any]] = None
        if scored:
            top_pick = scored[0].to_dict()

        assets_data = [item.to_dict() for item in scored]
        
        now = time.time()
        now_ts = int(now)
        epoch_bucket = now_ts - (now_ts % 300)
        global_remaining_sec = max(0, (epoch_bucket + 300) - now_ts)

        # Update Squad worker heartbeats
        fast_squad.oracle_scout.heartbeat(
            latency_ms=assets_data[0].get("latency_ms", 18.0) if assets_data else 18.0,
            details={"active_streams": len(assets_data), "source": "Chainlink/Pyth/Hyperliquid"}
        )
        fast_squad.technical_analyst.heartbeat(
            details={"ranked_assets": len(assets_data), "top_pick": top_pick.get("asset") if top_pick else None}
        )
        fast_squad.risk_commander.heartbeat(
            details={
                "position_size": fast_executor.settings.get("position_size_usd", "10.0"),
                "max_pools": fast_executor.settings.get("max_active_pools", "1"),
                "direction": fast_executor.settings.get("strategy_direction", "BOTH"),
                "has_active_trade": fast_executor.active_trade is not None
            }
        )

        return {
            "timestamp": now,
            "epoch_bucket": epoch_bucket,
            "epoch_remaining_sec": global_remaining_sec,
            "epoch_progress_pct": round(((300 - global_remaining_sec) / 300.0) * 100.0, 1),
            "assets": assets_data,
            "top_ranked_pair": top_pick,
            "active_trade": fast_executor.active_trade,
            "active_trades": fast_executor.get_active_trades(),
            "settings": fast_executor.settings,
            "auto_trading_active": fast_executor.settings.get("auto_trading_enabled", "true").lower() in ("true", "1", "yes"),
            "system_health": fast_squad.get_system_health(),
        }


# Global singleton instance
fast5m_engine = Fast5MEngine()
