import asyncio
import logging
from datetime import datetime, timedelta
from app.config import settings
from app.db.session import SessionLocal
from app.db.models import Market, MarketSnapshot, Signal, BotEvent
from app.db.schemas import MarketTick
from app.trading.risk import RiskManager
from app.engine.features import FeatureEngine
from app.engine.model import ProbabilityModel
from app.engine.strategy import StrategyEngine
from app.connectors.polymarket import PolymarketConnector
from app.api.websockets import manager
from app.research.snapshot_validator import classify_snapshot

logger = logging.getLogger(__name__)

from app.trading.paper_engine import PaperEngine

class Orchestrator:
    def __init__(self):
        self.poly = PolymarketConnector()
        self.running = False
        
        self.risk_manager = RiskManager()
        
        # Phase 6 Long-Term Paper Test Session Controller
        from app.engine.paper_controller import PaperTestController
        self.paper_controller = PaperTestController(self.risk_manager)
        
        self.paper_engine = PaperEngine(self.risk_manager)
        self.feature_engine = FeatureEngine()
        self.prob_model = ProbabilityModel()
        self.strategy = StrategyEngine(self.prob_model)
        
        # OMITTED: self.poly.register_callback(self.handle_tick)
        self.market_poll_times = {} # Track adaptive polling times
        
        self.last_latency = 0

    async def start(self):
        self.running = True
        logger.info(f"Starting Orchestrator in {settings.data_mode} mode")
        
        asyncio.create_task(self._poly_scanner_loop())
        asyncio.create_task(self._poly_polling_loop())
            
        asyncio.create_task(self._broadcast_loop())

        while self.running:
            await asyncio.sleep(1)
            
    async def _broadcast_loop(self):
        while self.running:
            markets_data = await asyncio.to_thread(self._sync_get_broadcast_data)
            if markets_data is not None:
                try:
                    await manager.broadcast({"type": "markets", "data": markets_data})
                except Exception as e:
                    logger.error(f"Broadcast error: {e}")
            await asyncio.sleep(2)

    def _sync_get_broadcast_data(self):
        db = SessionLocal()
        try:
            active_markets = db.query(Market).filter(Market.active == True).all()
            markets_data = []
            for m in active_markets:
                markets_data.append({
                    "market_id": m.market_id,
                    "question": m.question,
                    "token": m.token,
                    "current_price": m.current_price,
                    "spread": getattr(m, 'spread', 0.0),
                    "imbalance": getattr(m, 'imbalance', 0.0)
                })
            return markets_data
        except Exception as e:
            logger.error(f"DB read error: {e}")
            return None
        finally:
            db.close()

    async def _poly_scanner_loop(self):
        logger.info("[POLYMARKET] Requesting markets...")
        while self.running:
            try:
                markets = await self.poly.get_active_markets(limit=100)
                logger.info(f"[POLYMARKET] Received {len(markets)} markets")
                await self.process_poly_markets(markets)
            except Exception as e:
                logger.error(f"[POLYMARKET] ERROR {e}. Retry in 60 seconds")
            await asyncio.sleep(60)

    async def _poly_polling_loop(self):
        import time
        # Polls orderbooks for active markets we are tracking using batch API
        while self.running:
            try:
                active_markets = await asyncio.to_thread(self._sync_get_active_market_ids)
                if active_markets:
                    now = time.time()
                    # ADAPTIVE POLLING PRIORITY FILTER
                    to_poll = []
                    for m_id in active_markets:
                        if now >= self.market_poll_times.get(m_id, 0):
                            to_poll.append(m_id)
                            
                    if to_poll:
                        valid_asset_ids = set()
                        
                        # Batch fetch in chunks of 50
                        for i in range(0, len(to_poll), 50):
                            chunk = to_poll[i:i+50]
                            ticks = await self.poly.fetch_markets_books(chunk)
                            
                            # SMART BATCH PROCESSING
                            await asyncio.to_thread(self._sync_handle_ticks_batch, ticks, now)
                            
                            for t in ticks:
                                valid_asset_ids.add(t.market_id)
                            await asyncio.sleep(0.1) # reduced sleep since we batch and adaptive poll
                            
                        invalid = set(to_poll) - valid_asset_ids
                        self.last_valid_clob_count = len(valid_asset_ids)
                        self.last_invalid_clob_count = len(invalid)
                        
                        # Clear quarantine for valid markets
                        if valid_asset_ids:
                            await asyncio.to_thread(self._sync_clear_quarantine, list(valid_asset_ids))
                        
                        if invalid:
                            logger.warning(f"[SCANNER] Quarantining {len(invalid)} invalid/404 tokens for 5 minutes.")
                            await asyncio.to_thread(self._sync_quarantine_invalid, list(invalid))
                        
            except Exception as e:
                logger.error(f"Polling loop error: {e}")
            await asyncio.sleep(2)

    def _sync_get_active_market_ids(self):
        db = SessionLocal()
        try:
            # Only poll if not quarantined and not expired
            now = datetime.utcnow()
            return [m.market_id for m in db.query(Market).filter(
                Market.active == True,
                (Market.end_time == None) | (Market.end_time > now),
                (Market.quarantine_until == None) | (Market.quarantine_until < now)
            ).all()]
        finally:
            db.close()
            
    def _sync_quarantine_invalid(self, invalid_ids):
        db = SessionLocal()
        try:
            quarantine_time = datetime.utcnow() + timedelta(minutes=5)
            db.query(Market).filter(Market.market_id.in_(invalid_ids)).update({"quarantine_until": quarantine_time}, synchronize_session=False)
            db.commit()
            self.tracked_markets_count = db.query(Market).filter(Market.active == True).count()
        except Exception as e:
            db.rollback()
            logger.error(f"Error quarantining markets: {e}")
        finally:
            db.close()
            
    def _sync_clear_quarantine(self, valid_ids):
        db = SessionLocal()
        try:
            db.query(Market).filter(
                Market.market_id.in_(valid_ids), 
                Market.quarantine_until != None
            ).update({"quarantine_until": None}, synchronize_session=False)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error clearing quarantine: {e}")
        finally:
            db.close()

    def _sync_handle_ticks_batch(self, ticks: list[MarketTick], now_time: float):
        if not ticks:
            return
            
        db = SessionLocal()
        try:
            # Pre-fetch all markets in this batch
            market_ids = [t.market_id for t in ticks]
            markets_dict = {m.market_id: m for m in db.query(Market).filter(Market.market_id.in_(market_ids)).all()}
            
            for tick in ticks:
                self.last_latency = tick.latency_ms
                
                # ── STAGE A: CHEAP FILTER (Priority / Adaptive Polling) ──
                is_cheap_valid = tick.bid > 0 and tick.ask > 0 and tick.spread <= settings.max_spread
                
                # Update poll frequency
                if not is_cheap_valid:
                    if tick.bid == 0 and tick.ask == 0:
                        self.market_poll_times[tick.market_id] = now_time + 300 # Extremely low quality: poll every 5 min
                    else:
                        self.market_poll_times[tick.market_id] = now_time + 60 # Low quality: poll every 1 min
                else:
                    self.market_poll_times[tick.market_id] = now_time + 5 # High quality: poll frequently
                
                # Keep parent market record updated even if cheap filter fails
                market = markets_dict.get(tick.market_id)
                time_remaining = 0
                if market:
                    market.current_price = tick.price
                    market.best_bid = tick.bid
                    market.best_ask = tick.ask
                    market.spread = tick.spread
                    market.liquidity = tick.liquidity
                    market.last_update = datetime.utcnow()
                    if market.end_time:
                        time_remaining = (market.end_time - datetime.utcnow()).total_seconds()
                        
                classification = classify_snapshot(tick)
                if not classification.data_valid:
                    continue
                    
                # ── STAGE B: FULL QUANT ANALYSIS ──
                # Only execute expensive features and DB snapshots for trade eligible or sample research 
                # To preserve DB speed but keep research, we insert snapshot here (batched).
                snap = MarketSnapshot(
                    source=tick.source, symbol=tick.symbol, market_id=tick.market_id, token_id=tick.market_id,
                    event_timestamp=tick.event_timestamp, received_timestamp=tick.received_timestamp,
                    price=tick.price, bid=tick.bid, ask=tick.ask, spread=tick.spread, bid_depth=tick.bid_depth,
                    ask_depth=tick.ask_depth, imbalance=tick.imbalance, volume=tick.volume, liquidity=tick.liquidity,
                    latency_ms=tick.latency_ms, is_synthetic=False, trade_eligible=classification.trade_eligible,
                    ineligibility_reason="; ".join(classification.ineligibility_reasons) or None,
                )
                db.add(snap)
                
                if not classification.trade_eligible:
                    continue
                    
                self.feature_engine.add_tick(tick.symbol, tick.model_dump())
                features = self.feature_engine.get_features(tick.symbol, time_remaining)
                if features:
                    signal_data = self.strategy.evaluate(tick, features)
                    db.add(Signal(**signal_data))

                    self.paper_engine.update_positions(tick.market_id, tick.price)

                    sig_type = signal_data["signal_type"]
                    if settings.execution_mode == "paper" and sig_type in ("BUY", "SELL"):
                        real_condition_id = market.condition_id if market and market.condition_id else tick.market_id
                        market_info = {
                            "condition_id": real_condition_id,
                            "ask_depth": tick.ask_depth,
                            "bid_depth": tick.bid_depth
                        }
                        success, reason = self.paper_engine.execute_signal(signal_data, market_info)
                        if success:
                            from app.engine.user_engine import execute_saas_user_trades
                            execute_saas_user_trades(signal_data, market_info, tick.price)

            # Bulk commit once per batch (50 ticks)
            for attempt in range(5):
                try:
                    db.commit()
                    break
                except Exception as e:
                    db.rollback()
                    import time; time.sleep(0.5)
        except Exception as e:
            db.rollback()
            logger.error(f"Error handling tick batch: {e}")
        finally:
            db.close()

    async def process_poly_markets(self, api_markets):
        await asyncio.to_thread(self._sync_process_poly_markets, api_markets)

    def _sync_process_poly_markets(self, api_markets):
        db = SessionLocal()
        markets_discovered = 0
        try:
            for m in api_markets:
                condition_id = m.get('conditionId')
                if not condition_id:
                    continue

                clob_token_ids_str = m.get('clobTokenIds', '[]')
                outcomes_str = m.get('outcomes', '["Yes", "No"]')
                try:
                    import json
                    tokens = json.loads(clob_token_ids_str)
                    outcomes = json.loads(outcomes_str)
                except:
                    tokens = []
                    outcomes = []
                    
                if len(tokens) >= 2 and len(outcomes) >= 2:
                    end_date_str = m.get('endDate')
                    end_time = datetime.now() + timedelta(days=1)
                    if end_date_str:
                        try:
                            end_time = datetime.fromisoformat(end_date_str.replace('Z', '+00:00')).replace(tzinfo=None)
                        except:
                            pass
                            
                    # Process both tokens (YES and NO)
                    for i, token_id in enumerate(tokens[:2]):
                        token_name = outcomes[i]
                        
                        existing = db.query(Market).filter(Market.market_id == token_id).first()
                        
                        if existing:
                            existing.last_update = datetime.utcnow()
                            if datetime.utcnow() > end_time:
                                existing.active = False
                            # Retrofit condition_id if missing
                            if not existing.condition_id:
                                existing.condition_id = condition_id
                        else:
                            new_market = Market(
                                market_id=token_id,         # Instrument ID (clobTokenId)
                                condition_id=condition_id,  # Parent Market ID
                                question=m.get('question'),
                                token=token_name,
                                token_id=token_id,          # Keep in sync
                                current_price=0.0,
                                end_time=end_time,
                                active=True
                            )
                            db.add(new_market)
                    markets_discovered += 1
                    
                    if markets_discovered % 10 == 0:
                        for attempt in range(5):
                            try:
                                db.commit()
                                break
                            except Exception as e:
                                db.rollback()
                                import time; time.sleep(0.5)
            for attempt in range(5):
                try:
                    db.commit()
                    break
                except:
                    db.rollback()
                    import time; time.sleep(0.5)
            logger.info(f"[SCANNER] Markets discovered and processed: {markets_discovered}")
            self.tracked_markets_count = db.query(Market).filter(Market.active == True).count()
        except Exception as e:
            db.rollback()
            logger.error(f"DB Error in Scanner: {e}")
        finally:
            db.close()

    def get_health(self):
        tracked = getattr(self, 'tracked_markets_count', 0)
        valid_clob = getattr(self, 'last_valid_clob_count', 0)
        invalid_clob = getattr(self, 'last_invalid_clob_count', 0)
        
        poly_status = "STALE" if self.poly.check_stale() else "CONNECTED"
        if not self.poly.last_update:
            poly_status = "DISCONNECTED"
        elif poly_status == "CONNECTED" and valid_clob == 0 and tracked > 0:
            poly_status = "DEGRADED"
        
        return {
            "mode": "live",
            "active_markets": tracked,
            "poly": {
                "status": poly_status, 
                "latency": self.last_latency,
                "last_update": self.poly.last_update.isoformat() if self.poly.last_update else None,
                "valid_clob_markets": valid_clob,
                "quarantined_markets": invalid_clob
            }
        }

    async def stop(self):
        self.running = False
        await self.poly.disconnect()
        ()

# We will export a global orchestrator instance
orchestrator = Orchestrator()
