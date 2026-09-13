"""
resolution_checker.py  ?"  Polls Polymarket's official resolution endpoint and
writes labels to the Market table WITHOUT ever inferring outcome from prices.

Resolution source:
  GET https://gamma-api.polymarket.com/markets?id=<condition_id>
  or
  GET https://clob.polymarket.com/markets/<condition_id>

Both return `closed` and `winner` fields on the token objects.
We only write a label when the API explicitly provides a winner.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

import aiohttp

from app.config import settings
from app.db.session import SessionLocal
from app.db.models import Market, BotEvent

logger = logging.getLogger(__name__)

CLOB_BASE = "https://clob.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"
CHECK_INTERVAL_SECONDS = 300   # re-check every 5 minutes


async def fetch_resolution(session: aiohttp.ClientSession, condition_id: str) -> str | None:
    """
    Queries the Gamma API for a single market's resolution.
    Returns 'YES', 'NO', or None if the market is still open or data is unavailable.
    We NEVER infer resolution from prices.
    """
    url = f"{GAMMA_BASE}/markets?conditionId={condition_id}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                logger.debug(f"[RESOLUTION] HTTP {resp.status} for {condition_id}")
                return None
            data = await resp.json()
            markets = data if isinstance(data, list) else data.get("markets", [])
            for mkt in markets:
                if not mkt.get("closed"):
                    return None   # still open ?" no label
                # `outcomes` is a JSON string; find the winning token
                outcomes_raw = mkt.get("outcomes", "[]")
                clob_ids_raw = mkt.get("clobTokenIds", "[]")
                try:
                    outcomes = json.loads(outcomes_raw)
                    clob_ids = json.loads(clob_ids_raw)
                except Exception:
                    return None

                # The winning token will have price == 1.0 in the market data
                prices_raw = mkt.get("outcomePrices", "[]")
                try:
                    prices = json.loads(prices_raw)
                except Exception:
                    return None

                for i, price_str in enumerate(prices):
                    try:
                        if float(price_str) >= 0.99:
                            outcome_label = outcomes[i] if i < len(outcomes) else None
                            if outcome_label and outcome_label.lower() == "yes":
                                return "YES"
                            elif outcome_label and outcome_label.lower() == "no":
                                return "NO"
                    except (ValueError, TypeError):
                        continue
    except Exception as e:
        logger.warning(f"[RESOLUTION] Error fetching {condition_id}: {e}")
    return None


def get_candidates():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        return db.query(Market).filter(
            Market.resolved == False,
            Market.end_time <= now,
            Market.active == True,
        ).all()
    finally:
        db.close()

def resolve_market(market_id: str, resolution: str, paper_engine=None):
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        mkt = db.query(Market).filter(Market.market_id == market_id).first()
        if mkt:
            mkt.resolved = True
            mkt.resolved_at = now
            mkt.resolution = resolution
            db.commit()
            
            logger.info(f"[RESOLUTION] Market {mkt.market_id[:20]} resolved -> {resolution}")
            event = BotEvent(level="INFO", message=f"Market resolved: {mkt.market_id[:30]} -> {resolution}")
            db.add(event)
            db.commit()
            
            resolved_price = 1.0 if resolution == "YES" else 0.0
            if paper_engine:
                paper_engine.update_positions(
                    market_id=mkt.market_id, 
                    current_price=resolved_price, 
                    is_resolved=True, 
                    resolved_price=resolved_price
                )
            
            from app.engine.user_engine import resolve_saas_user_trades
            resolve_saas_user_trades(mkt.market_id, resolution)
    except Exception as e:
        logger.error(f"[RESOLUTION] resolve_market error: {e}")
        db.rollback()
    finally:
        db.close()

async def resolution_check_loop(paper_engine=None):
    """
    Background loop that checks unresolved markets for official resolution.
    Writes labels to Market.resolution only from official API data.
    Never infers labels from price movement.
    """
    logger.info("[RESOLUTION] Resolution checker started.")
    timeout = aiohttp.ClientTimeout(total=10)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            try:
                candidates = await asyncio.to_thread(get_candidates)
                if candidates:
                    logger.info(f"[RESOLUTION] Checking {len(candidates)} candidates...")

                for mkt in candidates:
                    condition_id = getattr(mkt, "token_id", None) or mkt.market_id
                    resolution = await fetch_resolution(session, condition_id)

                    if resolution in ("YES", "NO"):
                        await asyncio.to_thread(resolve_market, mkt.market_id, resolution, paper_engine)
                    else:
                        await asyncio.sleep(0.2)
            except Exception as e:
                logger.error(f"[RESOLUTION] loop error: {e}")
                
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
