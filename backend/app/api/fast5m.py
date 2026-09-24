"""
Fast 5M Fast Prediction API Router.
Exposes REST endpoints for the 7-asset real-time prediction engine and UI board.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from app.db.session import get_db
from app.db.models import Fast5MTrade
from app.fast5m.engine import fast5m_engine
from app.fast5m.executor import fast_executor

router = APIRouter()


class SettingsUpdate(BaseModel):
    auto_trading_enabled: Optional[bool] = None
    total_balance_usd: Optional[float] = None
    confidence_threshold: Optional[float] = None
    position_size_usd: Optional[float] = None
    max_active_pools: Optional[int] = None
    strategy_direction: Optional[str] = None
    take_profit_dollar: Optional[float] = None
    stop_loss_dollar: Optional[float] = None
    min_profit_to_lock: Optional[float] = None
    reversal_giveback_dollar: Optional[float] = None
    trailing_lock_enabled: Optional[bool] = None
    reversal_lock_enabled: Optional[bool] = None
    min_time_remaining: Optional[float] = None
    max_time_remaining: Optional[float] = None
    # Active Quantitative Filters & Indicator Flags
    filter_delta_enabled: Optional[bool] = None
    filter_delta_weight: Optional[float] = None
    filter_obi_enabled: Optional[bool] = None
    filter_obi_weight: Optional[float] = None
    filter_momentum_enabled: Optional[bool] = None
    filter_momentum_weight: Optional[float] = None
    filter_rsi_enabled: Optional[bool] = None
    filter_bb_enabled: Optional[bool] = None
    filter_ema_macd_enabled: Optional[bool] = None
    max_spread: Optional[float] = None
    min_liquidity_usd: Optional[float] = None
    save_as_default: Optional[bool] = None


class ManualOrderRequest(BaseModel):
    asset: str
    outcome: str # "UP" or "DOWN"
    cost: Optional[float] = 10.0


@router.get("/board")
def get_fast5m_board():
    """Retrieve full real-time board state for all 7 assets."""
    return fast5m_engine.get_board_state()


@router.get("/trades")
def get_fast5m_trades(limit: int = 50, db: Session = Depends(get_db)):
    """Retrieve historical trades and comprehensive PnL stats."""
    trades = (
        db.query(Fast5MTrade)
        .order_by(Fast5MTrade.id.desc())
        .limit(limit)
        .all()
    )
    result = []
    total_profit = 0.0
    total_loss = 0.0
    total_pnl = 0.0
    wins = 0
    losses = 0
    closed_trades = 0

    for t in trades:
        pnl_val = t.pnl or 0.0
        if t.status == "CLOSED":
            closed_trades += 1
            total_pnl += pnl_val
            if pnl_val > 0:
                total_profit += pnl_val
                wins += 1
            elif pnl_val < 0:
                total_loss += abs(pnl_val)
                losses += 1

        result.append({
            "id": t.id,
            "asset": t.asset,
            "market_id": t.market_id,
            "question": t.question,
            "epoch_bucket": t.epoch_bucket,
            "side": t.side,
            "outcome": t.outcome,
            "token_id": t.token_id,
            "entry_price": t.entry_price,
            "shares": t.shares,
            "cost": t.cost,
            "strike_price": t.strike_price,
            "entry_oracle_price": t.entry_oracle_price,
            "delta_at_entry": t.delta_at_entry,
            "confidence_score": t.confidence_score,
            "delta_score": getattr(t, "delta_score", 0.0) or 0.0,
            "obi_score": getattr(t, "obi_score", 0.0) or 0.0,
            "momentum_score": getattr(t, "momentum_score", 0.0) or 0.0,
            "prediction_rationale": getattr(t, "prediction_rationale", "") or "",
            "asset_rank": t.asset_rank,
            "latency_ms": t.latency_ms,
            "status": t.status,
            "exit_price": t.exit_price,
            "pnl": t.pnl,
            "pnl_percent": t.pnl_percent,
            "resolution": t.resolution,
            "created_at": t.created_at.isoformat() if t.created_at else "",
            "closed_at": t.closed_at.isoformat() if t.closed_at else None,
        })

    win_rate = (wins / closed_trades * 100.0) if closed_trades > 0 else 0.0

    initial_balance = float(fast_executor.settings.get("total_balance_usd", 300.0))
    current_balance = round(initial_balance + total_pnl, 2)

    return {
        "stats": {
            "initial_balance": initial_balance,
            "current_balance": current_balance,
            "total_pnl": round(total_pnl, 2),
            "total_profit": round(total_profit, 2),
            "total_loss": round(total_loss, 2),
            "win_rate": round(win_rate, 1),
            "wins": wins,
            "losses": losses,
            "total_trades": closed_trades,
            "open_trades": len([t for t in trades if t.status == "OPEN"]),
        },
        "trades": result
    }


@router.get("/settings")
def get_fast5m_settings():
    """Get active Fast 5M settings and saved custom default baseline."""
    return {
        **fast_executor.settings,
        "_defaults": fast_executor.get_default_settings()
    }


@router.post("/settings")
def update_fast5m_settings(payload: SettingsUpdate):
    """Update Fast 5M settings and optionally persist as permanent custom default baseline."""
    updates = {}
    if payload.auto_trading_enabled is not None:
        updates["auto_trading_enabled"] = "true" if payload.auto_trading_enabled else "false"
    if payload.total_balance_usd is not None:
        updates["total_balance_usd"] = str(payload.total_balance_usd)
    if payload.confidence_threshold is not None:
        updates["confidence_threshold"] = str(payload.confidence_threshold)
    if payload.position_size_usd is not None:
        updates["position_size_usd"] = str(payload.position_size_usd)
    if payload.max_active_pools is not None:
        updates["max_active_pools"] = str(payload.max_active_pools)
    if payload.strategy_direction is not None:
        updates["strategy_direction"] = str(payload.strategy_direction).upper()
    if payload.take_profit_dollar is not None:
        updates["take_profit_dollar"] = str(payload.take_profit_dollar)
    if payload.stop_loss_dollar is not None:
        updates["stop_loss_dollar"] = str(payload.stop_loss_dollar)
    if payload.min_profit_to_lock is not None:
        updates["min_profit_to_lock"] = str(payload.min_profit_to_lock)
    if payload.reversal_giveback_dollar is not None:
        updates["reversal_giveback_dollar"] = str(payload.reversal_giveback_dollar)
    if payload.trailing_lock_enabled is not None:
        updates["trailing_lock_enabled"] = "true" if payload.trailing_lock_enabled else "false"
    if payload.reversal_lock_enabled is not None:
        updates["reversal_lock_enabled"] = "true" if payload.reversal_lock_enabled else "false"
    if payload.min_time_remaining is not None:
        updates["min_time_remaining"] = str(payload.min_time_remaining)
    if payload.max_time_remaining is not None:
        updates["max_time_remaining"] = str(payload.max_time_remaining)

    # Active Filters & Indicators
    if payload.filter_delta_enabled is not None:
        updates["filter_delta_enabled"] = "true" if payload.filter_delta_enabled else "false"
    if payload.filter_delta_weight is not None:
        updates["filter_delta_weight"] = str(payload.filter_delta_weight)
    if payload.filter_obi_enabled is not None:
        updates["filter_obi_enabled"] = "true" if payload.filter_obi_enabled else "false"
    if payload.filter_obi_weight is not None:
        updates["filter_obi_weight"] = str(payload.filter_obi_weight)
    if payload.filter_momentum_enabled is not None:
        updates["filter_momentum_enabled"] = "true" if payload.filter_momentum_enabled else "false"
    if payload.filter_momentum_weight is not None:
        updates["filter_momentum_weight"] = str(payload.filter_momentum_weight)
    if payload.filter_rsi_enabled is not None:
        updates["filter_rsi_enabled"] = "true" if payload.filter_rsi_enabled else "false"
    if payload.filter_bb_enabled is not None:
        updates["filter_bb_enabled"] = "true" if payload.filter_bb_enabled else "false"
    if payload.filter_ema_macd_enabled is not None:
        updates["filter_ema_macd_enabled"] = "true" if payload.filter_ema_macd_enabled else "false"
    if payload.max_spread is not None:
        updates["max_spread"] = str(payload.max_spread)
    if payload.min_liquidity_usd is not None:
        updates["min_liquidity_usd"] = str(payload.min_liquidity_usd)

    if payload.save_as_default:
        saved_defaults = fast_executor.save_as_default(updates)
        return {
            "status": "success",
            "message": "Custom settings saved as permanent default baseline.",
            "settings": fast_executor.settings,
            "defaults": saved_defaults
        }

    fast_executor.update_settings(updates)
    return {"status": "success", "settings": fast_executor.settings}


@router.post("/settings/default")
def save_settings_as_default(payload: Optional[SettingsUpdate] = None):
    """Save current or specified settings as custom default baseline."""
    updates = {}
    if payload:
        if payload.take_profit_dollar is not None:
            updates["take_profit_dollar"] = str(payload.take_profit_dollar)
        if payload.stop_loss_dollar is not None:
            updates["stop_loss_dollar"] = str(payload.stop_loss_dollar)
        if payload.position_size_usd is not None:
            updates["position_size_usd"] = str(payload.position_size_usd)
        if payload.confidence_threshold is not None:
            updates["confidence_threshold"] = str(payload.confidence_threshold)
        if payload.max_active_pools is not None:
            updates["max_active_pools"] = str(payload.max_active_pools)
        if payload.strategy_direction is not None:
            updates["strategy_direction"] = str(payload.strategy_direction).upper()
        if payload.min_profit_to_lock is not None:
            updates["min_profit_to_lock"] = str(payload.min_profit_to_lock)
        if payload.reversal_giveback_dollar is not None:
            updates["reversal_giveback_dollar"] = str(payload.reversal_giveback_dollar)
        if payload.trailing_lock_enabled is not None:
            updates["trailing_lock_enabled"] = "true" if payload.trailing_lock_enabled else "false"
        if payload.filter_delta_enabled is not None:
            updates["filter_delta_enabled"] = "true" if payload.filter_delta_enabled else "false"
        if payload.filter_delta_weight is not None:
            updates["filter_delta_weight"] = str(payload.filter_delta_weight)
        if payload.filter_obi_enabled is not None:
            updates["filter_obi_enabled"] = "true" if payload.filter_obi_enabled else "false"
        if payload.filter_obi_weight is not None:
            updates["filter_obi_weight"] = str(payload.filter_obi_weight)
        if payload.filter_momentum_enabled is not None:
            updates["filter_momentum_enabled"] = "true" if payload.filter_momentum_enabled else "false"
        if payload.filter_momentum_weight is not None:
            updates["filter_momentum_weight"] = str(payload.filter_momentum_weight)
        if payload.filter_rsi_enabled is not None:
            updates["filter_rsi_enabled"] = "true" if payload.filter_rsi_enabled else "false"
        if payload.filter_bb_enabled is not None:
            updates["filter_bb_enabled"] = "true" if payload.filter_bb_enabled else "false"
        if payload.filter_ema_macd_enabled is not None:
            updates["filter_ema_macd_enabled"] = "true" if payload.filter_ema_macd_enabled else "false"
        if payload.max_spread is not None:
            updates["max_spread"] = str(payload.max_spread)
        if payload.min_liquidity_usd is not None:
            updates["min_liquidity_usd"] = str(payload.min_liquidity_usd)

    defaults = fast_executor.save_as_default(updates if updates else None)
    return {
        "status": "success",
        "message": "Custom configuration saved as default profile.",
        "settings": fast_executor.settings,
        "defaults": defaults
    }


@router.post("/settings/restore-defaults")
def restore_settings_defaults():
    """Restore active settings to the saved custom default baseline."""
    restored = fast_executor.restore_defaults()
    return {
        "status": "success",
        "message": "Settings restored to custom default baseline.",
        "settings": restored
    }


@router.post("/toggle")
def toggle_auto_trading():
    """Toggle auto-trading ON / PAUSED."""
    curr = fast_executor.settings.get("auto_trading_enabled", "true").lower() in ("true", "1", "yes")
    new_val = not curr
    fast_executor.update_settings({"auto_trading_enabled": "true" if new_val else "false"})
    return {"status": "success", "auto_trading_enabled": new_val}


@router.get("/system-health")
def get_system_health():
    """Retrieve real-time Squad background workers status, API health, and network speed."""
    from app.fast5m.squad import fast_squad
    return fast_squad.get_system_health()


@router.post("/system-health/test")
async def test_system_health():
    """Force an immediate network latency and API diagnostic check."""
    from app.fast5m.squad import fast_squad
    await fast_squad._measure_network_health()
    return fast_squad.get_system_health()
