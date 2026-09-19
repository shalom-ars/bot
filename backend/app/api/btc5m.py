"""
BTC 5M API endpoints.
Provides dashboard data for the BTC 5M module.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.session import get_db
from app.db.models import BTC5MMarket, BTC5MSignal, BTC5MTrade
from app.api.security import get_current_user
from datetime import datetime, timezone, timedelta
from app.btc5m.latency import latency_tracker
import time
import httpx
import os
from app.config import settings

router = APIRouter()

_cached_btc_price = None
_cached_btc_time = 0.0

def _get_live_btc_price():
    global _cached_btc_price, _cached_btc_time
    if hasattr(btc5m_engine, '_market_states') and btc5m_engine._market_states.get("latest_btc_price"):
        return btc5m_engine._market_states["latest_btc_price"]

    now = time.time()
    if _cached_btc_price is not None and (now - _cached_btc_time) < 0.9:
        return _cached_btc_price
    
    price = None
    rpc_urls = [
        "https://polygon.drpc.org",
        "https://polygon-bor-rpc.publicnode.com",
        "https://1rpc.io/matic"
    ]
    for rpc_url in rpc_urls:
        try:
            with httpx.Client(timeout=1.2, headers={"User-Agent": "Mozilla/5.0"}) as client:
                resp = client.post(rpc_url, json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_call",
                    "params": [{"to": "0xc907E116054Ad103354f2D350FD2514433D57F6f", "data": "0x50d25bcd"}, "latest"]
                })
                if resp.status_code == 200:
                    res_json = resp.json()
                    if "result" in res_json and res_json["result"] and res_json["result"] != "0x":
                        price = int(res_json["result"], 16) / 100000000.0
                        break
        except Exception:
            continue

    if price is not None:
        _cached_btc_price = price
        _cached_btc_time = now
        return price
    return _cached_btc_price


@router.get("/markets")
def get_btc5m_markets(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """All discovered BTC 5M markets with latest CLOB data."""
    markets = db.query(BTC5MMarket).order_by(BTC5MMarket.last_seen.desc()).offset(skip).limit(limit).all()
    total = db.query(BTC5MMarket).count()
    valid = db.query(BTC5MMarket).filter(BTC5MMarket.is_valid == True).count()
    return {
        "total": total,
        "valid": valid,
        "markets": [_format_market(m) for m in markets]
    }


@router.get("/signals")
def get_btc5m_signals(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Recent BTC 5M signals with full audit trail."""
    signals = db.query(BTC5MSignal).order_by(BTC5MSignal.timestamp.desc()).offset(skip).limit(limit).all()
    total = db.query(BTC5MSignal).count()
    enters = db.query(BTC5MSignal).filter(BTC5MSignal.state == "ENTER").count()
    skips  = db.query(BTC5MSignal).filter(BTC5MSignal.state == "SKIP").count()
    return {
        "total": total,
        "enters": enters,
        "skips": skips,
        "signals": [_format_signal(s) for s in signals]
    }


@router.get("/trades")
@router.get("/trades/history")
def get_btc5m_trades(skip: int = 0, limit: int = 100, period: str = "all", instance_id: Optional[str] = None, db: Session = Depends(get_db)):
    """BTC 5M paper trades with optional weekly, monthly, and instance filtering."""
    query = db.query(BTC5MTrade)
    if instance_id:
        query = query.filter(BTC5MTrade.instance_id == instance_id)
    now = datetime.utcnow()
    
    if period == "weekly":
        since = now - timedelta(days=7)
        query = query.filter(BTC5MTrade.entry_time >= since)
    elif period == "monthly":
        since = now - timedelta(days=30)
        query = query.filter(BTC5MTrade.entry_time >= since)

    trades = query.order_by(BTC5MTrade.entry_time.desc()).offset(skip).limit(limit).all()
    total  = query.count()
    open_  = query.filter(BTC5MTrade.status == "OPEN").count()
    closed = query.filter(BTC5MTrade.status == "CLOSED").count()

    closed_trades = query.filter(BTC5MTrade.status == "CLOSED").all()
    realized_pnl = sum((t.pnl or 0) for t in closed_trades)
    wins  = sum(1 for t in closed_trades if (t.pnl or 0) > 0)
    losses = sum(1 for t in closed_trades if (t.pnl or 0) < 0)
    win_rate = (wins / len(closed_trades) * 100) if closed_trades else 0

    return {
        "period": period,
        "total": total,
        "open": open_,
        "closed": closed,
        "realized_pnl": round(realized_pnl, 4),
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2),
        "trades": [_format_trade(t) for t in trades]
    }


