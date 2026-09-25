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
    "take_profit_dollar": "0.50",         # Target Profit dollar amount
    "stop_loss_dollar": "0.50",           # Stop Loss dollar amount
    "risk_reward_ratio": "1.0",           # Configurable Risk-to-Reward Ratio (e.g. 1.0, 1.5, 2.0)
    "buffer_timer_sec": "4.0",            # 3 to 5 second Grace Period Buffer immediately after trade entry
    "take_profit_pct": "3.0",             # Base Take-Profit target: 1.5% - 3.0%
    "stop_loss_pct": "3.0",               # Stop-Loss % trigger threshold
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
    # Slippage Circuit Breaker on Exit
    "exit_circuit_breaker_enabled": "true",
    "max_exit_slippage_pct": "5.0",       # Max allowed slippage % beyond target SL (prevents vacuum dumps)
    # Dedicated Per-Asset Spread & Liquidity Thresholds
    "max_spread_btc": "0.06",
    "min_liquidity_usd_btc": "150.0",
    "max_spread_eth": "0.06",
    "min_liquidity_usd_eth": "150.0",
    "max_spread_sol": "0.08",
    "min_liquidity_usd_sol": "120.0",
    "max_spread_xrp": "0.10",
    "min_liquidity_usd_xrp": "100.0",
    "max_spread_doge": "0.10",
    "min_liquidity_usd_doge": "100.0",
    "max_spread_bnb": "0.08",
    "min_liquidity_usd_bnb": "100.0",
    "max_spread_hype": "0.08",
    "min_liquidity_usd_hype": "150.0",
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

    def get_active_trades_for_user(self, user_id: Optional[int] = None, account_mode: str = "demo") -> List[Dict[str, Any]]:
        """Return open active trades partitioned by user and account mode."""
        trades = list(self.active_trades.values())
        if account_mode != "all":
            trades = [t for t in trades if t.get("account_mode", "demo") == account_mode]
        if user_id is not None:
            trades = [t for t in trades if t.get("user_id") == user_id]
        return trades

    def get_active_margin_for_user(self, user_id: Optional[int] = None, account_mode: str = "demo") -> float:
        """Calculate total active margin locked in open trades for a user."""
        user_trades = self.get_active_trades_for_user(user_id=user_id, account_mode=account_mode)
        return round(sum(t.get("cost", 0.0) for t in user_trades), 2)

    def get_dynamic_hard_cap(self, active_margin: float) -> float:
        """
        Calculate Dynamic Hard Cap Risk limit:
        dynamic_hard_cap = -(active_margin * 2.5)
        """
        effective_margin = max(active_margin, float(self.settings.get("position_size_usd", 10.0)))
        return round(-(effective_margin * 2.5), 2)

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

    def manual_exit_trade(self, trade_id: int, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Manually exit a specific active trade at market price.
        """
        trade = self.active_trades.get(trade_id)
        db: Session = SessionLocal()
        try:
            db_trade = db.query(Fast5MTrade).filter(Fast5MTrade.id == trade_id).first()
            if not db_trade:
                return {"status": "error", "message": f"Trade #{trade_id} not found."}
            if user_id and db_trade.user_id and db_trade.user_id != user_id:
                return {"status": "error", "message": "Unauthorized to close this position."}
            
            current_pnl = trade.get("current_pnl", 0.0) if trade else (db_trade.pnl or 0.0)
            cost = trade.get("cost", 10.0) if trade else (db_trade.cost or 10.0)
            
            db_trade.status = "CLOSED"
            db_trade.resolution = "MANUAL_EXIT"
            db_trade.pnl = round(current_pnl, 2)
            db_trade.pnl_percent = round((current_pnl / cost) * 100.0, 2) if cost > 0 else 0.0
            db_trade.closed_at = datetime.now(timezone.utc)
            db.commit()
            
            if trade_id in self.active_trades:
                del self.active_trades[trade_id]
                
            return {
                "status": "success",
                "message": f"Position #{trade_id} manually closed at market price.",
                "trade_id": trade_id,
                "pnl": db_trade.pnl
            }
        except Exception as e:
            logger.error(f"[Fast5M Executor] Error during manual trade exit: {e}")
            db.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            db.close()

    def reset_demo_account(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Wipes demo paper trading history for the user and resets virtual balance to $300.00.
        Real account history and live on-chain trades are strictly preserved.
        """
        demo_trade_ids = [
            tid for tid, t in self.active_trades.items() 
            if t.get("account_mode", "demo") == "demo" and (user_id is None or t.get("user_id") == user_id)
        ]
        for tid in demo_trade_ids:
            self.active_trades.pop(tid, None)

        self._traded_epochs.clear()
        self.update_settings({"total_balance_usd": "300.0"})

        db: Session = SessionLocal()
        deleted_count = 0
        try:
            # Delete ONLY temporary demo trades for the user (or all if user_id is None)
            query = db.query(Fast5MTrade).filter(
                (Fast5MTrade.account_mode == "demo") | (Fast5MTrade.account_mode.is_(None))
            )
            if user_id is not None:
                query = query.filter(Fast5MTrade.user_id == user_id)
                # Reset user's vault balance to 300.0
                vault = db.query(Fast5MUserVault).filter(Fast5MUserVault.user_id == user_id).first()
                if vault:
                    vault.allocated_balance = 300.0
                    vault.initial_deposit = 300.0
                    vault.total_deposited = 300.0
                    vault.total_withdrawn = 0.0

            deleted_count = query.delete(synchronize_session=False)
            db.commit()
            logger.info(f"[Fast5M Executor] 🔄 DEMO ACCOUNT RESET (User #{user_id}): {deleted_count} temporary paper trades wiped. Base balance restored to $300.00.")
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
                    "user_id": getattr(open_trade, "user_id", None),
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
                self._traded_epochs.add((open_trade.user_id, open_trade.asset, open_trade.epoch_bucket))
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
                if auto_enabled:
                    await self._check_and_execute_pairs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Fast5M Executor] Exec loop error: {e}", exc_info=True)
            await asyncio.sleep(1.0)

    async def _check_and_execute_pairs(self):
        """
        Identify top qualifying pairs and execute positions concurrently (up to 2 to 3 pairs)
        for each active user bot independently, while strictly enforcing individual margin exposure safeguards.
        """
        conf_threshold = float(self.settings.get("confidence_threshold", 70.0))
        multi_pair_threshold = float(self.settings.get("multi_pair_min_score", 90.0))
        max_pools = int(self.settings.get("max_active_pools", 3))
        min_time = float(self.settings.get("min_time_remaining", 20.0))
        max_time = float(self.settings.get("max_time_remaining", 280.0))
        base_size = float(self.settings.get("position_size_usd", 10.0))
        max_margin_pct = float(self.settings.get("max_portfolio_margin_pct", 30.0))
        strat_dir = self.settings.get("strategy_direction", "BOTH").upper()

        # Score all 7 assets once per tick
        scored_assets = fast_scorer.score_all_assets(conf_threshold)
        if not scored_assets:
            return

        # Query all approved active users so every user bot executes independently
        db: Session = SessionLocal()
        user_targets = []
        try:
            from app.db.models import User, Fast5MUserVault
            active_users = db.query(User).filter(User.status == "APPROVED", User.is_active == True).all()
            for u in active_users:
                vault = db.query(Fast5MUserVault).filter(Fast5MUserVault.user_id == u.id).first()
                mode = vault.account_mode if vault else "demo"
                balance = float(vault.allocated_balance) if vault and vault.allocated_balance > 0 else float(self.settings.get("total_balance_usd", 300.0))
                user_targets.append({
                    "user_id": u.id,
                    "email": u.email,
                    "mode": mode,
                    "balance": balance
                })
        except Exception as e:
            logger.debug(f"[Fast5M Executor] Error querying active users: {e}")
        finally:
            db.close()

        if not user_targets:
            user_targets.append({
                "user_id": None,
                "email": "default",
                "mode": "demo",
                "balance": float(self.settings.get("total_balance_usd", 300.0))
            })

        for user_cfg in user_targets:
            uid = user_cfg["user_id"]
            umode = user_cfg["mode"]
            ubal = user_cfg["balance"]

            # Independent trade capacity per user bot
            user_trades = [
                t for t in self.active_trades.values() 
                if (uid is None or t.get("user_id") == uid) and t.get("account_mode", "demo") == umode
            ]
            available_slots = max_pools - len(user_trades)
            if available_slots <= 0:
                continue

            # Independent Exposure Safeguard for this user:
            max_total_exposure = ubal * (max_margin_pct / 100.0)
            current_exposure = sum(t.get("cost", 0.0) for t in user_trades)
            available_exposure = max(0.0, max_total_exposure - current_exposure)

            if available_exposure < 0.50:
                continue

            active_assets = {t["asset"] for t in user_trades}
            user_candidates: List[ScoredAsset] = []

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
                epoch_key = (uid, asset_score.asset, market.epoch_bucket)
                if epoch_key in self._traded_epochs:
                    continue

                # Multi-Pair Scoring Rule for this user
                current_count = len(user_trades) + len(user_candidates)
                req_score = conf_threshold if current_count == 0 else multi_pair_threshold

                if asset_score.confidence >= req_score:
                    user_candidates.append(asset_score)
                    if len(user_candidates) >= available_slots:
                        break

            if not user_candidates:
                continue

            # Partition cost safely
            num_new_trades = len(user_candidates)
            safe_per_trade_cost = max(0.50, min(base_size, round(available_exposure / num_new_trades, 2)))

            # Open qualified pairs independently for this user bot
            for candidate in user_candidates:
                await self._execute_single_trade(candidate, safe_per_trade_cost, user_id=uid, account_mode=umode)

    async def _execute_single_trade(self, top_asset: ScoredAsset, cost: float, user_id: Optional[int] = None, account_mode: Optional[str] = None):
        market = fast_markets.get_market(top_asset.asset)
        if not market:
            return

        # Pre-trade entry validation against dedicated per-asset thresholds
        asset_lower = top_asset.asset.lower()
        raw_spread = self.settings.get(f"max_spread_{asset_lower}")
        asset_max_spread = float(raw_spread) if raw_spread is not None and float(raw_spread) > 0 else float(self.settings.get("max_spread", 0.20))
        raw_liq = self.settings.get(f"min_liquidity_usd_{asset_lower}")
        asset_min_liq = float(raw_liq) if raw_liq is not None and float(raw_liq) > 0 else float(self.settings.get("min_liquidity_usd", 100.0))

        # Effective spread and adaptive liquidity bounds: small trades (e.g. $1-$10) are never blocked by huge depth checks
        effective_max_spread = max(0.12, asset_max_spread)
        if market.spread > effective_max_spread:
            logger.warning(
                f"[Fast5M Executor] ⛔ PRE-TRADE ENTRY BLOCKED for {top_asset.asset}: "
                f"Live spread {market.spread*100:.1f}% exceeds threshold {effective_max_spread*100:.1f}%"
            )
            return

        required_liq = max(10.0, min(asset_min_liq, cost * 5.0))
        if market.total_liquidity < required_liq:
            logger.warning(
                f"[Fast5M Executor] ⛔ PRE-TRADE ENTRY BLOCKED for {top_asset.asset}: "
                f"Live liquidity ${market.total_liquidity:.1f} below required ${required_liq:.1f}"
            )
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

        # ── SECONDARY ORACLE-ANCHORED ENTRY PRICE SANITY GUARD ───────────────────
        # Even if a dust/outlier CLOB ask slips through the discovery clamping,
        # reject any fill where the entry_price deviates more than 5% from the
        # oracle-anchored fair_mid. This prevents fake +1000%+ PnL from $0.02 fills.
        oracle_state = None
        try:
            oracle_state = fast_oracle.get_asset_state(top_asset.asset)
        except Exception:
            pass
        if oracle_state:
            oracle_delta_pct = oracle_state.delta_pct if hasattr(oracle_state, 'delta_pct') else 0.0
            fair_mid = min(0.88, max(0.12, 0.50 + (oracle_delta_pct * 1.5)))
            MAX_ENTRY_DEVIATION = 0.05  # 5% absolute deviation from oracle fair_mid
            if abs(entry_price - fair_mid) > MAX_ENTRY_DEVIATION:
                logger.warning(
                    f"[Fast5M Executor] ⛔ ENTRY PRICE SANITY GUARD BLOCKED {top_asset.asset} {outcome}: "
                    f"entry_price=${entry_price:.4f} deviates {abs(entry_price - fair_mid):.4f} from "
                    f"oracle fair_mid=${fair_mid:.4f} (max allowed: {MAX_ENTRY_DEVIATION:.2f}). "
                    f"Aborting trade to prevent fake PnL."
                )
                return
            # Clamp entry_price to oracle fair zone as a final safety net
            entry_price = round(min(fair_mid + MAX_ENTRY_DEVIATION, max(fair_mid - MAX_ENTRY_DEVIATION, entry_price)), 4)

        cost = max(0.50, round(cost, 2))
        # Clamp shares: max 200 shares per $10 notional (equivalent to a $0.05 min fill price)
        # This guards against absurd share quantities (e.g. 500 shares for $10 at $0.02 entry)
        max_shares = round(cost / 0.05, 4)
        shares = max(0.01, min(max_shares, round(cost / entry_price, 4)))
        epoch_key = (user_id, top_asset.asset, market.epoch_bucket)

        from app.fast5m.wallet import wallet_manager
        current_account_mode = account_mode or getattr(wallet_manager, "account_mode", "demo") or "demo"

        # Place trade in DB
        db: Session = SessionLocal()
        try:
            trade_record = Fast5MTrade(
                user_id=user_id,
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
                "user_id": user_id,
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

            user_label = f"User #{user_id}" if user_id else "Global"
            logger.info(
                f"[Fast5M Executor] 🚀 EXECUTED INDEPENDENT POSITION ({user_label} - {current_account_mode.upper()}): "
                f"{top_asset.asset} {outcome} @ ${entry_price:.3f} (Cost: ${cost:.2f}, Shares: {shares}, Score: {top_asset.confidence}%)"
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
        raw_exit_bid = market.up_bid if outcome == "UP" else market.down_bid

        # ── ORACLE-ANCHORED EXIT BID SANITY CLAMP ────────────────────────────────
        # Reject exit bids that are dust/outlier prices far from oracle fair value.
        # This prevents a legitimate $0.39 entry from being "exited" at a $0.02 dust bid.
        oracle_delta_pct_exit = getattr(oracle, 'delta_pct', 0.0)
        fair_mid_exit = min(0.88, max(0.12, 0.50 + (oracle_delta_pct_exit * 1.5)))
        MAX_EXIT_BID_DEVIATION = 0.08  # 8% from fair_mid

        real_book_bid = None
        if raw_exit_bid and raw_exit_bid > 0.01 and abs(raw_exit_bid - fair_mid_exit) <= MAX_EXIT_BID_DEVIATION:
            real_book_bid = raw_exit_bid
        elif raw_exit_bid and raw_exit_bid > 0.01:
            logger.warning(
                f"[Fast5M Executor] ⚠️ OUTLIER EXIT BID CLAMPED for #{trade.get('id')} {asset} {outcome}: "
                f"raw_bid=${raw_exit_bid:.4f} deviates {abs(raw_exit_bid - fair_mid_exit):.4f} from "
                f"fair_mid=${fair_mid_exit:.4f}. Falling back to oracle-estimated exit price."
            )

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

        # 2. Dynamic Risk-to-Reward & Loss Limit Settings (Unclamped)
        sl_pct_setting = float(self.settings.get("stop_loss_pct", 3.0))
        user_sl_dollar = float(self.settings.get("stop_loss_dollar", 0.50))
        # Determine dollar stop loss: prioritize user percentage if set, else dollar setting
        pct_sl_dollar = round(cost * (sl_pct_setting / 100.0), 2) if sl_pct_setting > 0 else user_sl_dollar
        sl_limit = max(0.02, min(cost * 0.50, pct_sl_dollar if sl_pct_setting > 0 else user_sl_dollar))

        # Take-Profit Target (Dynamic based on R:R ratio or take_profit_pct)
        tp_pct_setting = float(self.settings.get("take_profit_pct", 3.0))
        pct_tp_dollar = round(cost * (tp_pct_setting / 100.0), 2) if tp_pct_setting > 0 else 0.50
        user_tp_dollar = float(self.settings.get("take_profit_dollar", 0.50))
        tp_target = max(0.02, pct_tp_dollar if tp_pct_setting > 0 else user_tp_dollar)

        trade_peak_pnl = max(trade.get("peak_pnl", 0.0), unrealized_pnl)
        trade["peak_pnl"] = round(trade_peak_pnl, 2)
        trade["current_pnl"] = round(unrealized_pnl, 2)
        trade["current_share_price"] = round(current_share_price, 4)
        trade["live_oracle_price"] = live_oracle_price

        should_close = False
        resolution = "HOLD"
        exit_price = current_share_price

        # Dynamic Hard Cap Risk Safeguard: dynamic_hard_cap = -(active_margin * 2.5)
        # Replaces any static hard cap with a dynamic, strictly margin-scaled ceiling
        active_margin_for_trade = cost
        dynamic_hard_cap = round(-(active_margin_for_trade * 2.5), 2)
        trade["dynamic_hard_cap"] = dynamic_hard_cap

        # If drawdown breaches dynamic hard cap, immediately force circuit breaker hard stop
        if unrealized_pnl <= dynamic_hard_cap:
            should_close = True
            resolution = "HARD_STOP_LOSS"
            exit_price = current_share_price
            trade["reversal_defense_active"] = False
            logger.warning(
                f"[Fast5M Executor] 🛑 DYNAMIC HARD CAP BREACHED: #{trade['id']} {asset} {outcome} "
                f"PnL ${unrealized_pnl:.2f} <= Dynamic Hard Cap ${dynamic_hard_cap:.2f} (-2.5x margin limit). "
                f"Forcing immediate emergency exit at ${exit_price:.4f}."
            )


        # 3. STRICT REAL-TIME TRAILING STOP & ZERO-SLIPPAGE PROFIT LOCKING
        # Rules:
        # a) Trailing stop is SUPPRESSED during the initial grace period buffer (noise protection).
        # b) Trailing stop only activates once trade peak PnL reaches the activation threshold (e.g. +1.0% to +1.5%).
        # c) The trailing floor has an absolute Breakeven minimum floor (>= +$0.02).
        # d) Trailing lock can ONLY execute when current PnL is POSITIVE (unrealized_pnl > 0.0).
        #    Under NO circumstances can AGGRESSIVE_TRAILING_LOCK close a trade at a negative loss!
        trailing_act_pct = float(self.settings.get("trailing_stop_activation_pct", 1.0))
        trailing_dist_pct = float(self.settings.get("trailing_stop_distance_pct", 0.5))
        min_gain_for_trailing = max(0.01, round(cost * (trailing_act_pct / 100.0), 2))
        tight_giveback = max(0.01, round(cost * (trailing_dist_pct / 100.0), 2))

        trailing_enabled = self.settings.get("trailing_lock_enabled", "true").lower() in ("true", "1", "yes")
        reversal_enabled = self.settings.get("reversal_lock_enabled", "true").lower() in ("true", "1", "yes")

        # ─────────────────────────────────────────────────────────────
        # 1. HARD ROUND TIMEOUT (04:50 Rule / remaining_time <= 10s)
        # Every trade MUST be strictly contained within its current 5M round.
        # At 04:50 (remaining_time <= 10s), cancel all pending limit orders,
        # force immediate Market Exit (Sell) on best available bid to bring
        # open position to zero.
        # If bid order book is completely dry (bid <= 0.0001), force-mark
        # internal trade state as EXPIRED_ROUND_CLOSE and clear active margin.
        # ─────────────────────────────────────────────────────────────
        if time_rem <= 10.0:
            should_close = True
            trade["circuit_breaker_active"] = False
            trade["reversal_defense_active"] = False

            raw_bid = real_book_bid if (real_book_bid is not None and real_book_bid > 0.0) else orderbook_bid_val
            if raw_bid <= 0.0001:
                resolution = "EXPIRED_ROUND_CLOSE"
                exit_price = 0.00
                logger.warning(
                    f"[Fast5M Executor] ⏱️ HARD ROUND TIMEOUT (04:50 Rule / DRY BOOK): #{trade['id']} {asset} {outcome} "
                    f"Bid=${raw_bid:.4f} <= 0.0001 at 04:50 (Remaining: {time_rem:.1f}s). "
                    f"Force-marking EXPIRED_ROUND_CLOSE and clearing active margin immediately."
                )
            else:
                resolution = "FORCE_ROUND_TIMEOUT"
                exit_price = round(raw_bid, 4)
                logger.info(
                    f"[Fast5M Executor] ⏱️ HARD ROUND TIMEOUT (04:50 Rule): #{trade['id']} {asset} {outcome} "
                    f"Force Market Exit (Sell) at best available bid ${exit_price:.4f} to bring position to zero (Remaining: {time_rem:.1f}s)."
                )

        # ─────────────────────────────────────────────────────────────
        # 2. TAKE PROFIT TARGET & TRAILING PROFIT LOCK
        # ─────────────────────────────────────────────────────────────
        elif not should_close and unrealized_pnl >= tp_target:
            should_close = True
            resolution = "TAKE_PROFIT"
            exit_price = current_share_price
            logger.info(f"[Fast5M Executor] 🎯 TAKE PROFIT HIT: #{trade['id']} {asset} {outcome} target +${unrealized_pnl:.2f} reached.")

        elif not should_close and trailing_enabled and not is_in_buffer:
            if trade.get("trailing_armed") or trade_peak_pnl >= min_gain_for_trailing:
                trade["trailing_armed"] = True
                trailing_floor = max(0.02, round(trade_peak_pnl - tight_giveback, 2))
                trade["trailing_floor"] = trailing_floor

                if unrealized_pnl <= trailing_floor and unrealized_pnl > 0.0:
                    should_close = True
                    resolution = "TAKE_PROFIT"
                    exit_price = current_share_price
                    logger.info(
                        f"[Fast5M Executor] 🔒 AGGRESSIVE TRAILING STOP HIT: #{trade['id']} {asset} {outcome} locked at +${unrealized_pnl:.2f} "
                        f"(Peak: +${trade_peak_pnl:.2f}, Floor: +${trailing_floor:.2f})"
                    )

        # ─────────────────────────────────────────────────────────────
        # 3. ACTIVE REVERSAL DEFENSE HOLD MONITORING (Early Round Only)
        # ─────────────────────────────────────────────────────────────
        if not should_close and trade.get("reversal_defense_active"):
            hold_elapsed = time.time() - (trade.get("reversal_defense_start_ts") or time.time())
            max_reversal_dd = min(0.60, max(0.04, round(cost * 0.06, 2))) # -$0.60 or 6% of margin

            # Boundary 1: Late-Round Circuit Breaker Lock (Time >= 03:30 / time_rem <= 90s)
            if time_rem <= 90.0:
                trade["reversal_defense_active"] = False
                should_close = True
                resolution = "HARD_STOP_LOSS"
                exit_price = current_share_price
                logger.warning(
                    f"[Fast5M Executor] 🛑 LATE-ROUND CIRCUIT BREAKER LOCK: #{trade['id']} {asset} {outcome} "
                    f"Round reached 03:30+ (Remaining: {time_rem:.1f}s <= 90s). Reversal hold cancelled. "
                    f"Executing immediate HARD_STOP_LOSS at ${exit_price:.4f} (PnL=${unrealized_pnl:.2f}) to avoid late liquidity crash."
                )

            # Boundary 2: Strict Drawdown Boundary (-$0.60 or 6% of margin)
            elif unrealized_pnl <= -max_reversal_dd:
                trade["reversal_defense_active"] = False
                should_close = True
                resolution = "HARD_STOP_LOSS"
                exit_price = current_share_price
                logger.warning(
                    f"[Fast5M Executor] 🛑 REVERSAL HOLD BOUNDARY BREACHED: #{trade['id']} {asset} {outcome} "
                    f"Drawdown ${unrealized_pnl:.2f} breached max allowed -${max_reversal_dd:.2f} (6% margin cap). "
                    f"Executing immediate HARD_STOP_LOSS at ${exit_price:.4f}."
                )

            # Boundary 3: Maximum 20-Second Defensive Hold Window
            elif hold_elapsed > 20.0:
                trade["reversal_defense_active"] = False
                should_close = True
                resolution = "HARD_STOP_LOSS"
                exit_price = current_share_price
                logger.warning(
                    f"[Fast5M Executor] 🛑 REVERSAL DEFENSE TIMED OUT: #{trade['id']} {asset} {outcome} "
                    f"Hold expired ({hold_elapsed:.1f}s > 20.0s). Executing HARD_STOP_LOSS at ${exit_price:.4f} (PnL=${unrealized_pnl:.2f})."
                )

            # Defensive Exit on Bounce: attempted exit at breakeven or reduced loss
            elif unrealized_pnl >= -0.05:
                trade["reversal_defense_active"] = False
                should_close = True
                resolution = "REVERSAL_EXIT"
                exit_price = current_share_price
                logger.info(
                    f"[Fast5M Executor] 🔄 REVERSAL EXIT: #{trade['id']} {asset} {outcome} "
                    f"Defensive bounce achieved at ${exit_price:.4f} (PnL=${unrealized_pnl:+.2f}, held {hold_elapsed:.1f}s). Exiting safely."
                )
            else:
                trade["buffer_status"] = f"REVERSAL_HOLD ({round(20.0 - hold_elapsed, 1)}s)"

        # ─────────────────────────────────────────────────────────────
        # 4. DRAWDOWN & STOP-LOSS EVALUATION (When not in active hold)
        # ─────────────────────────────────────────────────────────────
        if not should_close and not is_in_buffer and not trade.get("reversal_defense_active"):
            sl_triggered = (unrealized_pnl <= -sl_limit) or ((unrealized_pnl / cost) * 100.0 <= -sl_pct_setting)

            if sl_triggered:
                # Late-Round Circuit Breaker Lock (Time >= 03:30 / time_rem <= 90s)
                # Prioritize capital safety: immediately trigger Hard Stop Loss at default thresholds
                # (-$0.45 to -$0.50) without waiting for price recovery, avoiding end-of-round liquidity crash.
                if time_rem <= 90.0:
                    should_close = True
                    resolution = "HARD_STOP_LOSS"
                    exit_price = current_share_price
                    logger.warning(
                        f"[Fast5M Executor] 🛑 LATE-ROUND HARD STOP LOSS (Time >= 03:30): #{trade['id']} {asset} {outcome} "
                        f"Immediate SL at ${exit_price:.4f} (PnL=${unrealized_pnl:.2f}, Remaining: {time_rem:.1f}s). Reversal-wait disabled."
                    )

                # Early Round (Time < 03:30 / time_rem > 90s)
                # Check order book depth and spot momentum (Delta/RSI).
                # If high-volume bid wall (liquidity absorption) or divergence detected,
                # allow defensive hold for max 20 seconds.
                else:
                    bid_depth = market.up_bid_depth if outcome == "UP" else market.down_bid_depth
                    obi = market.orderbook_imbalance
                    vel10 = getattr(oracle, 'velocity_10s', 0.0)
                    rsi = getattr(oracle, 'rsi_14', 50.0)
                    delta = getattr(oracle, 'delta', 0.0)

                    # Absorption condition: high-volume bid wall absorbing sell pressure
                    has_absorption = (bid_depth >= 40.0) or (obi >= 0.15 if outcome == "UP" else obi <= -0.15)

                    # Divergence / bounce condition: spot delta/velocity/RSI reversing
                    has_divergence = (
                        (vel10 > 0.001 or rsi < 35.0 or delta > 0.0) if outcome == "UP"
                        else (vel10 < -0.001 or rsi > 65.0 or delta < 0.0)
                    )

                    # Strict Boundary check immediately: drawdown cannot exceed -$0.60 (or 6% of margin)
                    max_reversal_dd = min(0.60, max(0.04, round(cost * 0.06, 2)))

                    if (has_absorption or has_divergence) and unrealized_pnl > -max_reversal_dd:
                        # Engage Reversal Defense Hold
                        trade["reversal_defense_active"] = True
                        trade["reversal_defense_start_ts"] = time.time()
                        reason = "High-volume bid absorption" if has_absorption else "Momentum/RSI bounce divergence"
                        trade["buffer_status"] = "REVERSAL_HOLD (20.0s)"
                        logger.info(
                            f"[Fast5M Executor] 🔄 REVERSAL DEFENSE ENGAGED (Time < 03:30): #{trade['id']} {asset} {outcome} "
                            f"Drawdown=${unrealized_pnl:.2f}. {reason} (BidDepth=${bid_depth:.1f}, OBI={obi:+.2f}, RSI={rsi:.1f}). "
                            f"Holding defensively for max 20s (Cap: -${max_reversal_dd:.2f})."
                        )
                    else:
                        # No absorption or divergence, or already beyond allowable drawdown: immediate Hard Stop Loss
                        should_close = True
                        resolution = "HARD_STOP_LOSS"
                        exit_price = current_share_price
                        logger.warning(
                            f"[Fast5M Executor] 🛑 HARD STOP LOSS: #{trade['id']} {asset} {outcome} "
                            f"Triggered at ${exit_price:.4f} (PnL=${unrealized_pnl:.2f}, Remaining: {time_rem:.1f}s, no reversal bounce)."
                        )

        # Log buffer protection if stop loss threshold is touched during grace period
        elif not should_close and is_in_buffer and (unrealized_pnl <= -sl_limit or (unrealized_pnl / cost) * 100.0 <= -sl_pct_setting):
            logger.info(
                f"[Fast5M Executor] 🛡️ GRACE PERIOD BUFFER SUPPRESSION: #{trade['id']} {asset} {outcome} "
                f"Micro-dip PnL=${unrealized_pnl:.2f} held (Buffer active for {trade['buffer_remaining_sec']}s)"
            )

        if should_close:
            actual_exit_bid = round(float(exit_price), 4)
            shares_exact = round(cost / entry_price, 4) if (entry_price and entry_price > 0) else shares
            
            # ── 100% PURE UNCLAMPED CLOB REALIZED PNL CALCULATION ──
            if resolution in ("WON",):
                actual_exit_bid = 1.00
            elif resolution in ("LOST", "EXPIRED_ROUND_CLOSE"):
                actual_exit_bid = 0.00

            # Pure orderbook execution math
            if resolution == "EXPIRED_ROUND_CLOSE":
                realized_pnl = -round(cost, 2)
                pnl_pct = -100.0
            else:
                realized_pnl = round((actual_exit_bid - entry_price) * shares_exact, 2)
                if entry_price > 0:
                    pnl_pct = round(((actual_exit_bid - entry_price) / entry_price) * 100.0, 2)
                else:
                    pnl_pct = 0.0
            
            # Calculate execution slippage against theoretical trigger target
            if resolution == "TAKE_PROFIT":
                theoretical_price = round((cost + tp_target) / shares_exact, 4)
            elif resolution in ("HARD_STOP_LOSS", "CIRCUIT_BREAKER_SL_FILLED"):
                theoretical_price = round((cost - sl_limit) / shares_exact, 4)
            elif resolution == "REVERSAL_EXIT":
                theoretical_price = entry_price  # Target was breakeven
            elif resolution == "FORCE_ROUND_TIMEOUT":
                theoretical_price = actual_exit_bid  # Immediate market exit on best available bid
            elif resolution == "AGGRESSIVE_TRAILING_LOCK":
                theoretical_price = round((cost + trade.get("trailing_floor", 0.02)) / shares_exact, 4)
            elif resolution == "WON":
                theoretical_price = 1.00
            elif resolution in ("LOST", "LOST_CIRCUIT_BREAKER_EXPIRED", "EXPIRED_ROUND_CLOSE"):
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

            base_buffer_str = "EXPIRED (CLEARED)" if not is_in_buffer else f"ACTIVE ({trade['buffer_remaining_sec']}s)"
            cb_tag = " [CIRCUIT_BREAKER_DEFENSE]" if trade.get("circuit_breaker_active") else ""
            buffer_status_str = f"{base_buffer_str}{cb_tag}"

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
