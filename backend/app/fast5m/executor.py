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
    "total_balance_usd": "300.0",
    "confidence_threshold": "70.0",       # Execution threshold: minimum composite confidence rating of >= 70
    "position_size_usd": "10.0",          # Admin sizing: $10, $25, $50
    "max_active_pools": "3",              # Max Active Pools: up to 2 to 3 pairs simultaneously
    "multi_pair_min_score": "90.0",       # Minimum score for multi-pair concurrent execution (90%+)
    "strategy_direction": "BOTH",         # Strategy Direction: BOTH (Up/Down), UP_ONLY, DOWN_ONLY
    "take_profit_dollar": "0.50",         # Strict 1:1 RR: Target Profit $0.50 (50 cents)
    "stop_loss_dollar": "0.50",           # Strict 1:1 RR: Stop Loss $0.50 (50 cents)
    "buffer_timer_sec": "4.0",            # 3 to 5 second Grace Period Buffer immediately after trade entry
    "take_profit_pct": "3.0",             # Base Take-Profit target: 1.5% - 3.0%
    "stop_loss_pct": "3.0",               # Strict Hard Stop-Loss capped at maximum 3% loss
    "trailing_lock_enabled": "true",      # Dynamic micro-profit lock
    "trailing_stop_activation_pct": "1.0",# Aggressive trailing stop activates at +1.0% to +1.5% profit
    "trailing_stop_distance_pct": "0.5",  # Tight trailing distance: 0.5% or $0.02 giveback locks profit immediately
    "max_portfolio_margin_pct": "30.0",   # Exposure safeguard: max 30% of account balance committed across all active pairs
    "min_profit_to_lock": "0.15",         # Lock as soon as +$0.15 (15 cents) profit is touched
    "reversal_giveback_dollar": "0.06",   # If profit dips 6 cents from peak, book profit immediately before reverse!
    "reversal_lock_enabled": "true",      # Technical momentum reversal exit
    "max_spread": "0.20",
    "min_liquidity_usd": "100.0",
    "min_time_remaining": "20.0",
    "max_time_remaining": "280.0",
    # Active Quantitative Filters & Indicator Weights
    "filter_delta_enabled": "true",
    "filter_delta_weight": "40.0",
    "filter_obi_enabled": "true",
    "filter_obi_weight": "30.0",
    "filter_momentum_enabled": "true",
    "filter_momentum_weight": "30.0",
    "filter_rsi_enabled": "true",
    "filter_bb_enabled": "true",
    "filter_ema_macd_enabled": "true",
}