@router.get("/stats")
def get_btc5m_stats(instance_id: Optional[str] = None, db: Session = Depends(get_db)):
    """Summary statistics for BTC5M paper trading bot with optional instance filtering."""
    closed_query = db.query(BTC5MTrade).filter(BTC5MTrade.status == "CLOSED")
    open_query = db.query(BTC5MTrade).filter(BTC5MTrade.status == "OPEN")
    if instance_id:
        closed_query = closed_query.filter(BTC5MTrade.instance_id == instance_id)
        open_query = open_query.filter(BTC5MTrade.instance_id == instance_id)
    closed_trades = closed_query.all()
    open_trades = open_query.all()
    total_trades = len(closed_trades) + len(open_trades)
    
    realized_pnl = sum((t.pnl or 0.0) for t in closed_trades)
    wins = sum(1 for t in closed_trades if (t.pnl or 0.0) > 0)
    losses = sum(1 for t in closed_trades if (t.pnl or 0.0) < 0)
    win_rate = (wins / len(closed_trades) * 100) if closed_trades else 0.0
    
    winning_pnls = [(t.pnl or 0.0) for t in closed_trades if (t.pnl or 0.0) > 0]
    losing_pnls = [abs(t.pnl or 0.0) for t in closed_trades if (t.pnl or 0.0) < 0]
    
    avg_win = (sum(winning_pnls) / len(winning_pnls)) if winning_pnls else 0.0
    avg_loss = (sum(losing_pnls) / len(losing_pnls)) if losing_pnls else 0.0
    profit_factor = (sum(winning_pnls) / sum(losing_pnls)) if sum(losing_pnls) > 0 else (1.0 if not losing_pnls else 0.0)
    
    initial_balance = 500.0
    current_balance = initial_balance + realized_pnl
    
    return {
        "initial_balance": initial_balance,
        "current_balance": round(current_balance, 2),
        "realized_pnl": round(realized_pnl, 4),
        "total_trades": total_trades,
        "open_trades": len(open_trades),
        "closed_trades": len(closed_trades),
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2),
        "avg_winning_trade": round(avg_win, 2),
        "avg_losing_trade": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "actual_historical_rr": round(avg_win / avg_loss, 2) if avg_loss > 0 else 1.5,
        "expectancy": round((win_rate/100 * avg_win) - ((1 - win_rate/100) * avg_loss), 2)
    }


@router.post("/reset")
def reset_btc5m_state(db: Session = Depends(get_db)):
    """Completely reset all BTC5M trades, signals, price history, and risk state to $500 fresh virtual balance."""
    db.query(BTC5MTrade).delete()
    db.query(BTC5MSignal).delete()
    from app.db.models import BTC5MSkip, BTC5MPriceHistory
    db.query(BTC5MSkip).delete()
    db.query(BTC5MPriceHistory).delete()
    db.commit()

    if hasattr(btc5m_engine, '_market_states'):
        btc5m_engine._market_states.clear()
    if hasattr(btc5m_engine, 'risk_manager') and btc5m_engine.risk_manager:
        btc5m_engine.risk_manager.daily_pnl = 0.0
        btc5m_engine.risk_manager.consecutive_losses = 0
        btc5m_engine.risk_manager.current_exposure = 0.0
        btc5m_engine.risk_manager.unpause()

    _safe_broadcast()

    return {"status": "success", "message": "BTC5M state reset to $500 initial virtual capital"}


import httpx

from app.btc5m.engine import btc5m_engine, get_engine, ENGINES
from pydantic import BaseModel
from typing import Optional

def _safe_broadcast(instance_id: str = "instance_1"):
    try:
        import asyncio
        eng = get_engine(instance_id)
        loop = asyncio.get_running_loop()
        loop.create_task(eng.broadcast_status())
    except Exception:
        pass

class ToggleTradingRequest(BaseModel):
    active: bool
    instance_id: Optional[str] = "instance_1"

class AccountModeRequest(BaseModel):
    mode: str  # "demo" or "real_money"
    instance_id: Optional[str] = "instance_1"

class UpdateSettingsRequest(BaseModel):
    instance_id: Optional[str] = "instance_1"
    account_mode: Optional[str] = None
    slot_mode: Optional[str] = None
    risk_reward_ratio: Optional[str] = None
    min_entry_score: Optional[float] = None
    min_net_edge: Optional[float] = None
    min_rr: Optional[float] = None
    max_spread: Optional[float] = None
    min_liquidity: Optional[float] = None
    min_time_remaining: Optional[float] = None
    max_time_remaining: Optional[float] = None
    take_profit_delta: Optional[float] = None
    max_take_profit: Optional[float] = None
    stop_loss_ratio: Optional[float] = None
    risk_per_trade: Optional[float] = None
    trading_active: Optional[bool] = None
    mode: Optional[str] = None
    tp_dollar: Optional[float] = None
    sl_dollar: Optional[float] = None
    side_bias: Optional[str] = None
    only_short: Optional[bool] = None
    min_entry_price: Optional[float] = None
    max_entry_price: Optional[float] = None
    min_p2b_diff: Optional[float] = None
    min_entry_probability: Optional[float] = None
    rsi_period: Optional[int] = None
    rsi_overbought: Optional[float] = None
    rsi_oversold: Optional[float] = None
    macd_fast: Optional[int] = None
    macd_slow: Optional[int] = None
    macd_signal: Optional[int] = None
    bb_period: Optional[int] = None
    bb_std: Optional[float] = None

@router.get("/instances")
def get_btc5m_instances():
    """List all registered BTC 5M bot instances with operational state."""
    return {
        "status": "success",
        "instances": [
            {
                "instance_id": eng.instance_id,
                "name": eng.name,
                "mode": eng.mode,
                "slot_mode": getattr(eng, "slot_mode", "single_5m"),
                "only_short": eng.only_short,
                "tp_dollar": eng.tp_dollar,
                "sl_dollar": eng.sl_dollar,
                "trading_active": eng.trading_active
            }
            for eng in ENGINES.values()
        ]
    }


@router.get("/settings")
def get_btc5m_targeting_settings(instance_id: str = "instance_1", db: Session = Depends(get_db)):
    """Retrieve current persistent targeting settings and bot status for instance."""
    from app.btc5m.settings_manager import get_btc5m_settings
    eng = get_engine(instance_id)
    settings_data = get_btc5m_settings(db, instance_id=instance_id)
    settings_data["trading_active"] = eng.trading_active
    return {
        "status": "success",
        "instance_id": instance_id,
        "settings": settings_data
    }

