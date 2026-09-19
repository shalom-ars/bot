"""
BTC 5M Engine — Asynchronous Orchestrator.

Runs concurrently with the main Polymarket scanner.
- Polls Polymarket for BTC 5M markets every 30 seconds.
- Processes each market independently.
- Integrates with RiskManager and paper engine.
- Persists signals and trades to DB.
- Safe restart recovery.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from app.db.session import SessionLocal
from app.db.models import BTC5MMarket, BTC5MSignal as BTC5MSignalDB, BTC5MTrade
from app.btc5m.selector import discover_btc5m_markets, async_discover_btc5m_markets, BTC5MMarketInfo
from app.btc5m.features import BTC5MFeatureEngine
from app.btc5m.strategy import BTC5MStrategy, BTC5MSignal
from app.btc5m.latency import latency_tracker
from app.trading.risk import RiskManager
from app.config import settings

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 3   # High-frequency polling (3s) to ensure immediate execution at 5-minute window start
MAX_CONCURRENT_MARKETS = 20  # Safety cap


class BTC5MEngine:
    """
    Manages discovery, feature computation, signal generation,
    and paper trade execution for BTC 5M markets.
    """

    def __init__(
        self,
        instance_id: str = "instance_1",
        name: str = "Primary Bot",
        mode: str = "dynamic",
        tp_dollar: Optional[float] = None,
        sl_dollar: Optional[float] = None,
        only_short: bool = False,
        risk_manager: Optional[RiskManager] = None,
        slot_mode: Optional[str] = None
    ):
        self.instance_id = instance_id
        self.name = name
        self.mode = mode
        self.tp_dollar = tp_dollar
        self.sl_dollar = sl_dollar
        self.only_short = only_short
        self.slot_mode = slot_mode or "single_5m"
        from app.db.models import BTC5MTrade
        self.risk_manager = risk_manager or RiskManager(trade_model=BTC5MTrade, instance_id=self.instance_id)
        self.feature_engine = BTC5MFeatureEngine()
        self.strategy = BTC5MStrategy(
            risk_manager=self.risk_manager,
            instance_id=self.instance_id,
            mode=self.mode,
            tp_dollar=self.tp_dollar,
            sl_dollar=self.sl_dollar,
            only_short=self.only_short,
            slot_mode=self.slot_mode
        )

        self.running = False
        self.trading_active = True  # Default active for paper trading (toggleable via UI)
        self._market_states: Dict[str, str] = {}  # market_id -> state
        self._btc_history: list = []  # rolling [(timestamp_sec, btc_price)] for spot momentum
        self.rehydrate_state()

    def rehydrate_state(self):
        """
        Rehydrate active bot status, targeting settings, and open trade thesis from SQLite database.
        Ensures complete persistence across server restarts and updates.
        """
        try:
            db = SessionLocal()
            try:
                from app.db.models import BTC5MSetting, BTC5MAudit, BTC5MTrade
                from app.btc5m.settings_manager import get_btc5m_settings, ensure_btc5m_settings
                
                # 1. Ensure and load persistent targeting settings
                ensure_btc5m_settings(db, instance_id=self.instance_id)
                settings_map = get_btc5m_settings(db, instance_id=self.instance_id)
                if self.strategy:
                    self.strategy.settings = settings_map
                    self.strategy._sync_instance_params()

                # 2. Rehydrate RiskManager with BTC5M authoritative trades and persistent risk settings
                if self.risk_manager:
                    self.risk_manager.trade_model = BTC5MTrade
                    self.risk_manager.is_btc5m = True
                    self.risk_manager.max_consecutive_losses = int(settings_map.get("max_consecutive_losses", 5))
                    self.risk_manager.risk_per_trade = float(settings_map.get("risk_per_trade", 0.02))
                    self.risk_manager.rehydrate()
                
                # 2. Rehydrate trading_active state
                active_key = "trading_active" if self.instance_id in ("instance_1", "default") else f"{self.instance_id}:trading_active"
                active_setting = db.query(BTC5MSetting).filter(BTC5MSetting.key == active_key).first()
                if active_setting:
                    self.trading_active = (active_setting.value.lower() in ("true", "1", "yes", "on"))
                else:
                    last_audit = db.query(BTC5MAudit).filter(BTC5MAudit.action.in_(["START", "STOP"])).order_by(BTC5MAudit.timestamp.desc()).first()
                    if last_audit:
                        self.trading_active = (last_audit.action == "START")
                    else:
                        self.trading_active = True
                
                # 3. Rehydrate active open trades into strategy memory
                open_trades = db.query(BTC5MTrade).filter(
                    BTC5MTrade.status == "OPEN",
                    BTC5MTrade.instance_id == self.instance_id
                ).all()
                for trade in open_trades:
                    sig = BTC5MSignal(
                        market_id=trade.market_id,
                        condition_id=getattr(trade, "condition_id", ""),
                        question=trade.question,
                        yes_token_id=getattr(trade, "yes_token_id", ""),
                        no_token_id=getattr(trade, "no_token_id", ""),
                        timestamp=trade.entry_time or datetime.now(timezone.utc),
                        state="HOLD",
                        side=trade.execution_side or trade.side,
                        entry_price=trade.entry_price,
                        bid=trade.entry_price,
                        ask=trade.entry_price,
                        spread=trade.spread_at_entry or 0.01,
                        bid_depth=1000.0,
                        ask_depth=1000.0,
                        momentum=trade.momentum_at_entry or 0.0,
                        imbalance=trade.imbalance_at_entry or 0.0,
                        ob_pressure=0.0,
                        volatility=0.01,
                        momentum_persistence=0.5,
                        market_probability=trade.entry_market_probability or trade.entry_price,
                        fair_probability=trade.entry_fair_probability or trade.entry_price,
                        raw_edge=trade.entry_net_edge or 0.0,
                        spread_cost=0.005,
                        slippage_cost=0.0,
                        fees=0.0,
                        net_edge=trade.entry_net_edge or 0.0,
                        risk_pct=0.02,
                        position_size=trade.position_size,
                        time_remaining_sec=trade.time_remaining_at_entry or 150.0,
                        planned_risk=trade.planned_risk or 0.0,
                        planned_reward=trade.planned_reward or 0.0,
                        planned_rr=trade.entry_planned_rr or trade.planned_rr or 1.5,
                        stop_loss_price=trade.entry_stop_price or trade.stop_loss_price or 0.0,
                        take_profit_price=trade.entry_target_price or trade.take_profit_price or 1.0,
                        model_version=trade.model_version or "1.0",
                        strategy=trade.strategy or "BTC_5M",
                        reason=f"REHYDRATED_LOCKED_THESIS: {trade.locked_predicted_side or trade.side}",
                        skip_flags=[],
                        yes_score=trade.entry_yes_score or 0.0,
                        no_score=trade.entry_no_score or 0.0,
                        yes_prob=trade.entry_fair_probability or 0.5,
                        no_prob=1.0 - (trade.entry_fair_probability or 0.5),
                        predicted_side=trade.locked_predicted_side or ("YES" if trade.side == "BUY" else "NO"),
                        gate_results="{}",
                        yes_breakdown="{}",
                        no_breakdown="{}"
                    )
                    self.strategy.record_entry(trade.market_id, sig)
                    if self.risk_manager:
                        self.risk_manager.current_exposure = trade.position_size
                    logger.info(f"[BTC5M Engine] Rehydrated OPEN trade #{trade.id} ({sig.predicted_side}) on market {trade.market_id}")

                logger.info(f"[BTC5M Engine] Rehydration complete. trading_active={self.trading_active}, open_positions={len(open_trades)}")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[BTC5M Engine] Error during state rehydration: {e}", exc_info=True)

    async def start(self):
        self.rehydrate_state()
        self.running = True
        logger.info("[BTC5M Engine] Started. Polling Polymarket for BTC 5M markets.")
        asyncio.create_task(self._main_loop())
        asyncio.create_task(self._broadcast_loop())
        asyncio.create_task(self._fast_exit_monitor_loop())

    def stop(self):
        self.running = False
        logger.info(f"[BTC5M Engine {self.instance_id}] Stopped.")

    async def _fast_exit_monitor_loop(self):
        """High-frequency (250ms) in-memory exit monitor for active trades.
        Instantly evaluates take-profit and stop-loss using local orderbook data with zero HTTP latency.
        """
        logger.info(f"[BTC5M Engine {self.instance_id}] High-frequency exit monitor started (250ms).")
        while self.running:
            try:
                await self._check_immediate_exits()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[BTC5M Engine {self.instance_id}] Fast exit monitor loop error: {e}", exc_info=True)
            await asyncio.sleep(0.25)

    async def _check_immediate_exits(self):
        """Fast sub-second exit evaluation for active trades using local orderbook data."""
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            from app.db.models import BTC5MTrade
            open_trades = db.query(BTC5MTrade).filter(
                BTC5MTrade.status == "OPEN",
                BTC5MTrade.instance_id == self.instance_id
            ).all()
            if not open_trades:
                return

            any_closed = False
            for trade in open_trades:
                closed = await self._evaluate_and_apply_exit(db, trade)
                if closed:
                    any_closed = True

            if any_closed:
                await self.broadcast_status()
        except Exception as e:
            logger.error(f"[BTC5M Engine {self.instance_id}] Fast check exits error: {e}", exc_info=True)
        finally:
            db.close()

    async def _evaluate_and_apply_exit(self, db, trade) -> bool:
        """
        Evaluates an active OPEN trade against the latest local market state and CLOB prices.
        Executes immediate closure if TP, HARD_EXIT, or CONFIRMED_EXIT triggers.
        Returns True if trade was closed, False otherwise.
        """
        try:
            from app.db.models import BTC5MMarket, BTC5MPriceHistory
            trade_market = db.query(BTC5MMarket).filter(BTC5MMarket.market_id == trade.market_id).first()
            best_bid = None
            best_ask = None
            mid_price = None
            time_remaining_sec = 0.0

            if trade_market and trade_market.best_bid is not None and trade_market.best_ask is not None:
                best_bid = trade_market.best_bid
                best_ask = trade_market.best_ask
                mid_price = trade_market.mid_price or ((best_bid + best_ask) / 2.0)
                time_remaining_sec = trade_market.time_remaining_sec or 0.0

            if best_bid is None or best_ask is None:
                last_hist = db.query(BTC5MPriceHistory).filter(
                    BTC5MPriceHistory.market_id == trade.market_id
                ).order_by(BTC5MPriceHistory.timestamp.desc()).first()
                if last_hist:
                    best_bid = last_hist.best_bid
                    best_ask = last_hist.best_ask
                    mid_price = (best_bid + best_ask) / 2.0 if (best_bid is not None and best_ask is not None) else best_bid

            if best_bid is None:
                return False

            is_yes = (trade.locked_predicted_side == "YES") if trade.locked_predicted_side else (trade.side == "BUY")
            if is_yes:
                current_executable_price = best_bid
                current_pos_mid = mid_price
            else:
                current_executable_price = (1.0 - best_ask) if best_ask is not None else None
                current_pos_mid = (1.0 - mid_price) if mid_price is not None else None

            if current_executable_price is None:
                return False

            cache_key = f"p2b_{trade.market_id}"
            p2b = self._market_states.get(cache_key) if hasattr(self, '_market_states') else None
            btc_price = self._market_states.get("latest_btc_price") if hasattr(self, '_market_states') else None
            if btc_price is None:
                from app.api.btc5m import _get_live_btc_price
                btc_price = _get_live_btc_price()

            features = {
                "short_momentum_1m": getattr(trade_market, "short_momentum_1m", 0.0) if trade_market else 0.0,
                "bid_ask_imbalance": getattr(trade_market, "imbalance", 0.0) if trade_market else 0.0,
                "rolling_volatility": 0.001,
                "mid_price": mid_price or 0.5,
                "fair_prob_yes": mid_price or 0.5
            }
            if hasattr(self, '_btc_history') and self._btc_history and btc_price:
                now_ts = time.time()
                older_ticks = [x for x in self._btc_history if x[0] <= (now_ts - 10.0)]
                if older_ticks:
                    ref_ts, ref_p = older_ticks[-1]
                    elapsed = max(5.0, now_ts - ref_ts)
                    if ref_p > 0:
                        features["btc_momentum_1m"] = ((btc_price - ref_p) / ref_p) * min(6.0, (60.0 / elapsed))

            from app.btc5m.settings_manager import get_btc5m_settings
            from app.btc5m.exit_manager import BTC5MExitManager
            trade_settings = get_btc5m_settings(db, instance_id=self.instance_id)
            exit_mgr = BTC5MExitManager(db, instance_id=self.instance_id)

            decision, exit_price, reason, thesis_score, breakdown, audit_event = exit_mgr.evaluate_exit(
                trade=trade,
                current_executable_price=current_executable_price,
                current_mid_price=current_pos_mid,
                btc_price=btc_price,
                p2b=p2b,
                features=features,
                time_remaining_sec=time_remaining_sec,
                risk_manager=self.risk_manager,
                settings=trade_settings
            )

            if audit_event:
                exit_mgr.record_audit(
                    trade=trade,
                    event_type=audit_event,
                    current_executable_price=current_executable_price,
                    btc_price=btc_price,
                    p2b=p2b,
                    features=features,
                    time_remaining_sec=time_remaining_sec,
                    current_exit_decision=decision,
                    thesis_failure_score=thesis_score,
                    reason=reason,
                    breakdown=breakdown
                )

            if decision in ("TP", "CONFIRMED_EXIT", "HARD_EXIT"):
                trade.status = "CLOSED"
                trade.exit_time = datetime.now(timezone.utc)
                trade.exit_price = exit_price
                trade.pnl = (exit_price - trade.entry_price) * trade.quantity if (trade.entry_price is not None and trade.quantity is not None) else 0.0
                trade.exit_reason = reason
                if decision == "TP":
                    trade.resolution = "EARLY_TP"
                    trade.exit_decision_state = "TP"
                    if hasattr(trade, 'actual_rr'): trade.actual_rr = trade.planned_rr
                elif decision == "HARD_EXIT":
                    trade.resolution = "EARLY_SL"
                    trade.exit_decision_state = "HARD_EXIT"
                    if hasattr(trade, 'actual_rr') and trade.planned_risk and trade.planned_risk > 0:
                        trade.actual_rr = trade.pnl / trade.planned_risk
                else:
                    trade.resolution = "EARLY_SL"
                    trade.exit_decision_state = "CONFIRMED_EXIT"
                    if hasattr(trade, 'actual_rr') and trade.planned_risk and trade.planned_risk > 0:
                        trade.actual_rr = trade.pnl / trade.planned_risk

                self.risk_manager.record_trade_result(trade.pnl)
                self.risk_manager.current_exposure = max(0, self.risk_manager.current_exposure - trade.position_size)
                db.commit()
                self.strategy.record_exit(trade.market_id)
                logger.info(f"[BTC5M Fast Exit Monitor {self.instance_id}] INSTANT EXIT {decision} trade #{trade.id} ({trade.side}) @ ${exit_price:.4f} | PnL: ${trade.pnl:.2f} | Reason: {reason}")
                return True
            else:
                db.commit()
                return False
        except Exception as e:
            logger.error(f"[BTC5M Fast Exit Monitor {self.instance_id}] _evaluate_and_apply_exit error: {e}", exc_info=True)
            return False

    async def broadcast_status(self):
        """Build and broadcast current BTC 5M status to connected WebSocket clients."""
        try:
            from app.api.websockets import manager
            # If no clients connected, skip DB query overhead
            if not manager.active_connections:
                return

            from app.db.session import SessionLocal
            from app.api.btc5m import build_btc5m_status_payload
            db = SessionLocal()
            try:
                payload = await asyncio.to_thread(build_btc5m_status_payload, db, self.instance_id)
                await manager.broadcast_btc5m(payload, instance_id=self.instance_id)
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"[BTC5M Engine {self.instance_id}] Broadcast error: {e}")

    async def _broadcast_loop(self):
        """Asynchronous low-latency streaming loop pushing status ticks to WebSocket clients."""
        logger.info("[BTC5M Engine] WebSocket broadcast loop started.")
        while self.running:
            try:
                await self.broadcast_status()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[BTC5M Engine] Broadcast loop tick error: {e}")
            await asyncio.sleep(1.0)

    async def _main_loop(self):
        """Main async loop — runs indefinitely with exponential backoff on fatal loop errors."""
        backoff = 5
        while self.running:
            try:
                await self._cycle()
                backoff = 5
            except asyncio.CancelledError:
                logger.info("[BTC5M Engine] Main loop cancelled.")
                break
            except Exception as e:
                logger.error(f"[BTC5M Engine] Cycle error: {e}", exc_info=True)
                await asyncio.sleep(backoff)
                backoff = min(60, backoff * 2)
            sleep_sec = 1.0 if getattr(self, '_in_entry_window', False) else POLL_INTERVAL_SECONDS
            await asyncio.sleep(sleep_sec)

    async def _cycle(self):
        """
        One full cycle:
        1. Settle open trades
        2. Settle skips for hypothetical outcomes
        3. Discover BTC 5M markets from Polymarket.
        4. For each valid market: compute features, evaluate strategy.
        5. Persist signals to DB.
        6. Execute paper trades for ENTER signals (when trading_active).
        """
        try:
            await self._settle_trades()
        except Exception as e:
            logger.error(f"[BTC5M Engine] Settle trades error: {e}", exc_info=True)

        try:
            await self._settle_skips()
        except Exception as e:
            logger.error(f"[BTC5M Engine] Settle skips error: {e}", exc_info=True)

        logger.info("[BTC5M Engine] Discovering BTC 5M markets...")
        markets = None
        try:
            markets = await async_discover_btc5m_markets()
        except Exception as e:
            logger.error(f"[BTC5M Engine] Async discovery error: {e}", exc_info=True)
            try:
                markets = await asyncio.to_thread(discover_btc5m_markets)
            except Exception as e2:
                logger.error(f"[BTC5M Engine] Fallback discovery error: {e2}", exc_info=True)

        if not markets:
            logger.info("[BTC5M Engine] No BTC 5M markets discovered this cycle")
            return

        valid = [m for m in markets if m.is_valid]
        logger.info(f"[BTC5M Engine] {len(valid)}/{len(markets)} markets valid. Processing...")

        # Detect if we are in prime entry window (210s - 295s) for 1s rapid polling
        self._in_entry_window = any(210.0 <= getattr(m, 'time_remaining_sec', 0.0) <= 295.0 for m in valid)

        # Background market persistence so evaluation runs with zero DB wait
        asyncio.create_task(asyncio.to_thread(self._persist_markets, markets))

        for m in valid[:MAX_CONCURRENT_MARKETS]:
            try:
                await self._process_market(m)
            except Exception as e:
                logger.error(f"[BTC5M Engine] Error processing market {m.market_id}: {e}", exc_info=True)

        # Trigger real-time status broadcast on cycle completion
        try:
            await self.broadcast_status()
        except Exception:
            pass


    def _get_btc5m_reference_data(self, market: BTC5MMarketInfo):
        """
        Return (btc_price, price_to_beat).

        BTC price uses the existing Chainlink-on-Polygon path already
        used by the BTC5M API. Active-market P2B is deliberately NOT
        guessed from previous-market finalPrice.
        """
        btc_price = None
        price_to_beat = None

        if not hasattr(self, '_market_states'):
            self._market_states = {}

        RPC_URLS = [
            "https://polygon.drpc.org",
            "https://polygon-bor-rpc.publicnode.com",
            "https://1rpc.io/matic"
        ]
        try:
            import httpx
            for rpc_url in RPC_URLS:
                try:
                    with httpx.Client(timeout=1.5, headers={"User-Agent": "Mozilla/5.0"}) as client:
                        resp = client.post(
                            rpc_url,
                            json={
                                "jsonrpc": "2.0",
                                "id": 1,
                                "method": "eth_call",
                                "params": [
                                    {
                                        "to": "0xc907E116054Ad103354f2D350FD2514433D57F6f",
                                        "data": "0x50d25bcd"
                                    },
                                    "latest"
                                ]
                            }
                        )
                        if resp.status_code == 200:
                            payload = resp.json()
                            result = payload.get("result")
                            if result and result != "0x":
                                btc_price = int(result, 16) / 100000000.0
                                break
                except Exception:
                    continue

            # Fallback to Coinbase spot price matching global live BTC
            if btc_price is None:
                try:
                    with httpx.Client(timeout=1.5, headers={"User-Agent": "Mozilla/5.0"}) as client:
                        resp = client.get("https://api.coinbase.com/v2/prices/BTC-USD/spot")
                        if resp.status_code == 200:
                            btc_price = float(resp.json()["data"]["amount"])
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("[BTC5M Engine] BTC reference fetch failed: %s", exc)

        # Cache the authoritative Chainlink BTC price exactly at the start time of this market as P2B
        if btc_price is not None:
            self._market_states["latest_btc_price"] = btc_price
            if market.start_time and market.end_time:
                now_utc = datetime.now(timezone.utc)
                start_utc = market.start_time.replace(tzinfo=timezone.utc) if market.start_time.tzinfo is None else market.start_time
                end_utc = market.end_time.replace(tzinfo=timezone.utc) if market.end_time.tzinfo is None else market.end_time
                
                if now_utc >= start_utc and now_utc < end_utc:
                    cache_key = f"p2b_{market.market_id}"
                    if cache_key not in self._market_states:
                        self._market_states[cache_key] = btc_price
                        logger.info(f"[BTC5M Engine] Captured authoritative P2B {btc_price} for market {market.market_id} at {now_utc}")
                    price_to_beat = self._market_states[cache_key]

            if price_to_beat is None and (market.time_remaining_sec and 0 < market.time_remaining_sec <= 300):
                cache_key = f"p2b_{market.market_id}"
                if cache_key not in self._market_states:
                    self._market_states[cache_key] = btc_price
                    logger.info(f"[BTC5M Engine] Fallback captured P2B {btc_price} for active market {market.market_id}")
                price_to_beat = self._market_states[cache_key]

        return btc_price, price_to_beat

    async def _get_btc5m_reference_data_async(self, market: BTC5MMarketInfo):
        """
        Asynchronously and concurrently fetch BTC reference price and authoritative P2B:
        - Races multiple Polygon RPC nodes in parallel using asyncio.as_completed.
        - The fastest responding node returns in <50ms instead of sequential 1500ms timeouts.
        - Caches authoritative P2B at exact market start time.
        """
        btc_price = None
        price_to_beat = None

        if not hasattr(self, '_market_states'):
            self._market_states = {}

        now_mono = time.monotonic()
        if hasattr(self, '_cached_rpc_btc') and (now_mono - getattr(self, '_cached_rpc_time', 0.0)) < 1.2:
            btc_price = self._cached_rpc_btc

        RPC_URLS = [
            "https://polygon.drpc.org",
            "https://polygon-bor-rpc.publicnode.com",
            "https://1rpc.io/matic"
        ]

        import httpx

        async def _query_rpc(client: httpx.AsyncClient, url: str) -> Optional[float]:
            try:
                resp = await client.post(
                    url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "eth_call",
                        "params": [
                            {
                                "to": "0xc907E116054Ad103354f2D350FD2514433D57F6f",
                                "data": "0x50d25bcd"
                            },
                            "latest"
                        ]
                    },
                    timeout=2.0
                )
                if resp.status_code == 200:
                    payload = resp.json()
                    result = payload.get("result")
                    if result and result != "0x":
                        return int(result, 16) / 100000000.0
            except Exception:
                pass
            return None

        if btc_price is None:
            try:
                async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
                    tasks = [asyncio.create_task(_query_rpc(client, url)) for url in RPC_URLS]
                    for fut in asyncio.as_completed(tasks):
                        try:
                            p = await fut
                            if p is not None and p > 0:
                                btc_price = p
                                for t in tasks:
                                    if not t.done():
                                        t.cancel()
                                break
                        except Exception:
                            continue

                    # Fallback to Coinbase spot if all RPC nodes failed
                    if btc_price is None:
                        try:
                            resp = await client.get("https://api.coinbase.com/v2/prices/BTC-USD/spot", timeout=1.5)
                            if resp.status_code == 200:
                                btc_price = float(resp.json()["data"]["amount"])
                        except Exception:
                            pass
            except Exception as exc:
                logger.warning("[BTC5M Engine] Async BTC reference fetch failed: %s", exc)

        if btc_price is not None:
            self._cached_rpc_btc = btc_price
            self._cached_rpc_time = now_mono

        # Fallback to sync method if needed
        if btc_price is None:
            btc_price, _ = self._get_btc5m_reference_data(market)

        if btc_price is not None:
            self._market_states["latest_btc_price"] = btc_price
            if market.start_time and market.end_time:
                now_utc = datetime.now(timezone.utc)
                start_utc = market.start_time.replace(tzinfo=timezone.utc) if market.start_time.tzinfo is None else market.start_time
                end_utc = market.end_time.replace(tzinfo=timezone.utc) if market.end_time.tzinfo is None else market.end_time

                if now_utc >= start_utc and now_utc < end_utc:
                    cache_key = f"p2b_{market.market_id}"
                    if cache_key not in self._market_states:
                        self._market_states[cache_key] = btc_price
                        logger.info(f"[BTC5M Engine] Captured authoritative P2B {btc_price} for market {market.market_id} at {now_utc}")
                    price_to_beat = self._market_states[cache_key]

            if price_to_beat is None and (market.time_remaining_sec and 0 < market.time_remaining_sec <= 300):
                cache_key = f"p2b_{market.market_id}"
                if cache_key not in self._market_states:
                    self._market_states[cache_key] = btc_price
                    logger.info(f"[BTC5M Engine] Fallback captured P2B {btc_price} for active market {market.market_id}")
                price_to_beat = self._market_states[cache_key]

        return btc_price, price_to_beat

    async def _process_market(self, market: BTC5MMarketInfo):
        """Process a single BTC 5M market end-to-end."""
        try:
            # Get current balance from RiskManager
            current_balance = self.risk_manager.current_balance

            # Features require scalar values from the market
            features = self.feature_engine.update_and_compute(
                market_id=market.market_id,
                price=market.mid_price,
                bid=market.best_bid,
                ask=market.best_ask,
                spread=market.spread,
                bid_depth=market.bid_depth,
                ask_depth=market.ask_depth,
                imbalance=market.imbalance,
                time_remaining_sec=market.time_remaining_sec,
            )
            # Inject orderbook fields into features for strategy
            features["bid"] = market.best_bid
            features["ask"] = market.best_ask
            features["bid_depth"] = market.bid_depth
            features["ask_depth"] = market.ask_depth

            # Fetch reference data BEFORE strategy evaluation via asynchronous RPC race.
            t0_ref = time.perf_counter()
            btc_price, price_to_beat = await self._get_btc5m_reference_data_async(market)
            latency_tracker.record("chainlink_ms", (time.perf_counter() - t0_ref) * 1000)

            # Record spot BTC ticks and compute true 1m spot BTC momentum
            if btc_price is not None and btc_price > 0:
                now_ts = time.time()
                self._btc_history.append((now_ts, btc_price))
                cutoff = now_ts - 900.0
                self._btc_history = [x for x in self._btc_history if x[0] >= cutoff]
                older_ticks = [x for x in self._btc_history if x[0] <= (now_ts - 10.0)]
                if older_ticks:
                    ref_ts, ref_p = older_ticks[-1]
                    elapsed = max(5.0, now_ts - ref_ts)
                    if ref_p > 0:
                        raw_mom = (btc_price - ref_p) / ref_p
                        features["btc_momentum_1m"] = raw_mom * min(6.0, (60.0 / elapsed))

            # Evaluate both YES and NO with explicit BTC/P2B inputs.
            t0_strat = time.perf_counter()
            signal = self.strategy.evaluate(
                market_id=market.market_id,
                condition_id=market.condition_id,
                question=market.question,
                yes_token_id=market.yes_token_id,
                no_token_id=market.no_token_id,
                features=features,
                orderbook_timestamp=market.orderbook_timestamp,
                btc_price=btc_price,
                price_to_beat=price_to_beat,
                current_balance=current_balance,
            )
            latency_tracker.record("strategy_ms", (time.perf_counter() - t0_strat) * 1000)

            # Execute paper trade immediately if ENTER for zero decision latency
            if signal.state == "ENTER" and not settings.live_trading_enabled:
                if not self.trading_active:
                    logger.info(f"[BTC5M Engine] ENTER signal received, but BOT IS STOPPED (trading_active=False). Blocking trade entry.")
                    try:
                        self._record_skip(signal, "SKIP - Trading paused (Bot is STOPPED)")
                    except Exception as e:
                        logger.error(f"Error recording stopped skip: {e}")
                else:
                    t0_exec = time.perf_counter()
                    success = await asyncio.to_thread(self._execute_paper_trade, signal, current_balance)
                    latency_tracker.record("execution_ms", (time.perf_counter() - t0_exec) * 1000)
                    if success:
                        self.strategy.record_entry(market.market_id, signal)
                        logger.info(f"[BTC5M Engine] PAPER ENTRY SUCCESS: {signal.question[:50]} | side={signal.side} | size=${signal.position_size:.2f}")
                        asyncio.create_task(self.broadcast_status())
                    else:
                        logger.error(f"[BTC5M Engine] PAPER ENTRY FAILED: Database order routing error for market {market.market_id}")

                # Persist signal in background so execution path has 0ms DB latency
                asyncio.create_task(asyncio.to_thread(self._persist_signal, signal))
            else:
                # Background persist signal
                asyncio.create_task(asyncio.to_thread(self._persist_signal, signal))
                reason_ext = getattr(signal, 'skip_flags', signal.reason)
                if hasattr(signal, 'skip_flags') and isinstance(signal.skip_flags, list) and len(signal.skip_flags) > 0:
                    reason_ext = " | ".join(signal.skip_flags)
                logger.info(f"[BTC5M Engine] {signal.state}: {signal.question[:40]} | {reason_ext}")
                
                # Record the skip to the DB
                if signal.state == "SKIP":
                    try:
                        t0_skip = time.perf_counter()
                        self._record_skip(signal, reason_ext)
                        latency_tracker.record("db_write_ms", (time.perf_counter() - t0_skip) * 1000)
                    except Exception as e:
                        logger.error(f"Error recording skip: {e}")


        except Exception as e:
            logger.error(f"[BTC5M Engine] Error processing market {market.market_id}: {e}", exc_info=True)

    def _persist_markets(self, markets: list):
        db = SessionLocal()
        from app.db.models import BTC5MPriceHistory
        try:
            for m in markets:
                existing = db.query(BTC5MMarket).filter(BTC5MMarket.market_id == m.market_id).first()
                now = datetime.now(timezone.utc)
                
                if m.best_bid is not None and m.best_ask is not None:
                    db.add(BTC5MPriceHistory(
                        market_id=m.market_id,
                        timestamp=now,
                        best_bid=m.best_bid,
                        best_ask=m.best_ask
                    ))

                if existing:
                    existing.best_bid = m.best_bid
                    existing.best_ask = m.best_ask
                    existing.bid_depth = m.bid_depth
                    existing.ask_depth = m.ask_depth
                    existing.spread = m.spread
                    existing.mid_price = m.mid_price
                    existing.imbalance = m.imbalance
                    existing.liquidity = m.liquidity
                    existing.time_remaining_sec = m.time_remaining_sec
                    existing.orderbook_timestamp = m.orderbook_timestamp
                    existing.is_valid = m.is_valid
                    existing.rejection_reason = m.rejection_reason
                    existing.last_seen = now
                else:
                    db.add(BTC5MMarket(
                        market_id=m.market_id,
                        condition_id=m.condition_id,
                        question=m.question,
                        yes_token_id=m.yes_token_id,
                        no_token_id=m.no_token_id,
                        end_time=m.end_time,
                        start_time=m.start_time,
                        best_bid=m.best_bid,
                        best_ask=m.best_ask,
                        bid_depth=m.bid_depth,
                        ask_depth=m.ask_depth,
                        spread=m.spread,
                        mid_price=m.mid_price,
                        imbalance=m.imbalance,
                        liquidity=m.liquidity,
                        time_remaining_sec=m.time_remaining_sec,
                        orderbook_timestamp=m.orderbook_timestamp,
                        is_valid=m.is_valid,
                        rejection_reason=m.rejection_reason,
                        last_seen=now,
                    ))
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"[BTC5M Engine] DB persist markets error: {e}")
        finally:
            db.close()

    def _persist_signal(self, signal: BTC5MSignal):
        db = SessionLocal()
        try:
            db.add(BTC5MSignalDB(
                market_id=signal.market_id,
                condition_id=signal.condition_id,
                question=signal.question,
                yes_token_id=signal.yes_token_id,
                no_token_id=signal.no_token_id,
                timestamp=signal.timestamp,
                state=signal.state,
                side=signal.side,
                entry_price=signal.entry_price,
                bid=signal.bid,
                ask=signal.ask,
                spread=signal.spread,
                bid_depth=signal.bid_depth,
                ask_depth=signal.ask_depth,
                momentum=signal.momentum,
                imbalance=signal.imbalance,
                ob_pressure=signal.ob_pressure,
                volatility=signal.volatility,
                momentum_persistence=signal.momentum_persistence,
                market_probability=signal.market_probability,
                fair_probability=signal.fair_probability,
                raw_edge=signal.raw_edge,
                spread_cost=signal.spread_cost,
                slippage_cost=signal.slippage_cost,
                fees=signal.fees,
                net_edge=signal.net_edge,
                risk_pct=signal.risk_pct,
                position_size=signal.position_size,
                time_remaining_sec=signal.time_remaining_sec,
                model_version=signal.model_version,
                strategy=signal.strategy,
                reason=signal.reason,
                yes_score=signal.yes_score,
                no_score=signal.no_score,
                yes_prob=signal.yes_prob,
                no_prob=signal.no_prob,
                predicted_side=signal.predicted_side,
                gate_results=signal.gate_results,
                yes_breakdown=signal.yes_breakdown,
                no_breakdown=signal.no_breakdown,
                instance_id=self.instance_id,
            ))
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"[BTC5M Engine {self.instance_id}] DB persist signal error: {e}")
        finally:
            db.close()

    def _execute_paper_trade(self, signal: BTC5MSignal, balance: float):
        """Record paper trade entry in DB."""
        db = SessionLocal()
        try:
            quantity = signal.position_size / (signal.entry_price + 1e-9)

            # Core Rule — Immutable Trade Thesis Mapping
            is_yes = (signal.predicted_side == "YES") or (signal.side == "BUY" and signal.predicted_side != "NO")
            locked_pred = "YES" if is_yes else "NO"
            locked_dir = "UP" if is_yes else "DOWN"
            locked_outcome = "YES" if is_yes else "NO"
            locked_token = signal.yes_token_id if is_yes else (signal.no_token_id or signal.yes_token_id)

            trade = BTC5MTrade(
                instance_id=self.instance_id,
                market_id=signal.market_id,
                condition_id=signal.condition_id,
                question=signal.question,
                yes_token_id=signal.yes_token_id,
                no_token_id=signal.no_token_id,
                side=signal.side,
                entry_price=signal.entry_price,
                quantity=quantity,
                position_size=signal.position_size,
                spread_at_entry=signal.spread,
                fees=signal.fees,
                slippage=signal.slippage_cost,
                net_edge=signal.net_edge,
                momentum_at_entry=signal.momentum,
                imbalance_at_entry=signal.imbalance,
                time_remaining_at_entry=signal.time_remaining_sec,
                yes_score=signal.yes_score,
                no_score=signal.no_score,
                planned_risk=signal.planned_risk,
                planned_reward=signal.planned_reward,
                planned_rr=signal.planned_rr,
                stop_loss_price=signal.stop_loss_price,
                take_profit_price=signal.take_profit_price,
                strategy="BTC_5M",
                model_version=signal.model_version,
                entry_reason=signal.reason,
                status="OPEN",
                entry_time=signal.timestamp,
                # Immutable Thesis Fields (Write-Once)
                locked_predicted_side=locked_pred,
                locked_direction=locked_dir,
                locked_outcome=locked_outcome,
                locked_token_id=locked_token,
                execution_side="BUY",
                entry_yes_score=signal.yes_score,
                entry_no_score=signal.no_score,
                entry_fair_probability=signal.fair_probability,
                entry_market_probability=signal.market_probability,
                entry_net_edge=signal.net_edge,
                entry_planned_rr=signal.planned_rr,
                entry_stop_price=signal.stop_loss_price,
                entry_target_price=signal.take_profit_price,
                prediction_locked_at=signal.timestamp,
                prediction_lock_version="1.0",
                # Smart Exit System initial state
                exit_decision_state="HOLD",
                hard_stop_price=max(0.01, (signal.stop_loss_price or 0.10) - 0.02)
            )
            db.add(trade)
            db.commit()

            # Update RiskManager state
            self.risk_manager.current_exposure += signal.position_size
            return True

        except Exception as e:
            db.rollback()
            logger.error(f"[BTC5M Engine {self.instance_id}] Execute paper trade error: {e}", exc_info=True)
            return False
        finally:
            db.close()

    async def _settle_trades(self):
        """Find OPEN paper trades, query Polymarket Gamma API via YES token ID, and settle if closed."""
        db = SessionLocal()
        try:
            open_trades = db.query(BTC5MTrade).filter(
                BTC5MTrade.status == "OPEN",
                BTC5MTrade.instance_id == self.instance_id
            ).all()
            if not open_trades:
                return

            import aiohttp, json as _json, math as _math
            any_settled = False
            async with aiohttp.ClientSession() as session:
                for trade in open_trades:
                    # Derive the bucket slug from entry_time to find the exact market
                    # entry_time is naive UTC stored in DB
                    try:
                        entry_ts = int(trade.entry_time.replace(tzinfo=timezone.utc).timestamp())
                    except Exception:
                        entry_ts = int(trade.entry_time.timestamp()) if trade.entry_time else 0

                    now_ts_curr = int(datetime.now(timezone.utc).timestamp())
                    # While candle is active (< 280s elapsed), delegate exclusively to sub-second local exit monitor
                    if (now_ts_curr - entry_ts) < 280:
                        closed_now = await self._evaluate_and_apply_exit(db, trade)
                        if closed_now:
                            any_settled = True
                        continue

                    # The BTC5M market ends at the next 5-minute boundary from entry
                    # Try the bucket at entry and entry+300
                    buckets_to_check = []
                    for offset in [0, 300, 600, -300]:
                        b = entry_ts - (entry_ts % 300) + offset
                        buckets_to_check.append(b)

                    found_resolution = False
                    for bucket_ts in buckets_to_check:
                        slug = f"btc-updown-5m-{bucket_ts}"
                        url = f"https://gamma-api.polymarket.com/events?slug={slug}"
                        try:
                            async with session.get(url, timeout=3.0) as resp:
                                if resp.status != 200:
                                    continue
                                data = await resp.json()
                        except Exception:
                            continue

                        for event in (data if isinstance(data, list) else []):
                            for mkt in event.get("markets", []):
                                # Verify this is the right market via conditionId or clobTokenIds
                                clob_ids = mkt.get("clobTokenIds", [])
                                if isinstance(clob_ids, str):
                                    try:
                                        clob_ids = _json.loads(clob_ids)
                                    except Exception:
                                        clob_ids = []
                                mkt_cid = mkt.get("conditionId", "")
                                is_match = (mkt_cid == trade.condition_id) or (trade.yes_token_id in clob_ids)
                                if not is_match:
                                    continue

                                if not mkt.get("closed"):
                                    closed_now = await self._evaluate_and_apply_exit(db, trade)
                                    found_resolution = True
                                    if closed_now:
                                        any_settled = True
                                    break

                                # Market is closed - resolve
                                try:
                                    outcomes = _json.loads(mkt.get("outcomes", "[]")) if isinstance(mkt.get("outcomes"), str) else mkt.get("outcomes", [])
                                    prices_raw = _json.loads(mkt.get("outcomePrices", "[]")) if isinstance(mkt.get("outcomePrices"), str) else mkt.get("outcomePrices", [])
                                    prices = [float(p) for p in prices_raw]
                                except Exception:
                                    continue

                                resolution = None
                                winning_idx = -1
                                for i, price in enumerate(prices):
                                    if price >= 0.99:
                                        label = outcomes[i].lower() if i < len(outcomes) else ""
                                        winning_idx = i
                                        if label in ("yes", "up"):
                                            resolution = "YES"
                                        elif label in ("no", "down"):
                                            resolution = "NO"
                                        break

                                if not resolution:
                                    logger.warning(f"[BTC5M Engine] Could not determine resolution from prices {prices} outcomes {outcomes}")
                                    continue

                                # Settle the trade
                                trade.status = "CLOSED"
                                trade.resolution = resolution
                                trade.exit_time = datetime.now(timezone.utc)

                                trade_pred = trade.locked_predicted_side or ("YES" if trade.side == "BUY" else "NO")
                                is_win = (trade_pred == resolution)

                                if is_win:
                                    revenue = trade.quantity * 1.0
                                    trade.pnl = revenue - trade.position_size
                                    trade.exit_price = 1.0
                                else:
                                    trade.pnl = -trade.position_size
                                    trade.exit_price = 0.0
                                    
                                if trade.planned_risk and trade.planned_risk > 0:
                                    trade.actual_rr = trade.pnl / trade.planned_risk

                                # Update risk manager via proper API
                                trade.exit_decision_state = "RESOLVED"
                                try:
                                    from app.btc5m.exit_manager import BTC5MExitManager
                                    exit_mgr = BTC5MExitManager(db, instance_id=self.instance_id)
                                    exit_mgr.record_audit(
                                        trade=trade,
                                        event_type="RESOLUTION_EXIT",
                                        current_executable_price=trade.exit_price,
                                        btc_price=None,
                                        p2b=None,
                                        features={},
                                        time_remaining_sec=0.0,
                                        current_exit_decision="RESOLVED",
                                        thesis_failure_score=0.0 if is_win else 100.0,
                                        reason=f"Market settled at resolution: {resolution} (Win: {is_win})",
                                        breakdown={"is_win": is_win, "resolution": resolution}
                                    )
                                except Exception as exc:
                                    logger.debug(f"Audit log on resolution error: {exc}")

                                db.commit()
                                self.strategy.record_exit(trade.market_id)
                                logger.info(f"[BTC5M Engine] SETTLED {trade.side} trade. Resolution: {resolution} | PnL: {trade.pnl:.2f} | Balance: {self.risk_manager.current_balance:.2f}")
                                found_resolution = True
                                any_settled = True
                                break
                            if found_resolution:
                                break
                        if found_resolution:
                            break

            if any_settled:
                asyncio.create_task(self.broadcast_status())
        except Exception as e:
            logger.error(f"[BTC5M Engine] Settle trades error: {e}", exc_info=True)
        finally:
            db.close()



    def _record_skip(self, signal, reason: str):
        from app.db.session import SessionLocal
        from app.db.models import BTC5MSkip
        db = SessionLocal()
        try:
            skip = BTC5MSkip(
                market_id=signal.market_id,
                question=signal.question,
                yes_score=getattr(signal, "yes_score", 0.0),
                no_score=getattr(signal, "no_score", 0.0),
                yes_prob=getattr(signal, "yes_prob", 0.0),
                no_prob=getattr(signal, "no_prob", 0.0),
                net_edge=signal.net_edge,
                spread=signal.spread,
                liquidity=signal.bid_depth + signal.ask_depth,
                volatility=signal.volatility,
                time_remaining=signal.time_remaining_sec,
                planned_rr=signal.planned_rr,
                skip_reason=reason,
                predicted_side=getattr(signal, "predicted_side", "NONE"),
                gate_results=getattr(signal, "gate_results", "{}"),
                yes_breakdown=getattr(signal, "yes_breakdown", "{}"),
                no_breakdown=getattr(signal, "no_breakdown", "{}")
            )
            db.add(skip)
            db.commit()
        finally:
            db.close()

    async def _settle_skips(self):
        """Find pending skips that haven't been hypothetical resolved yet.
        Bounded to at most 3 items per cycle to guarantee zero event-loop latency.
        """
        from app.db.session import SessionLocal
        from app.db.models import BTC5MSkip
        import aiohttp
        from datetime import timezone, datetime, timedelta
        db = SessionLocal()
        try:
            now_dt = datetime.now(timezone.utc)
            now_ts = int(now_dt.timestamp())
            # Skips need at least 300s to have settled
            cutoff_dt = now_dt - timedelta(seconds=300)
            pending_skips = db.query(BTC5MSkip).filter(
                BTC5MSkip.actual_resolution == None,
                BTC5MSkip.timestamp <= cutoff_dt
            ).order_by(BTC5MSkip.timestamp.desc()).limit(3).all()

            if not pending_skips:
                return

            async with aiohttp.ClientSession() as session:
                for skip in pending_skips:
                    try:
                        entry_ts = int(skip.timestamp.replace(tzinfo=timezone.utc).timestamp())
                    except Exception:
                        entry_ts = int(skip.timestamp.timestamp()) if skip.timestamp else 0

                    if entry_ts < (now_ts - 7200):
                        skip.actual_resolution = "EXPIRED"
                        skip.hypothetical_outcome = "EXPIRED"
                        db.commit()
                        continue

                    buckets_to_check = [
                        entry_ts - (entry_ts % 300),
                        entry_ts - (entry_ts % 300) + 300
                    ]

                    for bucket_ts in buckets_to_check:
                        slug = f"btc-updown-5m-{bucket_ts}"
                        url = f"https://gamma-api.polymarket.com/events?slug={slug}"
                        try:
                            async with session.get(url, timeout=2.0) as resp:
                                if resp.status == 200:
                                    events = await resp.json()
                                    if events and isinstance(events, list):
                                        ev = events[0]
                                        closed = ev.get("closed", False)
                                        if closed and ev.get("eventMetadata", {}).get("finalPrice"):
                                            final = ev["eventMetadata"].get("finalPrice")
                                            p2b = ev["eventMetadata"].get("priceToBeat")
                                            if final and p2b:
                                                final = float(final)
                                                p2b = float(p2b)
                                                res = "YES" if final >= p2b else "NO"
                                                skip.actual_resolution = res
                                                best_side = "YES" if skip.yes_score >= skip.no_score else "NO"
                                                skip.hypothetical_outcome = "WIN" if res == best_side else "LOSS"
                                                db.commit()
                                                break
                        except Exception:
                            pass
        finally:
            db.close()

# Primary Bot (Single Slot 5M)
btc5m_engine = BTC5MEngine(
    instance_id="instance_1",
    name="BTC 5M Trading Bot",
    mode="fixed_dollar",
    tp_dollar=1.0,
    sl_dollar=10.0,
    only_short=False,
    slot_mode="single_5m"
)

ENGINES: Dict[str, BTC5MEngine] = {
    "instance_1": btc5m_engine,
}

def get_engine(instance_id: str = "instance_1") -> BTC5MEngine:
    return ENGINES.get(instance_id, btc5m_engine)