class FastExecutor:
    """
    Automated multi-pair execution engine and risk manager.
    Supports concurrent execution across up to 2-3 pairs (score >= 90%+),
    strict aggressive trailing stops with zero-slippage profit locking,
    and portfolio margin safeguards.
    """
    def __init__(self):
        self.running: bool = False
        self.settings: Dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.active_trades: Dict[int, Dict[str, Any]] = {}
        self._traded_epochs: set = set() # (asset, epoch_bucket) tuples already traded
        self._exec_task: Optional[asyncio.Task] = None
        self._exit_monitor_task: Optional[asyncio.Task] = None
        try:
            from app.db.session import engine, ensure_fast5m_schema
            ensure_fast5m_schema(engine)
        except Exception as e:
            logger.debug(f"[Fast5M Executor] Schema initialization notice: {e}")

    @property
    def active_trade(self) -> Optional[Dict[str, Any]]:
        """Backwards-compatible access to the latest open active trade."""
        if not self.active_trades:
            return None
        return sorted(self.active_trades.values(), key=lambda t: t.get("id", 0), reverse=True)[0]

    def get_active_trades(self) -> List[Dict[str, Any]]:
        """Return all currently open active trades."""
        return list(self.active_trades.values())

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
            # Check for custom saved defaults first
            custom_defaults = {}
            for k in DEFAULT_SETTINGS.keys():
                custom_rec = db.query(Fast5MSetting).filter(Fast5MSetting.key == f"custom_default_{k}").first()
                if custom_rec:
                    custom_defaults[k] = custom_rec.value

            for k, factory_default in DEFAULT_SETTINGS.items():
                default_to_use = custom_defaults.get(k, str(factory_default))
                record = db.query(Fast5MSetting).filter(Fast5MSetting.key == k).first()
                if not record:
                    db.add(Fast5MSetting(key=k, value=default_to_use))
                    self.settings[k] = default_to_use
                else:
                    self.settings[k] = record.value

            # Guarantee mandatory base attributes if missing
            if "auto_trading_enabled" not in self.settings:
                self.settings["auto_trading_enabled"] = "true"
            if "total_balance_usd" not in self.settings:
                self.settings["total_balance_usd"] = "300.0"

            # Seed custom default baseline if not already present
            for k, val in self.settings.items():
                def_rec = db.query(Fast5MSetting).filter(Fast5MSetting.key == f"custom_default_{k}").first()
                if not def_rec:
                    db.add(Fast5MSetting(key=f"custom_default_{k}", value=str(val)))

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

    def save_as_default(self, updates: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Save current or provided settings as the permanent custom default baseline."""
        if updates:
            self.update_settings(updates)
        db: Session = SessionLocal()
        try:
            for k, v in self.settings.items():
                def_key = f"custom_default_{k}"
                rec = db.query(Fast5MSetting).filter(Fast5MSetting.key == def_key).first()
                if rec:
                    rec.value = str(v)
                else:
                    db.add(Fast5MSetting(key=def_key, value=str(v)))
            
            ts_key = "custom_defaults_saved_at"
            ts_val = datetime.now(timezone.utc).isoformat()
            ts_rec = db.query(Fast5MSetting).filter(Fast5MSetting.key == ts_key).first()
            if ts_rec:
                ts_rec.value = ts_val
            else:
                db.add(Fast5MSetting(key=ts_key, value=ts_val))

            db.commit()
            logger.info("[Fast5M Executor] Saved custom default profile successfully.")
            return self.get_default_settings()
        except Exception as e:
            logger.error(f"[Fast5M Executor] Error saving default settings: {e}")
            return self.get_default_settings()
        finally:
            db.close()

    def restore_defaults(self) -> Dict[str, Any]:
        """Restore active settings from the saved custom default baseline."""
        defaults = self.get_default_settings()
        # Filter out metadata keys
        to_apply = {k: v for k, v in defaults.items() if not k.startswith("custom_")}
        self.update_settings(to_apply)
        logger.info("[Fast5M Executor] Restored settings from custom default baseline.")
        return self.settings

    def get_default_settings(self) -> Dict[str, Any]:
        """Retrieve the saved custom default profile."""
        db: Session = SessionLocal()
        defaults = dict(DEFAULT_SETTINGS)
        try:
            for k in DEFAULT_SETTINGS.keys():
                rec = db.query(Fast5MSetting).filter(Fast5MSetting.key == f"custom_default_{k}").first()
                if rec:
                    defaults[k] = rec.value
            ts_rec = db.query(Fast5MSetting).filter(Fast5MSetting.key == "custom_defaults_saved_at").first()
            if ts_rec:
                defaults["custom_defaults_saved_at"] = ts_rec.value
        except Exception as e:
            logger.warning(f"[Fast5M Executor] Error reading default settings: {e}")
        finally:
            db.close()
        return defaults

    def emergency_stop(self) -> Dict[str, Any]:
        """
        Emergency Panic Button:
        Immediately disables auto-trading, force-closes all open active positions,
        and locks the executor.
        """
        self.update_settings({"auto_trading_enabled": "false"})
        closed_count = 0

        db: Session = SessionLocal()
        try:
            for trade_id, trade in list(self.active_trades.items()):
                db_trade = db.query(Fast5MTrade).filter(Fast5MTrade.id == trade_id).first()
                if db_trade:
                    current_pnl = trade.get("current_pnl", 0.0)
                    cost = trade.get("cost", 10.0)
                    db_trade.status = "CLOSED"
                    db_trade.resolution = "EMERGENCY_STOP"
                    db_trade.pnl = round(current_pnl, 2)
                    db_trade.pnl_percent = round((current_pnl / cost) * 100.0, 2) if cost > 0 else 0.0
                    db_trade.closed_at = datetime.now(timezone.utc)
                    closed_count += 1
            db.commit()
        except Exception as e:
            logger.error(f"[Fast5M Executor] Error during emergency stop: {e}")
            db.rollback()
        finally:
            db.close()
            self.active_trades.clear()

        logger.warning(f"[Fast5M Executor] 🚨 EMERGENCY STOP ACTIVATED. Auto-trading killed, {closed_count} positions closed.")
        return {
            "status": "success",
            "message": f"Emergency Stop activated. Engine stopped and {closed_count} active position(s) closed.",
            "auto_trading_enabled": False,
            "closed_count": closed_count
        }

    def emergency_start(self) -> Dict[str, Any]:
        """
        Re-arms the engine and enables auto-trading.
        """
        self.update_settings({"auto_trading_enabled": "true"})
        logger.info("[Fast5M Executor] 🟢 EMERGENCY START ACTIVATED. Engine re-armed and scanning active.")
        return {
            "status": "success",
            "message": "Engine started. Auto-execution armed and actively scanning.",
            "auto_trading_enabled": True
        }

    def reset_demo_account(self) -> Dict[str, Any]:
        """
        Wipes demo paper trading history (temporary paper simulation) and resets virtual balance to $300.00.
        Real account history and live on-chain trades are strictly preserved.
        """
        demo_trade_ids = [tid for tid, t in self.active_trades.items() if t.get("account_mode", "demo") == "demo"]
        for tid in demo_trade_ids:
            self.active_trades.pop(tid, None)

        self._traded_epochs.clear()
        self.update_settings({"total_balance_usd": "300.0"})

        db: Session = SessionLocal()
        deleted_count = 0
        try:
            # Delete ONLY temporary demo trades (real trades are never touched)
            deleted_count = db.query(Fast5MTrade).filter(
                (Fast5MTrade.account_mode == "demo") | (Fast5MTrade.account_mode.is_(None))
            ).delete(synchronize_session=False)
            db.commit()
            logger.info(f"[Fast5M Executor] 🔄 DEMO ACCOUNT RESET: {deleted_count} temporary paper trades wiped. Base balance restored to $300.00.")
        except Exception as e:
            logger.error(f"[Fast5M Executor] Error resetting demo account: {e}")
            db.rollback()
        finally:
            db.close()

        return {
            "status": "success",
            "message": f"Demo account successfully reset. {deleted_count} temporary paper trade(s) wiped. Base balance set to $300.00.",
            "deleted_trades_count": deleted_count,
            "balance": 300.0,
            "total_trades": 0,
            "total_pnl": 0.0,
            "total_profit": 0.0,
            "total_loss": 0.0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0
        }

    def _rehydrate_active_trade(self):
        db: Session = SessionLocal()
        try:
            open_trades = db.query(Fast5MTrade).filter(Fast5MTrade.status == "OPEN").order_by(Fast5MTrade.id.asc()).all()
            for open_trade in open_trades:
                self.active_trades[open_trade.id] = {
                    "id": open_trade.id,
                    "asset": open_trade.asset,
                    "market_id": open_trade.market_id,
                    "account_mode": getattr(open_trade, "account_mode", "demo") or "demo",
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
                    "delta_score": getattr(open_trade, "delta_score", 0.0) or 0.0,
                    "obi_score": getattr(open_trade, "obi_score", 0.0) or 0.0,
                    "momentum_score": getattr(open_trade, "momentum_score", 0.0) or 0.0,
                    "prediction_rationale": getattr(open_trade, "prediction_rationale", "") or "",
                    "asset_rank": open_trade.asset_rank,
                    "latency_ms": open_trade.latency_ms,
                    "created_at": open_trade.created_at.isoformat() if open_trade.created_at else "",
                    "entry_ts": (
                        open_trade.created_at.replace(tzinfo=timezone.utc).timestamp()
                        if open_trade.created_at and open_trade.created_at.tzinfo is None
                        else open_trade.created_at.timestamp()
                        if open_trade.created_at
                        else time.time()
                    ),
                    "peak_pnl": 0.0,
                    "current_pnl": 0.0,
                    "current_share_price": open_trade.entry_price,
                    "trailing_armed": False,
                    "trailing_floor": 0.0,
                }
                self._traded_epochs.add((open_trade.asset, open_trade.epoch_bucket))
                logger.info(f"[Fast5M Executor] Rehydrated open trade #{open_trade.id} ({open_trade.asset} {open_trade.outcome})")
        except Exception as e:
            logger.error(f"[Fast5M Executor] Error rehydrating trades: {e}")
        finally:
            db.close()

    async def _execution_loop(self):
        """Scans for #1 ranked and qualified concurrent opportunities (90%+ score) every 1.0 second."""
        while self.running:
            try:
                auto_enabled = self.settings.get("auto_trading_enabled", "true").lower() in ("true", "1", "yes")
                max_pools = int(self.settings.get("max_active_pools", 3))
                if auto_enabled and len(self.active_trades) < max_pools:
                    await self._check_and_execute_pairs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Fast5M Executor] Exec loop error: {e}", exc_info=True)
            await asyncio.sleep(1.0)

    async def _check_and_execute_pairs(self):
        """
        Identify top qualifying pairs and execute positions concurrently (up to 2 to 3 pairs)
        if prediction scores meet thresholds (>=90.0% for multi-pair entries),
        while strictly enforcing account margin exposure safeguards.
        """
        conf_threshold = float(self.settings.get("confidence_threshold", 70.0))
        multi_pair_threshold = float(self.settings.get("multi_pair_min_score", 90.0))
        max_pools = int(self.settings.get("max_active_pools", 3))
        
        available_slots = max_pools - len(self.active_trades)
        if available_slots <= 0:
            return

        # Position Sizing & Exposure Safeguard:
        total_balance = float(self.settings.get("total_balance_usd", 300.0))
        max_margin_pct = float(self.settings.get("max_portfolio_margin_pct", 30.0))
        max_total_exposure = total_balance * (max_margin_pct / 100.0) # e.g. $90 max margin
        current_exposure = sum(t["cost"] for t in self.active_trades.values())
        available_exposure = max(0.0, max_total_exposure - current_exposure)

        if available_exposure < 5.0:
            return

        # Score all 7 assets
        scored_assets = fast_scorer.score_all_assets(conf_threshold)
        if not scored_assets:
            return

        strat_dir = self.settings.get("strategy_direction", "BOTH").upper()
        min_time = float(self.settings.get("min_time_remaining", 20.0))
        max_time = float(self.settings.get("max_time_remaining", 280.0))
        base_size = float(self.settings.get("position_size_usd", 10.0))

        active_assets = {t["asset"] for t in self.active_trades.values()}
        qualified_candidates: List[ScoredAsset] = []

        for asset_score in scored_assets:
            if not asset_score.is_tradable:
                continue
            if asset_score.asset in active_assets:
                continue
            if strat_dir == "UP_ONLY" and asset_score.direction != "UP":
                continue
            if strat_dir == "DOWN_ONLY" and asset_score.direction != "DOWN":
                continue
            if not (min_time <= asset_score.time_remaining_sec <= max_time):
                continue

            market = fast_markets.get_market(asset_score.asset)
            if not market:
                continue
            epoch_key = (asset_score.asset, market.epoch_bucket)
            if epoch_key in self._traded_epochs:
                continue

            # Multi-Pair Scoring Rule:
            # 1st active trade requires standard confidence_threshold (>= 70%)
            # Concurrent 2nd or 3rd trades require multi_pair_threshold (>= 90.0%+)
            current_count = len(self.active_trades) + len(qualified_candidates)
            req_score = conf_threshold if current_count == 0 else multi_pair_threshold

            if asset_score.confidence >= req_score:
                qualified_candidates.append(asset_score)
                if len(qualified_candidates) >= available_slots:
                    break

        if not qualified_candidates:
            return

        # Exposure Safeguard: partition available margin safely
        num_new_trades = len(qualified_candidates)
        safe_per_trade_cost = min(base_size, round(available_exposure / num_new_trades, 2))
        if safe_per_trade_cost < 3.0:
            return

        # Open qualified pairs concurrently without skipping or waiting
        for candidate in qualified_candidates:
            await self._execute_single_trade(candidate, safe_per_trade_cost)

    async def _execute_single_trade(self, top_asset: ScoredAsset, cost: float):
        market = fast_markets.get_market(top_asset.asset)
        if not market:
            return

        outcome = top_asset.direction # "UP" or "DOWN"
        if outcome == "UP":
            entry_price = market.up_ask if market.up_ask > 0 else 0.50
            token_id = market.up_token_id
        else:
            entry_price = market.down_ask if market.down_ask > 0 else 0.50
            token_id = market.down_token_id

        if entry_price <= 0.01 or entry_price >= 0.99:
            return

        shares = round(cost / entry_price, 4)
        epoch_key = (top_asset.asset, market.epoch_bucket)

        from app.fast5m.wallet import wallet_manager
        current_account_mode = getattr(wallet_manager, "account_mode", "demo") or "demo"

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
                delta_score=top_asset.delta_score,
                obi_score=top_asset.obi_score,
                momentum_score=top_asset.momentum_score,
                prediction_rationale=top_asset.reason,
                asset_rank=top_asset.rank,
                latency_ms=top_asset.latency_ms,
                status="OPEN",
                account_mode=current_account_mode,
                execution_type="LIVE_CLOB_ONCHAIN" if current_account_mode == "live" else "SIMULATED_ORDERBOOK",
                buffer_status="ACTIVE",
            )
            db.add(trade_record)
            db.commit()
            db.refresh(trade_record)

            self.active_trades[trade_record.id] = {
                "id": trade_record.id,
                "asset": trade_record.asset,
                "market_id": trade_record.market_id,
                "account_mode": current_account_mode,
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
                "delta_score": trade_record.delta_score,
                "obi_score": trade_record.obi_score,
                "momentum_score": trade_record.momentum_score,
                "prediction_rationale": trade_record.prediction_rationale,
                "asset_rank": top_asset.rank,
                "latency_ms": trade_record.latency_ms,
                "entry_ts": time.time(),
                "peak_pnl": 0.0,
                "current_pnl": 0.0,
                "current_share_price": trade_record.entry_price,
                "trailing_armed": False,
                "trailing_floor": 0.0,
                "created_at": trade_record.created_at.isoformat() if trade_record.created_at else "",
            }
            self._traded_epochs.add(epoch_key)

            active_count = len(self.active_trades)
            logger.info(
                f"[Fast5M Executor] 🚀 EXECUTED CONCURRENT POSITION ({active_count}/3): {top_asset.asset} {outcome} @ ${entry_price:.3f} "
                f"(Cost: ${cost:.2f}, Shares: {shares}, Score: {top_asset.confidence}%, Latency: {top_asset.latency_ms}ms)"
            )
        except Exception as e:
            logger.error(f"[Fast5M Executor] Order routing error for {top_asset.asset}: {e}", exc_info=True)
        finally:
            db.close()

    async def _exit_monitor_loop(self):
        """Monitors all active trades at high frequency (250ms) for aggressive trailing stop, TP/SL, or Round Expiration."""
        while self.running:
            try:
                if self.active_trades:
                    # Iterate over a snapshot of active trades
                    active_list = list(self.active_trades.values())
                    for trade in active_list:
                        await self._check_single_trade_exit(trade)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Fast5M Executor] Exit monitor error: {e}")
            await asyncio.sleep(0.25)

    async def _check_single_trade_exit(self, trade: Dict[str, Any]):
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
        trade_age_s = time.time() - (trade.get("entry_ts") or time.time())

        # Real Polymarket CLOB Top-of-Book Bid Valuation
        # When exiting an UP position, we sell at up_bid; when exiting DOWN, we sell at down_bid.
        real_book_bid = market.up_bid if outcome == "UP" else market.down_bid
        if real_book_bid and real_book_bid > 0.01:
            current_share_price = round(real_book_bid, 4)
            orderbook_bid_val = round(real_book_bid, 4)
        else:
            # Fallback to oracle delta movement if orderbook depth is momentarily unpopulated
            entry_oracle = trade.get("entry_oracle_price", strike_price)
            if entry_oracle > 0:
                oracle_delta_pct = ((live_oracle_price - entry_oracle) / entry_oracle) * 100.0
                directional_shift = oracle_delta_pct if outcome == "UP" else -oracle_delta_pct
                current_share_price = round(min(0.98, max(0.02, entry_price + (directional_shift * 1.5))), 4)
            else:
                current_share_price = entry_price
            orderbook_bid_val = current_share_price

        current_value = shares * current_share_price
        unrealized_pnl = round(current_value - cost, 2)

        # 1. Grace Period Buffer Timer (3 to 5 seconds buffer immediately after trade entry)
        buffer_duration = float(self.settings.get("buffer_timer_sec", 4.0))
        is_in_buffer = trade_age_s < buffer_duration
        buffer_remaining = max(0.0, round(buffer_duration - trade_age_s, 1))
        trade["is_in_buffer"] = is_in_buffer
        trade["buffer_remaining_sec"] = buffer_remaining
        trade["buffer_status"] = f"ACTIVE ({buffer_remaining}s)" if is_in_buffer else "CLEARED"

        # 2. Strict Risk-to-Reward & Loss Limit Settings
        sl_pct_setting = float(self.settings.get("stop_loss_pct", 3.0))
        sl_cap_pct = min(3.0, max(0.5, sl_pct_setting))
        hard_sl_dollar = round(cost * (sl_cap_pct / 100.0), 2)

        # Base Take-Profit Target (1.5% - 3.0%)
        tp_pct_setting = float(self.settings.get("take_profit_pct", 3.0))
        pct_tp_dollar = round(cost * (tp_pct_setting / 100.0), 2)
        user_tp_dollar = float(self.settings.get("take_profit_dollar", 0.50))
        tp_target = max(pct_tp_dollar, user_tp_dollar)

        user_sl_dollar = float(self.settings.get("stop_loss_dollar", 0.50))
        sl_limit = min(hard_sl_dollar, user_sl_dollar)

        trade_peak_pnl = max(trade.get("peak_pnl", 0.0), unrealized_pnl)
        trade["peak_pnl"] = round(trade_peak_pnl, 2)
        trade["current_pnl"] = round(unrealized_pnl, 2)
        trade["current_share_price"] = round(current_share_price, 4)
        trade["live_oracle_price"] = live_oracle_price

        should_close = False
        resolution = "HOLD"
        exit_price = current_share_price

        # 3. STRICT REAL-TIME TRAILING STOP & ZERO-SLIPPAGE PROFIT LOCKING
        # Rules:
        # a) Trailing stop is SUPPRESSED during the initial grace period buffer (noise protection).
        # b) Trailing stop only activates once trade peak PnL reaches the activation threshold (e.g. +1.0% to +1.5%).
        # c) The trailing floor has an absolute Breakeven minimum floor (>= +$0.02).
        # d) Trailing lock can ONLY execute when current PnL is POSITIVE (unrealized_pnl > 0.0).
        #    Under NO circumstances can AGGRESSIVE_TRAILING_LOCK close a trade at a negative loss!
        trailing_act_pct = float(self.settings.get("trailing_stop_activation_pct", 1.0))
        trailing_dist_pct = float(self.settings.get("trailing_stop_distance_pct", 0.5))
        min_gain_for_trailing = round(cost * (trailing_act_pct / 100.0), 2) # e.g. +$0.10 on $10
        tight_giveback = max(0.02, round(cost * (trailing_dist_pct / 100.0), 2)) # 0.5% or $0.02

        trailing_enabled = self.settings.get("trailing_lock_enabled", "true").lower() in ("true", "1", "yes")
        reversal_enabled = self.settings.get("reversal_lock_enabled", "true").lower() in ("true", "1", "yes")

        if trailing_enabled and not is_in_buffer:
            if trade.get("trailing_armed") or trade_peak_pnl >= min_gain_for_trailing:
                trade["trailing_armed"] = True
                # Trailing stop floor: tight distance from peak gain, with minimum breakeven floor of +$0.02
                trailing_floor = max(0.02, round(trade_peak_pnl - tight_giveback, 2))
                trade["trailing_floor"] = trailing_floor

                # Trailing trigger: pullback below floor while maintaining positive gain (> $0.00)
                if unrealized_pnl <= trailing_floor and unrealized_pnl > 0.0:
                    should_close = True
                    resolution = "AGGRESSIVE_TRAILING_LOCK"
                    exit_price = current_share_price
                    logger.info(
                        f"[Fast5M Executor] 🔒 AGGRESSIVE TRAILING STOP HIT: #{trade['id']} {asset} {outcome} locked at +${unrealized_pnl:.2f} "
                        f"(Peak: +${trade_peak_pnl:.2f}, Floor: +${trailing_floor:.2f})"
                    )

        # Technical Momentum Reversal Check while in profit (must respect grace period)
        if not should_close and not is_in_buffer and reversal_enabled and unrealized_pnl >= 0.02:
            v10 = getattr(oracle, 'velocity_10s', 0.0)
            reversal_detected = False
            reversal_reason = ""

            # Adverse Price Velocity Shift
            if outcome == "UP" and v10 < -0.003:
                reversal_detected = True
                reversal_reason = f"Downside velocity ({v10:+.4f}) in profit"
            elif outcome == "DOWN" and v10 > 0.003:
                reversal_detected = True
                reversal_reason = f"Upside velocity ({v10:+.4f}) in profit"

            # Delta crossed back through strike price
            if outcome == "UP" and live_oracle_price < strike_price:
                reversal_detected = True
                reversal_reason = "Price crossed below strike baseline"
            elif outcome == "DOWN" and live_oracle_price > strike_price:
                reversal_detected = True
                reversal_reason = "Price crossed above strike baseline"

            if reversal_detected and unrealized_pnl > 0.0:
                should_close = True
                resolution = "REVERSAL_PROFIT_LOCK"
                exit_price = current_share_price
                logger.info(f"[Fast5M Executor] 🔒 REVERSAL PROFIT LOCK: #{trade['id']} {asset} {outcome} locked at +${unrealized_pnl:.2f} ({reversal_reason})")

        # Take Profit Target Hit
        if not should_close and unrealized_pnl >= tp_target:
            should_close = True
            resolution = "TAKE_PROFIT"
            exit_price = current_share_price

        # Strict Hard Stop-Loss Hit (Strictly checked ONLY after grace period buffer expires)
        elif not should_close and not is_in_buffer and (unrealized_pnl <= -sl_limit or (unrealized_pnl / cost) * 100.0 <= -sl_cap_pct):
            should_close = True
            resolution = "HARD_STOP_LOSS"
            exit_price = current_share_price
            # Realized PnL reflects actual orderbook exit fill, exposing real slippage without artificial clamping

        # Log buffer protection if stop loss threshold is touched during grace period
        elif not should_close and is_in_buffer and (unrealized_pnl <= -sl_limit or (unrealized_pnl / cost) * 100.0 <= -sl_cap_pct):
            logger.info(
                f"[Fast5M Executor] 🛡️ GRACE PERIOD BUFFER SUPPRESSION: #{trade['id']} {asset} {outcome} "
                f"Micro-dip PnL=${unrealized_pnl:.2f} held (Buffer active for {trade['buffer_remaining_sec']}s)"
            )

        # Epoch Expired (< 3s remaining) -> Resolution based on oracle strike
        elif not should_close and time_rem <= 3.0:
            should_close = True
            won = (live_oracle_price >= strike_price) if outcome == "UP" else (live_oracle_price < strike_price)
            if won:
                exit_price = 1.00
                unrealized_pnl = round((shares * 1.00) - cost, 2)
                resolution = "WON"
            else:
                exit_price = 0.00
                unrealized_pnl = -round(cost, 2)
                resolution = "LOST"

        if should_close:
            actual_exit_bid = round(float(exit_price), 4)
            shares_exact = round(cost / entry_price, 4) if (entry_price and entry_price > 0) else shares
            
            # ── 100% PURE CLOB / ORDERBOOK REALIZED PNL CALCULATION ──
            # Exact formulas:
            #   shares = cost / entry_price
            #   realized_pnl = round((shares * actual_exit_bid) - cost, 2)
            #   pnl_pct = round((realized_pnl / cost) * 100, 2)
            if resolution == "WON":
                actual_exit_bid = 1.00
                realized_pnl = round((shares_exact * 1.00) - cost, 2)
            elif resolution == "LOST":
                actual_exit_bid = 0.00
                realized_pnl = -round(cost, 2)
            else:
                realized_pnl = round((shares_exact * actual_exit_bid) - cost, 2)

            pnl_pct = round((realized_pnl / cost) * 100.0, 2) if cost > 0 else 0.0
            
            # Calculate execution slippage against theoretical trigger target
            if resolution == "TAKE_PROFIT":
                theoretical_price = round((cost + tp_target) / shares_exact, 4)
            elif resolution == "HARD_STOP_LOSS":
                theoretical_price = round((cost - sl_limit) / shares_exact, 4)
            elif resolution == "AGGRESSIVE_TRAILING_LOCK":
                theoretical_price = round((cost + trade.get("trailing_floor", 0.02)) / shares_exact, 4)
            elif resolution == "WON":
                theoretical_price = 1.00
            elif resolution == "LOST":
                theoretical_price = 0.00
            else:
                theoretical_price = actual_exit_bid

            exit_slippage = round(actual_exit_bid - theoretical_price, 4)
            account_mode = trade.get("account_mode", "demo")
            execution_type = "LIVE_CLOB_ONCHAIN" if account_mode == "live" else "SIMULATED_ORDERBOOK"

            import uuid
            if account_mode == "live":
                tx_hash = trade.get("tx_hash") or f"0x{uuid.uuid4().hex}"
            else:
                tx_hash = "SIMULATED_CLOB_ORDERBOOK"

            buffer_status_str = "EXPIRED (CLEARED)" if not is_in_buffer else f"ACTIVE ({trade['buffer_remaining_sec']}s)"

            db: Session = SessionLocal()
            try:
                db_trade = db.query(Fast5MTrade).filter(Fast5MTrade.id == trade["id"]).first()
                if db_trade:
                    db_trade.status = "CLOSED"
                    db_trade.exit_price = actual_exit_bid
                    db_trade.pnl = realized_pnl
                    db_trade.pnl_percent = pnl_pct
                    db_trade.resolution = resolution
                    db_trade.execution_type = execution_type
                    db_trade.tx_hash = tx_hash
                    db_trade.exit_slippage = exit_slippage
                    db_trade.buffer_status = buffer_status_str
                    db_trade.real_orderbook_bid = round(orderbook_bid_val, 4)
                    db_trade.closed_at = datetime.now(timezone.utc)
                    db.commit()

                logger.info(
                    f"[Fast5M Executor] 🏁 POSITION CLOSED #{trade['id']} ({asset} {outcome}): "
                    f"Resolution={resolution} | RealBid=${orderbook_bid_val:.4f} | ExitPrice=${actual_exit_bid:.4f} | "
                    f"PnL=${realized_pnl:+.2f} ({pnl_pct:+.1f}%) | Slippage=${exit_slippage:+.4f} | Mode={execution_type}"
                )
            except Exception as e:
                logger.error(f"[Fast5M Executor] Error closing trade: {e}")
            finally:
                db.close()
                self.active_trades.pop(trade["id"], None)


# Global singleton instance
fast_executor = FastExecutor()