@router.post("/settings")
def update_btc5m_targeting_settings(req: UpdateSettingsRequest, db: Session = Depends(get_db)):
    """Update targeting settings and persist them to SQLite across restarts."""
    from app.btc5m.settings_manager import update_btc5m_settings
    inst_id = req.instance_id or "instance_1"
    eng = get_engine(inst_id)
    updates = {k: v for k, v in req.dict().items() if v is not None and k != "instance_id"}
    if not updates:
        return {"status": "error", "message": "No valid settings fields provided"}
    
    updated = update_btc5m_settings(db, updates, user_info=f"API_{inst_id}", instance_id=inst_id)
    if hasattr(eng, 'strategy') and eng.strategy:
        eng.strategy.settings = updated
        eng.strategy._sync_instance_params()
    if "trading_active" in updates:
        eng.trading_active = bool(updates["trading_active"])
        
    _safe_broadcast(inst_id)

    return {
        "status": "success",
        "instance_id": inst_id,
        "message": f"Targeting settings for {inst_id} updated and persisted successfully",
        "settings": updated
    }

@router.post("/toggle_trading")
def toggle_trading(req: ToggleTradingRequest, db: Session = Depends(get_db)):
    inst_id = req.instance_id or "instance_1"
    eng = get_engine(inst_id)
    eng.trading_active = req.active
    
    # Persist in btc5m_settings so it survives reboots
    from app.btc5m.settings_manager import update_btc5m_settings
    update_btc5m_settings(db, {"trading_active": req.active}, user_info=f"UI_TOGGLE_{inst_id}", instance_id=inst_id)
    
    # Force engine to clear cached markets if starting fresh
    if req.active:
        if hasattr(eng, '_market_states'):
            eng._market_states.clear()
        if hasattr(eng, 'risk_manager') and eng.risk_manager:
            eng.risk_manager.unpause()
        
    from app.db.models import BTC5MAudit
    audit = BTC5MAudit(
        action="START" if req.active else "STOP",
        details=f"Bot {inst_id} started manually via UI" if req.active else f"Bot {inst_id} stopped manually via UI"
    )
    db.add(audit)
    db.commit()
    
    _safe_broadcast(inst_id)

    return {"status": "success", "instance_id": inst_id, "trading_active": eng.trading_active}

@router.get("/account_mode")
def get_account_mode(instance_id: str = "instance_1", db: Session = Depends(get_db)):
    from app.btc5m.settings_manager import get_btc5m_settings
    settings_map = get_btc5m_settings(db, instance_id=instance_id)
    eng = get_engine(instance_id)
    has_credentials = bool(
        getattr(settings, "polymarket_api_key", None) or 
        os.environ.get("POLYMARKET_API_KEY") or
        os.environ.get("POLYGON_WALLET_PRIVATE_KEY")
    )
    acc_mode = settings_map.get("account_mode", "demo")
    return {
        "status": "success",
        "instance_id": instance_id,
        "account_mode": acc_mode,
        "execution_mode": "live" if acc_mode == "real_money" else "paper",
        "has_credentials": has_credentials,
        "virtual_equity": round(eng.risk_manager.current_balance, 2) if (eng and eng.risk_manager) else 500.0,
        "is_armed": has_credentials if acc_mode == "real_money" else False
    }

@router.post("/account_mode")
def set_account_mode(req: AccountModeRequest, db: Session = Depends(get_db)):
    target_mode = "real_money" if req.mode.lower() in ("real_money", "real", "live") else "demo"
    from app.btc5m.settings_manager import update_btc5m_settings
    inst_id = req.instance_id or "instance_1"
    update_btc5m_settings(db, {"account_mode": target_mode}, user_info=f"UI_TOGGLE_ACCOUNT_{inst_id}", instance_id=inst_id)
    eng = get_engine(inst_id)
    if eng and eng.strategy:
        eng.strategy.rehydrate_settings()
    has_credentials = bool(
        getattr(settings, "polymarket_api_key", None) or 
        os.environ.get("POLYMARKET_API_KEY") or
        os.environ.get("POLYGON_WALLET_PRIVATE_KEY")
    )
    _safe_broadcast(inst_id)
    return {
        "status": "success",
        "instance_id": inst_id,
        "account_mode": target_mode,
        "execution_mode": "live" if target_mode == "real_money" else "paper",
        "has_credentials": has_credentials,
        "warning": None if (has_credentials or target_mode == "demo") else "Live trading credentials not configured in environment. System remains in safe paper fallback."
    }

@router.post("/reset_history")
def reset_trading_history(db: Session = Depends(get_db)):
    """
    Completely resets all BTC5M trading history across all instances:
    - Deletes all trades, signals, price history, skips, exit audits, and audits.
    - Reinitializes virtual balance/equity to exactly $500.00 in RiskManager.
    - Clears in-memory active positions.
    - Broadcasts clean state to all connected WebSocket clients.
    """
    from app.db.models import (
        BTC5MTrade, BTC5MSignal, BTC5MPriceHistory, BTC5MSkip, BTC5MExitAudit, BTC5MAudit, BTC5MSetting
    )
    try:
        db.query(BTC5MTrade).delete()
        db.query(BTC5MSignal).delete()
        db.query(BTC5MPriceHistory).delete()
        db.query(BTC5MSkip).delete()
        db.query(BTC5MExitAudit).delete()
        db.query(BTC5MAudit).delete()
        db.query(BTC5MSetting).delete()
        db.commit()

        # Reset RiskManager balance to $500.00 for active engine and rehydrate defaults
        for eng in ENGINES.values():
            if eng and eng.risk_manager:
                eng.risk_manager.starting_balance = 500.0
                eng.risk_manager.current_balance = 500.0
                eng.risk_manager.peak_balance = 500.0
                eng.risk_manager.daily_pnl = 0.0
                eng.risk_manager.consecutive_losses = 0
                eng.risk_manager.current_exposure = 0.0
                eng.risk_manager.open_positions_count = 0
                eng.risk_manager.is_paused = False
                eng.risk_manager.pause_reason = "Allowed"
            if eng and eng.strategy:
                eng.strategy._active_positions.clear()
                eng.strategy.rehydrate_settings()

        _safe_broadcast("instance_1")

        return {
            "status": "success",
            "message": "All trading history reset. Virtual equity reset to $500.00 for all instances.",
            "virtual_equity": 500.0
        }
    except Exception as exc:
        db.rollback()
        logger.error(f"Error resetting history: {exc}", exc_info=True)
        return {"status": "error", "message": str(exc)}


