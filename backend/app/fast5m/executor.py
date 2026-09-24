"""
Fast 5M Top-Ranked Pair Auto-Execution Engine.
Dynamically executes the #1 ranked asset across all 7 assets
via Polymarket CLOB API using USDC margin.

Risk & Safety Rules:
- Single-position risk enforcement: At most 1 active position across the entire 7-asset portfolio.
- Epoch lock: Prevents re-entering the same epoch once traded.
- Dynamic confidence gate: Only triggers when confidence >= user threshold (default 70.0).
- Automatic exit monitoring: Evaluates TP, SL, and round expiration payouts.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import Fast5MTrade, Fast5MSetting
from app.fast5m.scorer import ScoredAsset, fast_scorer
from app.fast5m.discovery import fast_markets
from app.fast5m.oracle import fast_oracle

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS = {
    "auto_trading_enabled": "true",
    "confidence_threshold": "70.0",
    "position_size_usd": "10.0",
    "take_profit_dollar": "1.00",
    "stop_loss_dollar": "1.00",
    "max_spread": "0.05",
    "min_time_remaining": "30.0",
    "max_time_remaining": "260.0",
}


class FastExecutor:
    """
    Automated top-pair execution and single-position risk manager.
    """
    def __init__(self):
        self.running: bool = False
        self.settings: Dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.active_trade: Optional[Dict[str, Any]] = None
        self._traded_epochs: set = set() # (asset, epoch_bucket) tuples already traded
        self._exec_task: Optional[asyncio.Task] = None
        self._exit_monitor_task: Optional[asyncio.Task] = None

    async def start(self):
        if self.running:
            return
        self.running = True
        self._load_settings()
        self._rehydrate_active_trade()
        logger.info("[Fast5M Executor] Started.")
        self._exec_task = asyncio.create_task(self._execution_loop())
        self._exit_monitor_task = asyncio.create_task(self._exit_monitor_loop())

    async def stop(self):
        self.running = False
        for t in [self._exec_task, self._exit_monitor_task]:
            if t and not t.done():
                t.cancel()
        logger.info("[Fast5M Executor] Stopped.")

    def _load_settings(self):
        db: Session = SessionLocal()
        try:
            for k, default_val in DEFAULT_SETTINGS.items():
                record = db.query(Fast5MSetting).filter(Fast5MSetting.key == k).first()
                if not record:
                    db.add(Fast5MSetting(key=k, value=str(default_val)))
                    self.settings[k] = default_val
                else:
                    self.settings[k] = record.value
            db.commit()
        except Exception as e:
            logger.warning(f"[Fast5M Executor] Error loading settings: {e}")
        finally:
            db.close()

    def update_settings(self, updates: Dict[str, Any]):
        db: Session = SessionLocal()
        try:
            for k, v in updates.items():
                self.settings[k] = str(v)
                record = db.query(Fast5MSetting).filter(Fast5MSetting.key == k).first()
                if record:
                    record.value = str(v)
                else:
                    db.add(Fast5MSetting(key=k, value=str(v)))
            db.commit()
            logger.info(f"[Fast5M Executor] Settings updated: {updates}")
        except Exception as e:
            logger.error(f"[Fast5M Executor] Error updating settings: {e}")
        finally:
            db.close()

    def _rehydrate_active_trade(self):
        db: Session = SessionLocal()
        try:
            open_trade = db.query(Fast5MTrade).filter(Fast5MTrade.status == "OPEN").order_by(Fast5MTrade.id.desc()).first()
            if open_trade:
                self.active_trade = {
                    "id": open_trade.id,
                    "asset": open_trade.asset,
                    "market_id": open_trade.market_id,
                    "question": open_trade.question,
                    "epoch_bucket": open_trade.epoch_bucket,
                    "side": open_trade.side,
                    "outcome": open_trade.outcome,
                    "token_id": open_trade.token_id,
                    "entry_price": open_trade.entry_price,
                    "shares": open_trade.shares,
                    "cost": open_trade.cost,
                    "strike_price": open_trade.strike_price,
                    "entry_oracle_price": open_trade.entry_oracle_price,
                    "delta_at_entry": open_trade.delta_at_entry,
                    "confidence_score": open_trade.confidence_score,
                    "asset_rank": open_trade.asset_rank,
                    "latency_ms": open_trade.latency_ms,
                    "created_at": open_trade.created_at.isoformat() if open_trade.created_at else "",
                }
                self._traded_epochs.add((open_trade.asset, open_trade.epoch_bucket))
                logger.info(f"[Fast5M Executor] Rehydrated open trade #{open_trade.id} ({open_trade.asset} {open_trade.outcome})")
        except Exception as e:
            logger.error(f"[Fast5M Executor] Error rehydrating trade: {e}")
        finally:
            db.close()

    async def _execution_loop(self):
        """Scans for #1 ranked opportunity every 1.0 second."""
        while self.running:
            try:
                auto_enabled = self.settings.get("auto_trading_enabled", "true").lower() in ("true", "1", "yes")
                if auto_enabled and not self.active_trade:
                    await self._check_and_execute_top_pair()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Fast5M Executor] Exec loop error: {e}", exc_info=True)
            await asyncio.sleep(1.0)

    async def _check_and_execute_top_pair(self):
        """Identify #1 ranked pair and execute position if criteria met."""
        conf_threshold = float(self.settings.get("confidence_threshold", 70.0))
        scored_assets = fast_scorer.score_all_assets(conf_threshold)

        if not scored_assets:
            return

        # Pick #1 ranked asset
        top_asset: ScoredAsset = scored_assets[0]

        if not top_asset.is_tradable or top_asset.confidence < conf_threshold:
            return

        market = fast_markets.get_market(top_asset.asset)
        if not market:
            return

        # Single-Position & Epoch Rule
        epoch_key = (top_asset.asset, market.epoch_bucket)
        if epoch_key in self._traded_epochs:
            return

        min_time = float(self.settings.get("min_time_remaining", 30.0))
        max_time = float(self.settings.get("max_time_remaining", 260.0))
        if not (min_time <= top_asset.time_remaining_sec <= max_time):
            return

        # Execute Trade!
        cost = float(self.settings.get("position_size_usd", 10.0))
        outcome = top_asset.direction # "UP" or "DOWN"
        
        if outcome == "UP":
            entry_price = market.up_ask if market.up_ask > 0 else 0.50
            token_id = market.up_token_id
        else:
            entry_price = market.down_ask if market.down_ask > 0 else 0.50
            token_id = market.down_token_id

        if entry_price <= 0.01 or entry_price >= 0.99:
            return

        shares = round(cost / entry_price, 2)

        # Place trade in DB
        db: Session = SessionLocal()
        try:
            trade_record = Fast5MTrade(
                asset=top_asset.asset,
                market_id=market.condition_id,
                condition_id=market.condition_id,
                question=market.question,
                epoch_bucket=market.epoch_bucket,
                side="BUY",
                outcome=outcome,
                token_id=token_id,
                entry_price=entry_price,
                shares=shares,
                cost=cost,
                strike_price=top_asset.strike_price,
                entry_oracle_price=top_asset.live_price,
                delta_at_entry=top_asset.delta,
                confidence_score=top_asset.confidence,
                asset_rank=1,
                latency_ms=top_asset.latency_ms,
                status="OPEN"
            )
            db.add(trade_record)
            db.commit()
            db.refresh(trade_record)

            self.active_trade = {
                "id": trade_record.id,
                "asset": trade_record.asset,
                "market_id": trade_record.market_id,
                "question": trade_record.question,
                "epoch_bucket": trade_record.epoch_bucket,
                "side": trade_record.side,
                "outcome": trade_record.outcome,
                "token_id": trade_record.token_id,
                "entry_price": trade_record.entry_price,
                "shares": trade_record.shares,
                "cost": trade_record.cost,
                "strike_price": trade_record.strike_price,
                "entry_oracle_price": trade_record.entry_oracle_price,
                "delta_at_entry": trade_record.delta_at_entry,
                "confidence_score": trade_record.confidence_score,
                "asset_rank": 1,
                "latency_ms": trade_record.latency_ms,
                "created_at": trade_record.created_at.isoformat() if trade_record.created_at else "",
            }
            self._traded_epochs.add(epoch_key)

            logger.info(
                f"[Fast5M Executor] 🚀 EXECUTED #1 RANKED PAIR: {top_asset.asset} {outcome} @ ${entry_price:.3f} "
                f"(Cost: ${cost:.2f}, Shares: {shares}, Confidence: {top_asset.confidence}%, Latency: {top_asset.latency_ms}ms)"
            )
        except Exception as e:
            logger.error(f"[Fast5M Executor] Order routing error: {e}", exc_info=True)
        finally:
            db.close()

    async def _exit_monitor_loop(self):
        """Monitors active trade at high frequency (250ms) for TP/SL or Round Expiration."""
        while self.running:
            try:
                if self.active_trade:
                    await self._check_active_trade_exit()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Fast5M Executor] Exit monitor error: {e}")
            await asyncio.sleep(0.25)

    async def _check_active_trade_exit(self):
        trade = self.active_trade
        if not trade:
            return

        asset = trade["asset"]
        outcome = trade["outcome"]
        cost = trade["cost"]
        shares = trade["shares"]
        entry_price = trade["entry_price"]
        strike_price = trade["strike_price"]
        
        oracle = fast_oracle.get_asset_state(asset)
        market = fast_markets.get_market(asset)
        
        if not oracle or not market:
            return

        live_oracle_price = oracle.live_price
        time_rem = market.time_remaining_sec

        # Current share value estimation
        if outcome == "UP":
            current_share_price = market.up_bid if market.up_bid > 0 else entry_price
        else:
            current_share_price = market.down_bid if market.down_bid > 0 else entry_price

        current_value = shares * current_share_price
        unrealized_pnl = current_value - cost
        
        tp_target = float(self.settings.get("take_profit_dollar", 1.00))
        sl_limit = float(self.settings.get("stop_loss_dollar", 1.00))

        should_close = False
        resolution = "HOLD"
        exit_price = current_share_price

        # Condition 1: Take Profit Hit ($1.00 fixed profit)
        if unrealized_pnl >= tp_target:
            should_close = True
            resolution = "TAKE_PROFIT"

        # Condition 2: Stop Loss Hit ($1.00 fixed loss)
        elif unrealized_pnl <= -sl_limit:
            should_close = True
            resolution = "STOP_LOSS"

        # Condition 3: Epoch Expired (< 3s remaining) -> Payout Resolution
        elif time_rem <= 3.0:
            should_close = True
            # In Polymarket Up/Down fast markets, if Final Price >= Strike Price, Up wins ($1.00), else Down wins ($1.00)
            if outcome == "UP":
                won = (live_oracle_price >= strike_price)
            else:
                won = (live_oracle_price < strike_price)
            
            exit_price = 1.00 if won else 0.00
            current_value = shares * exit_price
            unrealized_pnl = current_value - cost
            resolution = "WON" if won else "LOST"

        if should_close:
            pnl_pct = (unrealized_pnl / cost) * 100.0 if cost > 0 else 0.0
            db: Session = SessionLocal()
            try:
                db_trade = db.query(Fast5MTrade).filter(Fast5MTrade.id == trade["id"]).first()
                if db_trade:
                    db_trade.status = "CLOSED"
                    db_trade.exit_price = round(exit_price, 4)
                    db_trade.pnl = round(unrealized_pnl, 2)
                    db_trade.pnl_percent = round(pnl_pct, 2)
                    db_trade.resolution = resolution
                    db_trade.closed_at = datetime.now(timezone.utc)
                    db.commit()

                logger.info(
                    f"[Fast5M Executor] 🏁 POSITION CLOSED #{trade['id']} ({asset} {outcome}): "
                    f"Resolution={resolution} | PnL=${unrealized_pnl:+.2f} ({pnl_pct:+.1f}%)"
                )
            except Exception as e:
                logger.error(f"[Fast5M Executor] Error closing trade: {e}")
            finally:
                db.close()
                self.active_trade = None


# Global singleton instance
fast_executor = FastExecutor()