@router.post("/close_trade")
def close_btc5m_trade(instance_id: str = "instance_1", db: Session = Depends(get_db)):
    """Manually terminate currently open BTC 5M paper trade immediately at the current market price for the specified bot instance."""
    eng = get_engine(instance_id)
    trade = db.query(BTC5MTrade).filter(
        BTC5MTrade.status == "OPEN",
        BTC5MTrade.instance_id == instance_id
    ).first()
    if not trade:
        return {"status": "error", "message": f"No active trade found to close for {instance_id}"}

    # Fetch latest available execution price for the trade's side
    market = db.query(BTC5MMarket).filter(BTC5MMarket.market_id == trade.market_id).first()
    best_bid = None
    if market:
        if trade.side == "BUY" and market.best_bid is not None:
            best_bid = market.best_bid
        elif trade.side == "SELL" and market.best_ask is not None:
            best_bid = 1.0 - market.best_ask
        elif market.best_bid is not None:
            best_bid = market.best_bid

    if best_bid is None:
        from app.db.models import BTC5MPriceHistory
        last_hist = db.query(BTC5MPriceHistory).filter(
            BTC5MPriceHistory.market_id == trade.market_id
        ).order_by(BTC5MPriceHistory.timestamp.desc()).first()
        if last_hist:
            if trade.side == "BUY" and last_hist.best_bid is not None:
                best_bid = last_hist.best_bid
            elif trade.side == "SELL" and last_hist.best_ask is not None:
                best_bid = 1.0 - last_hist.best_ask

    # Fallback to entry_price if no orderbook depth exists
    exit_price = best_bid if best_bid is not None else trade.entry_price
    pnl = (exit_price - trade.entry_price) * trade.quantity

    trade.status = "CLOSED"
    trade.exit_price = round(exit_price, 4)
    trade.exit_time = datetime.utcnow()
    trade.exit_reason = "MANUAL_CLOSE"
    trade.resolution = "MANUAL"
    trade.pnl = round(pnl, 4)

    # Release engine strategy state and risk manager exposure
    if hasattr(eng, 'strategy') and eng.strategy:
        eng.strategy.record_exit(trade.market_id)
    if hasattr(eng, 'risk_manager') and eng.risk_manager:
        eng.risk_manager.record_trade_result(trade.pnl)
        eng.risk_manager.current_exposure = max(0.0, eng.risk_manager.current_exposure - trade.position_size)

    from app.db.models import BTC5MAudit
    audit = BTC5MAudit(
        action="MANUAL_CLOSE",
        details=f"Trade {trade.id} ({trade.side} {trade.locked_predicted_side}) on {instance_id} closed manually at ${exit_price:.4f} with PnL: ${pnl:.4f}"
    )
    db.add(audit)
    db.commit()
    db.refresh(trade)

    _safe_broadcast(instance_id)

    return {
        "status": "success",
        "message": f"Trade {trade.id} closed manually at ${exit_price:.4f}",
        "trade": _format_trade(trade)
    }

def build_btc5m_status_payload(db: Session, instance_id: str = "instance_1") -> dict:
    """Builds the comprehensive real-time status payload used by REST and WebSockets for a specific bot instance."""
    now = datetime.now(timezone.utc)
    # Since DB timestamps might be naive UTC, strip tzinfo for comparison
    now_naive = now.replace(tzinfo=None)

    eng = get_engine(instance_id)

    current_market = db.query(BTC5MMarket).filter(
        BTC5MMarket.start_time <= now_naive,
        BTC5MMarket.end_time > now_naive
    ).order_by(BTC5MMarket.start_time.desc()).first()

    next_market = db.query(BTC5MMarket).filter(
        BTC5MMarket.start_time > now_naive
    ).order_by(BTC5MMarket.start_time.asc()).first()

    open_trade = db.query(BTC5MTrade).filter(
        BTC5MTrade.status == "OPEN",
        BTC5MTrade.instance_id == instance_id
    ).first()
    
    open_trade_dict = _format_trade(open_trade) if open_trade else None
    if open_trade_dict:
        trade_market = db.query(BTC5MMarket).filter(BTC5MMarket.market_id == open_trade.market_id).first()
        if trade_market:
            best_bid = trade_market.best_bid
            best_ask = trade_market.best_ask
            
            # If the market expired, Polymarket might drop the book to 0 or spread 1.0. Fallback to last known price history.
            if best_bid is None or best_ask is None or (best_ask - best_bid) > 0.5:
                from app.db.models import BTC5MPriceHistory
                last_hist = db.query(BTC5MPriceHistory).filter(
                    BTC5MPriceHistory.market_id == open_trade.market_id,
                    (BTC5MPriceHistory.best_ask - BTC5MPriceHistory.best_bid) < 0.5
                ).order_by(BTC5MPriceHistory.timestamp.desc()).first()
                if last_hist:
                    best_bid = last_hist.best_bid
                    best_ask = last_hist.best_ask
                else:
                    best_bid = None
                    best_ask = None

            if best_bid is not None and best_ask is not None and (best_ask - best_bid) <= 0.5:
                if open_trade.side == "BUY":
                    current_price = best_bid
                else:
                    current_price = 1.0 - best_ask
                
                unrealized_pnl = (current_price - open_trade.entry_price) * open_trade.quantity
                open_trade_dict["current_price"] = current_price
                open_trade_dict["unrealized_pnl"] = unrealized_pnl
                open_trade_dict["pnl_pct"] = (unrealized_pnl / open_trade.position_size) * 100 if open_trade.position_size > 0 else 0
            else:
                open_trade_dict["current_price"] = None
                open_trade_dict["unrealized_pnl"] = None
                open_trade_dict["pnl_pct"] = None

        # Smart Exit Confirmation Countdown
        if open_trade.exit_decision_state == "EXIT_REVIEW" and open_trade.exit_review_started_at:
            rev_start = open_trade.exit_review_started_at
            if rev_start.tzinfo is None:
                rev_start = rev_start.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - rev_start).total_seconds()
            conf_total = 10.0
            if hasattr(eng, "settings") and isinstance(eng.settings, dict):
                conf_total = float(eng.settings.get("soft_stop_confirmation_seconds", 10.0))
            open_trade_dict["confirmation_seconds_elapsed"] = round(max(0.0, elapsed), 1)
            open_trade_dict["confirmation_seconds_total"] = conf_total
            open_trade_dict["confirmation_seconds_remaining"] = round(max(0.0, conf_total - elapsed), 1)
        else:
            open_trade_dict["confirmation_seconds_elapsed"] = 0.0
            open_trade_dict["confirmation_seconds_total"] = 10.0
            open_trade_dict["confirmation_seconds_remaining"] = 0.0

    btc_price = _get_live_btc_price()

    price_to_beat = None
    if current_market:
        cache_key = f"p2b_{current_market.market_id}"
        if hasattr(eng, '_market_states') and cache_key in eng._market_states:
            price_to_beat = eng._market_states[cache_key]
        elif hasattr(btc5m_engine, '_market_states') and cache_key in btc5m_engine._market_states:
            price_to_beat = btc5m_engine._market_states[cache_key]

    # Get latest signal scores for current market scoped to instance
    yes_score = 0
    no_score = 0
    latest_sig = None
    if current_market:
        latest_sig = db.query(BTC5MSignal).filter(
            BTC5MSignal.market_id == current_market.market_id,
            BTC5MSignal.instance_id == instance_id
        ).order_by(BTC5MSignal.timestamp.desc()).first()
    if not latest_sig and next_market:
        latest_sig = db.query(BTC5MSignal).filter(
            BTC5MSignal.market_id == next_market.market_id,
            BTC5MSignal.instance_id == instance_id
        ).order_by(BTC5MSignal.timestamp.desc()).first()

    if latest_sig:
        yes_score = getattr(latest_sig, "yes_score", None)
        no_score = getattr(latest_sig, "no_score", None)
        
        # If signal scores are missing or null, fallback to btc5m_skips
        if yes_score is None or no_score is None:
            from app.db.models import BTC5MSkip
            skip_rec = db.query(BTC5MSkip).filter(BTC5MSkip.market_id == latest_sig.market_id).order_by(BTC5MSkip.timestamp.desc()).first()
            if skip_rec:
                yes_score = skip_rec.yes_score or 0.0
                no_score = skip_rec.no_score or 0.0
                if not getattr(latest_sig, "yes_prob", None):
                    setattr(latest_sig, "yes_prob", skip_rec.yes_prob)
                if not getattr(latest_sig, "no_prob", None):
                    setattr(latest_sig, "no_prob", skip_rec.no_prob)
                if not getattr(latest_sig, "predicted_side", None):
                    setattr(latest_sig, "predicted_side", skip_rec.predicted_side)
                if not getattr(latest_sig, "gate_results", None):
                    setattr(latest_sig, "gate_results", skip_rec.gate_results)
                if not getattr(latest_sig, "yes_breakdown", None):
                    setattr(latest_sig, "yes_breakdown", skip_rec.yes_breakdown)
                if not getattr(latest_sig, "no_breakdown", None):
                    setattr(latest_sig, "no_breakdown", skip_rec.no_breakdown)
        yes_score = yes_score or 0.0
        no_score = no_score or 0.0

    analysis = None
    if latest_sig:
        analysis = {
            "state": latest_sig.state,
            "reason": latest_sig.reason,
            "fair_probability": latest_sig.fair_probability,
            "net_edge": latest_sig.net_edge,
            "momentum": getattr(latest_sig, "momentum", None),
            "volatility": getattr(latest_sig, "volatility", None),
            "yes_score": yes_score,
            "no_score": no_score,
            "yes_prob": getattr(latest_sig, "yes_prob", None),
            "no_prob": getattr(latest_sig, "no_prob", None),
            "side": getattr(latest_sig, "side", "NONE"),
            "predicted_side": getattr(latest_sig, "predicted_side", "NONE"),
            "gate_results": getattr(latest_sig, "gate_results", "{}"),
            "yes_breakdown": getattr(latest_sig, "yes_breakdown", "{}"),
            "no_breakdown": getattr(latest_sig, "no_breakdown", "{}")
        }

    live_market_analysis = analysis.copy() if analysis else None

    latency_summary = latency_tracker.get_summary()
    is_degraded = latency_tracker.is_degraded()

    health = {
        "backend": "HEALTHY",
        "btc5m_engine": "RUNNING" if getattr(eng, "running", False) else "STOPPED",
        "clob": "CONNECTED" if current_market and current_market.best_bid is not None else "DISCONNECTED",
        "chainlink": "FRESH" if btc_price is not None else "STALE",
        "database": "HEALTHY",
        "p2b": "VALID" if price_to_beat is not None else "MISSING",
        "latency_status": "DEGRADED" if is_degraded else "NORMAL",
    }

    t_rem = current_market.time_remaining_sec if (current_market and current_market.time_remaining_sec is not None) else 300.0
    current_slot = 1 if t_rem > 150.0 else 2
    settings_map = (lambda: __import__('app.btc5m.settings_manager', fromlist=['get_btc5m_settings']).get_btc5m_settings(db, instance_id=instance_id))()
    account_mode = settings_map.get("account_mode", "demo")
    slot_mode = getattr(eng, "slot_mode", settings_map.get("slot_mode", "single_5m"))
    virtual_equity = round(eng.risk_manager.current_balance, 2) if (eng and eng.risk_manager) else 500.0

    return {
        "instance_id": instance_id,
        "instance_name": eng.name,
        "mode": eng.mode,
        "slot_mode": slot_mode,
        "current_slot": current_slot,
        "slot_time_remaining": round(t_rem - 150.0 if current_slot == 1 else t_rem, 1),
        "account_mode": account_mode,
        "risk_reward_ratio": settings_map.get("risk_reward_ratio", "1:2"),
        "virtual_equity": virtual_equity,
        "only_short": eng.only_short,
        "tp_dollar": eng.tp_dollar,
        "sl_dollar": eng.sl_dollar,
        "trading_active": eng.trading_active,
        "health": health,
        "latency": latency_summary,
        "current_market": _format_market(current_market) if current_market else None,
        "next_market": _format_market(next_market) if next_market else None,
        "open_trade": open_trade_dict,
        "active_trade": open_trade_dict,
        "chainlink_btc_usd": btc_price,
        "price_to_beat": price_to_beat,
        "direction": "UP" if btc_price and price_to_beat and btc_price > price_to_beat else ("DOWN" if btc_price and price_to_beat and btc_price < price_to_beat else "NEUTRAL"),
        "yes_score": yes_score,
        "no_score": no_score,
        "latest_signal": latest_sig.state if latest_sig else None,
        "analysis": analysis,
        "live_market_analysis": live_market_analysis,
        "targeting_settings": settings_map
    }


@router.get("/status")
def get_btc5m_status(instance_id: str = "instance_1", db: Session = Depends(get_db)):
    """Returns the current market, next market, and active trade for specified instance."""
    return build_btc5m_status_payload(db, instance_id=instance_id)


@router.get("/skips")
def get_btc5m_skips(db: Session = Depends(get_db), limit: int = 50):
    from app.db.models import BTC5MSkip
    skips = db.query(BTC5MSkip).order_by(BTC5MSkip.timestamp.desc()).limit(limit).all()
    return [{"id": s.id, "market_id": s.market_id, "question": s.question, "yes_score": s.yes_score, "no_score": s.no_score, "net_edge": s.net_edge, "spread": s.spread, "liquidity": s.liquidity, "time_remaining": s.time_remaining, "planned_rr": s.planned_rr, "skip_reason": s.skip_reason, "timestamp": s.timestamp.isoformat() if s.timestamp else None, "actual_resolution": s.actual_resolution, "hypothetical_outcome": s.hypothetical_outcome} for s in skips]

@router.get("/stats")
def get_btc5m_stats(db: Session = Depends(get_db)):
    """BTC 5M strategy performance statistics."""
    total_markets   = db.query(BTC5MMarket).count()
    valid_markets   = db.query(BTC5MMarket).filter(BTC5MMarket.is_valid == True).count()
    total_signals   = db.query(BTC5MSignal).count()
    enter_signals   = db.query(BTC5MSignal).filter(BTC5MSignal.state == "ENTER").count()
    skip_signals    = db.query(BTC5MSignal).filter(BTC5MSignal.state == "SKIP").count()
    from app.db.models import BTC5MSkip
    total_skips = db.query(BTC5MSkip).count()
    hypothetical_wins = db.query(BTC5MSkip).filter(BTC5MSkip.hypothetical_outcome == "WIN").count()
    hypothetical_losses = db.query(BTC5MSkip).filter(BTC5MSkip.hypothetical_outcome == "LOSS").count()
    
    total_trades    = db.query(BTC5MTrade).count()
    open_trades     = db.query(BTC5MTrade).filter(BTC5MTrade.status == "OPEN").count()
    closed_trades_q = db.query(BTC5MTrade).filter(BTC5MTrade.status == "CLOSED").all()
    realized_pnl    = sum((t.pnl or 0) for t in closed_trades_q)
    wins            = sum(1 for t in closed_trades_q if (t.pnl or 0) > 0)
    losses          = sum(1 for t in closed_trades_q if (t.pnl or 0) < 0)
    win_rate        = (wins / len(closed_trades_q) * 100) if closed_trades_q else 0
    
    # Calculate R:R
    winning_trades = [t for t in closed_trades_q if (t.pnl or 0) > 0]
    losing_trades = [t for t in closed_trades_q if (t.pnl or 0) < 0]
    avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0
    avg_loss = sum(abs(t.pnl) for t in losing_trades) / len(losing_trades) if losing_trades else 0
    historical_rr = avg_win / avg_loss if avg_loss > 0 else 0
    profit_factor = sum(t.pnl for t in winning_trades) / sum(abs(t.pnl) for t in losing_trades) if losing_trades else 0
    expectancy = (win_rate/100 * avg_win) - ((1 - win_rate/100) * avg_loss)

    # Avg net edge from signals
    enter_sigs = db.query(BTC5MSignal).filter(BTC5MSignal.state == "ENTER").all()
    avg_net_edge = sum(s.net_edge or 0 for s in enter_sigs) / len(enter_sigs) if enter_sigs else 0
    avg_spread   = sum(s.spread or 0 for s in enter_sigs) / len(enter_sigs) if enter_sigs else 0
    avg_slippage = sum(s.slippage_cost or 0 for s in enter_sigs) / len(enter_sigs) if enter_sigs else 0

    # Last activity
    last_signal = db.query(BTC5MSignal).order_by(BTC5MSignal.timestamp.desc()).first()

    return {
        "module": "BTC_5M",
        "data_source": "Polymarket CLOB (live only, no synthetic data)",
        "execution_mode": "paper",
        "live_trading_enabled": False,
        "total_markets_analyzed": total_markets,
        "valid_markets": valid_markets,
        "total_signals": total_signals,
        "enter_signals": enter_signals,
        "skip_signals": skip_signals,
        "total_trades": total_trades,
        "open_trades": open_trades,
        "closed_trades": len(closed_trades_q),
        "total_skips_recorded": total_skips,
        "hypothetical_skip_wins": hypothetical_wins,
        "hypothetical_skip_losses": hypothetical_losses,
        "realized_pnl": round(realized_pnl, 4),
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2),
        "avg_winning_trade": round(avg_win, 2),
        "avg_losing_trade": round(avg_loss, 2),
        "actual_historical_rr": round(historical_rr, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy": round(expectancy, 2),
        "avg_net_edge": round(avg_net_edge, 4),
        "avg_spread": round(avg_spread, 4),
        "avg_slippage": round(avg_slippage, 4),
        "last_signal_at": last_signal.timestamp.isoformat() if last_signal else None,
        "strategy_params": {
            "min_momentum": 0.01,
            "min_imbalance": 0.05,
            "max_volatility": 0.08,
            "max_spread": 0.05,
            "min_depth_usd": 50.0,
            "min_liquidity_usd": 100.0,
            "min_time_remaining_sec": 60,
            "min_net_edge": 0.015,
            "min_rr": 1.5,
            "min_entry_score": 60.0,
            "risk_per_trade_pct": 2.0,
            "model_version": "rule_based_btc5m",
        }
    }


def _format_market(m: BTC5MMarket) -> dict:
    now = datetime.now(timezone.utc)
    end = m.end_time.replace(tzinfo=timezone.utc) if m.end_time and m.end_time.tzinfo is None else m.end_time
    remaining = (end - now).total_seconds() if end else None
    return {
        "market_id": m.market_id,
        "condition_id": m.condition_id,
        "question": m.question,
        "yes_token_id": m.yes_token_id,
        "no_token_id": m.no_token_id,
        "end_time": m.end_time.isoformat() if m.end_time else None,
        "start_time": m.start_time.isoformat() if m.start_time else None,
        "time_remaining_sec": remaining,
        "best_bid": m.best_bid,
        "best_ask": m.best_ask,
        "bid_depth": m.bid_depth,
        "ask_depth": m.ask_depth,
        "spread": m.spread,
        "spread_pct": round((m.spread / m.best_ask * 100), 2) if m.best_ask and m.spread else None,
        "mid_price": m.mid_price,
        "imbalance": m.imbalance,
        "liquidity": m.liquidity,
        "orderbook_timestamp": m.orderbook_timestamp.isoformat() if m.orderbook_timestamp else None,
        "is_valid": m.is_valid,
        "rejection_reason": m.rejection_reason,
        "last_seen": m.last_seen.isoformat() if m.last_seen else None,
    }


def _format_signal(s: BTC5MSignal) -> dict:
    return {
        "id": s.id,
        "market_id": s.market_id,
        "question": s.question,
        "timestamp": s.timestamp.isoformat() if s.timestamp else None,
        "state": s.state,
        "side": s.side,
        "entry_price": s.entry_price,
        "bid": s.bid,
        "ask": s.ask,
        "spread": s.spread,
        "bid_depth": s.bid_depth,
        "ask_depth": s.ask_depth,
        "momentum": s.momentum,
        "imbalance": s.imbalance,
        "ob_pressure": s.ob_pressure,
        "volatility": s.volatility,
        "momentum_persistence": s.momentum_persistence,
        "market_probability": s.market_probability,
        "fair_probability": s.fair_probability,
        "raw_edge": s.raw_edge,
        "spread_cost": s.spread_cost,
        "slippage_cost": s.slippage_cost,
        "fees": s.fees,
        "net_edge": s.net_edge,
        "risk_pct": s.risk_pct,
        "position_size": s.position_size,
        "time_remaining_sec": s.time_remaining_sec,
        "model_version": s.model_version,
        "strategy": s.strategy,
        "reason": s.reason,
    }


def _format_trade(t: BTC5MTrade) -> dict:
    return {
        "id": t.id,
        "market_id": t.market_id,
        "question": t.question,
        "side": t.side,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "quantity": t.quantity,
        "position_size": t.position_size,
        "spread_at_entry": t.spread_at_entry,
        "momentum_at_entry": t.momentum_at_entry,
        "imbalance_at_entry": t.imbalance_at_entry,
        "time_remaining_at_entry": t.time_remaining_at_entry,
        "net_edge": t.net_edge,
        "planned_risk": t.planned_risk,
        "planned_reward": t.planned_reward,
        "planned_rr": t.planned_rr,
        "actual_rr": getattr(t, 'actual_rr', None),
        "stop_loss_price": t.stop_loss_price,
        "take_profit_price": t.take_profit_price,
        "strategy": t.strategy,
        "model_version": t.model_version,
        "entry_reason": t.entry_reason,
        "exit_reason": t.exit_reason,
        "status": t.status,
        "entry_time": t.entry_time.isoformat() if t.entry_time else None,
        "exit_time": t.exit_time.isoformat() if t.exit_time else None,
        "pnl": t.pnl,
        "resolution": t.resolution,
        # Immutable locked thesis fields
        "locked_predicted_side": getattr(t, "locked_predicted_side", None) or ("YES" if t.side == "BUY" else "NO"),
        "locked_direction": getattr(t, "locked_direction", None) or ("UP" if t.side == "BUY" else "DOWN"),
        "locked_outcome": getattr(t, "locked_outcome", None) or ("YES" if t.side == "BUY" else "NO"),
        "locked_token_id": getattr(t, "locked_token_id", None),
        "execution_side": getattr(t, "execution_side", None) or t.side,
        "entry_yes_score": getattr(t, "entry_yes_score", None),
        "entry_no_score": getattr(t, "entry_no_score", None),
        "entry_fair_probability": getattr(t, "entry_fair_probability", None),
        "entry_market_probability": getattr(t, "entry_market_probability", None),
        "entry_net_edge": getattr(t, "entry_net_edge", None) or t.net_edge,
        "entry_planned_rr": getattr(t, "entry_planned_rr", None) or t.planned_rr,
        "entry_stop_price": getattr(t, "entry_stop_price", None) or t.stop_loss_price,
        "prediction_locked_at": t.prediction_locked_at.isoformat() if getattr(t, "prediction_locked_at", None) else (t.entry_time.isoformat() if t.entry_time else None),
        "prediction_lock_version": getattr(t, "prediction_lock_version", 1),
        "is_thesis_locked": True,
        # Smart Exit System Fields
        "exit_decision_state": getattr(t, "exit_decision_state", "HOLD") or "HOLD",
        "soft_stop_touched_at": t.soft_stop_touched_at.isoformat() if getattr(t, "soft_stop_touched_at", None) else None,
        "exit_review_started_at": t.exit_review_started_at.isoformat() if getattr(t, "exit_review_started_at", None) else None,
        "last_exit_review_reason": getattr(t, "last_exit_review_reason", None),
        "thesis_failure_score": getattr(t, "thesis_failure_score", None),
        "hard_stop_price": getattr(t, "hard_stop_price", None),
    }

@router.get("/exit_audits")
def get_btc5m_exit_audits(instance_id: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)):
    """Recent smart exit audit records for transparency and forensics."""
    from app.db.models import BTC5MExitAudit
    query = db.query(BTC5MExitAudit)
    if instance_id:
        query = query.filter(BTC5MExitAudit.instance_id == instance_id)
    audits = query.order_by(BTC5MExitAudit.timestamp.desc()).limit(limit).all()
    return {
        "status": "success",
        "total": len(audits),
        "audits": [
            {
                "id": a.id,
                "trade_id": a.trade_id,
                "instance_id": a.instance_id,
                "market_id": a.market_id,
                "event_type": a.event_type,
                "timestamp": a.timestamp.isoformat() if a.timestamp else None,
                "locked_predicted_side": a.locked_predicted_side,
                "current_live_prediction": a.current_live_prediction,
                "btc_price": a.btc_price,
                "p2b": a.p2b,
                "delta": a.delta,
                "momentum": a.momentum,
                "probability": a.probability,
                "orderbook_imbalance": a.orderbook_imbalance,
                "volatility": a.volatility,
                "remaining_time": a.remaining_time,
                "entry_price": a.entry_price,
                "current_price": a.current_price,
                "unrealized_pnl": a.unrealized_pnl,
                "original_stop": a.original_stop,
                "hard_stop": a.hard_stop,
                "current_exit_decision": a.current_exit_decision,
                "thesis_failure_score": a.thesis_failure_score,
                "reason": a.reason,
                "details": a.details_json
            }
            for a in audits
        ]
    }

@router.get("/chart")
def get_btc5m_chart(market_id: str, db: Session = Depends(get_db)):
    from app.db.models import BTC5MPriceHistory
    history = db.query(BTC5MPriceHistory).filter(
        BTC5MPriceHistory.market_id == market_id
    ).order_by(BTC5MPriceHistory.timestamp.asc()).all()
    
    data = []
    for h in history:
        data.append({
            "time": h.timestamp.isoformat(),
            "yes_bid": h.best_bid,
            "yes_ask": h.best_ask
        })
    return {"history": data}


@router.get("/candles")
def get_btc_candles(limit: int = 30):
    """Returns real-time 1-minute BTC OHLCV candles."""
    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.get(f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit={limit}")
            if resp.status_code == 200:
                raw = resp.json()
                candles = []
                for k in raw:
                    candles.append({
                        "timestamp": k[0],
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5])
                    })
                return {"candles": candles}
    except Exception:
        pass
    return {"candles": []}

