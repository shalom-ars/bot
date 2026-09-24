"""
Fast 5M Fast Prediction API Router.
Exposes REST endpoints for the 7-asset real-time prediction engine and UI board.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
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
    multi_pair_min_score: Optional[float] = None
    strategy_direction: Optional[str] = None
    take_profit_dollar: Optional[float] = None
    stop_loss_dollar: Optional[float] = None
    min_profit_to_lock: Optional[float] = None
    reversal_giveback_dollar: Optional[float] = None
    trailing_lock_enabled: Optional[bool] = None
    trailing_stop_activation_pct: Optional[float] = None
    trailing_stop_distance_pct: Optional[float] = None
    max_portfolio_margin_pct: Optional[float] = None
    reversal_lock_enabled: Optional[bool] = None
    min_time_remaining: Optional[float] = None
    max_time_remaining: Optional[float] = None
    # Buffer Timer & Strict Loss Limit Parameters
    buffer_timer_sec: Optional[float] = None
    take_profit_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
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


class WalletConnectRequest(BaseModel):
    address: str
    private_key: Optional[str] = None
    proxy_address: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    api_passphrase: Optional[str] = None


class WalletModeRequest(BaseModel):
    mode: str  # 'demo' or 'live'


@router.get("/board")
def get_fast5m_board():
    """Retrieve full real-time board state for all 7 assets."""
    return fast5m_engine.get_board_state()


@router.get("/trades")
def get_fast5m_trades(
    timeframe: str = Query("all", regex="^(today|week|month|all)$"),
    account_mode: Optional[str] = Query("demo", regex="^(demo|live|all)$"),
    limit: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Retrieve historical trades and comprehensive PnL metrics with lifetime database persistence
    and dynamic timeframe filtering (today, week, month, all-time) separated by account mode (demo vs live).
    """
    now = datetime.now(timezone.utc)
    base_query = db.query(Fast5MTrade)

    if account_mode == "demo":
        base_query = base_query.filter((Fast5MTrade.account_mode == "demo") | (Fast5MTrade.account_mode.is_(None)))
    elif account_mode == "live":
        base_query = base_query.filter(Fast5MTrade.account_mode == "live")

    if timeframe == "today":
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        filtered_query = base_query.filter(Fast5MTrade.created_at >= today_start)
    elif timeframe == "week":
        week_start = now - timedelta(days=7)
        filtered_query = base_query.filter(Fast5MTrade.created_at >= week_start)
    elif timeframe == "month":
        month_start = now - timedelta(days=30)
        filtered_query = base_query.filter(Fast5MTrade.created_at >= month_start)
    else: # "all"
        filtered_query = base_query

    ordered_query = filtered_query.order_by(Fast5MTrade.id.desc())
    if limit is not None and limit > 0:
        trades = ordered_query.limit(limit).all()
    else:
        trades = ordered_query.all()

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
            "account_mode": getattr(t, "account_mode", "demo") or "demo",
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

    # Also compute all-time lifetime stats across closed records matching mode
    lifetime_q = db.query(Fast5MTrade).filter(Fast5MTrade.status == "CLOSED")
    if account_mode == "demo":
        lifetime_q = lifetime_q.filter((Fast5MTrade.account_mode == "demo") | (Fast5MTrade.account_mode.is_(None)))
    elif account_mode == "live":
        lifetime_q = lifetime_q.filter(Fast5MTrade.account_mode == "live")

    all_closed_records = lifetime_q.all()
    all_wins = sum(1 for t in all_closed_records if (t.pnl or 0) > 0)
    all_losses = sum(1 for t in all_closed_records if (t.pnl or 0) < 0)
    all_profit = sum(t.pnl for t in all_closed_records if (t.pnl or 0) > 0)
    all_loss = sum(abs(t.pnl) for t in all_closed_records if (t.pnl or 0) < 0)
    all_pnl = all_profit - all_loss
    all_closed_count = len(all_closed_records)
    all_win_rate = (all_wins / all_closed_count * 100.0) if all_closed_count > 0 else 0.0

    if account_mode == "live":
        from app.fast5m.wallet import wallet_manager
        current_balance = round(wallet_manager.total_usdc_balance, 2)
        initial_balance = round(current_balance - all_pnl, 2) if wallet_manager.is_connected else 0.0
        active_open_trades = len([t for t in fast_executor.get_active_trades() if t.get("account_mode") == "live"])
    else:
        initial_balance = float(fast_executor.settings.get("total_balance_usd", 300.0))
        current_balance = round(initial_balance + all_pnl, 2)
        active_open_trades = len([t for t in fast_executor.get_active_trades() if t.get("account_mode", "demo") == "demo"])

    return {
        "timeframe": timeframe,
        "account_mode": account_mode,
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
            "open_trades": active_open_trades,
        },
        "lifetime_stats": {
            "total_trades": all_closed_count,
            "total_profit": round(all_profit, 2),
            "total_loss": round(all_loss, 2),
            "total_pnl": round(all_pnl, 2),
            "win_rate": round(all_win_rate, 1),
            "wins": all_wins,
            "losses": all_losses,
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
    if payload.multi_pair_min_score is not None:
        updates["multi_pair_min_score"] = str(payload.multi_pair_min_score)
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
    if payload.trailing_stop_activation_pct is not None:
        updates["trailing_stop_activation_pct"] = str(payload.trailing_stop_activation_pct)
    if payload.trailing_stop_distance_pct is not None:
        updates["trailing_stop_distance_pct"] = str(payload.trailing_stop_distance_pct)
    if payload.max_portfolio_margin_pct is not None:
        updates["max_portfolio_margin_pct"] = str(payload.max_portfolio_margin_pct)
    if payload.reversal_lock_enabled is not None:
        updates["reversal_lock_enabled"] = "true" if payload.reversal_lock_enabled else "false"
    if payload.min_time_remaining is not None:
        updates["min_time_remaining"] = str(payload.min_time_remaining)
    if payload.max_time_remaining is not None:
        updates["max_time_remaining"] = str(payload.max_time_remaining)

    # Buffer Timer & Strict Loss Limit Parameters
    if payload.buffer_timer_sec is not None:
        updates["buffer_timer_sec"] = str(max(2.0, min(15.0, payload.buffer_timer_sec)))
    if payload.take_profit_pct is not None:
        updates["take_profit_pct"] = str(payload.take_profit_pct)
        pos_size = float(payload.position_size_usd or fast_executor.settings.get("position_size_usd", 10.0))
        updates["take_profit_dollar"] = str(round(pos_size * (payload.take_profit_pct / 100.0), 2))
    if payload.stop_loss_pct is not None:
        # Strictly cap at maximum 3.0% loss
        capped_sl = min(3.0, max(0.5, payload.stop_loss_pct))
        updates["stop_loss_pct"] = str(capped_sl)
        pos_size = float(payload.position_size_usd or fast_executor.settings.get("position_size_usd", 10.0))
        updates["stop_loss_dollar"] = str(round(pos_size * (capped_sl / 100.0), 2))

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
        if payload.take_profit_pct is not None:
            updates["take_profit_pct"] = str(payload.take_profit_pct)
            pos_size = float(payload.position_size_usd or fast_executor.settings.get("position_size_usd", 10.0))
            updates["take_profit_dollar"] = str(round(pos_size * (payload.take_profit_pct / 100.0), 2))
        if payload.stop_loss_pct is not None:
            capped_sl = min(3.0, max(0.5, payload.stop_loss_pct))
            updates["stop_loss_pct"] = str(capped_sl)
            pos_size = float(payload.position_size_usd or fast_executor.settings.get("position_size_usd", 10.0))
            updates["stop_loss_dollar"] = str(round(pos_size * (capped_sl / 100.0), 2))
        if payload.buffer_timer_sec is not None:
            updates["buffer_timer_sec"] = str(max(2.0, min(15.0, payload.buffer_timer_sec)))
        if payload.position_size_usd is not None:
            updates["position_size_usd"] = str(payload.position_size_usd)
        if payload.confidence_threshold is not None:
            updates["confidence_threshold"] = str(payload.confidence_threshold)
        if payload.max_active_pools is not None:
            updates["max_active_pools"] = str(payload.max_active_pools)
        if payload.multi_pair_min_score is not None:
            updates["multi_pair_min_score"] = str(payload.multi_pair_min_score)
        if payload.strategy_direction is not None:
            updates["strategy_direction"] = str(payload.strategy_direction).upper()
        if payload.min_profit_to_lock is not None:
            updates["min_profit_to_lock"] = str(payload.min_profit_to_lock)
        if payload.reversal_giveback_dollar is not None:
            updates["reversal_giveback_dollar"] = str(payload.reversal_giveback_dollar)
        if payload.trailing_lock_enabled is not None:
            updates["trailing_lock_enabled"] = "true" if payload.trailing_lock_enabled else "false"
        if payload.trailing_stop_activation_pct is not None:
            updates["trailing_stop_activation_pct"] = str(payload.trailing_stop_activation_pct)
        if payload.trailing_stop_distance_pct is not None:
            updates["trailing_stop_distance_pct"] = str(payload.trailing_stop_distance_pct)
        if payload.max_portfolio_margin_pct is not None:
            updates["max_portfolio_margin_pct"] = str(payload.max_portfolio_margin_pct)
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


@router.post("/emergency-stop")
def emergency_stop_trading():
    """
    Emergency Panic Button:
    Instantly kills auto-trading and force-closes any open active positions.
    """
    return fast_executor.emergency_stop()


@router.post("/emergency-start")
def emergency_start_trading():
    """
    Emergency Start / Resume:
    Re-arms auto-execution and resumes market scanning.
    """
    return fast_executor.emergency_start()


@router.post("/reset-demo")
def reset_demo_trading():
    """
    Reset Demo Account:
    Wipes paper trade history and resets virtual equity back to $300.00 base.
    """
    return fast_executor.reset_demo_account()



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


# ==========================================
# REAL WALLET & POLYMARKET CLOB ENDPOINTS
# ==========================================

@router.get("/wallet")
def get_fast5m_wallet():
    """Retrieve connected wallet status, Polygon on-chain balances, and CLOB configuration."""
    from app.fast5m.wallet import wallet_manager
    return wallet_manager.get_status()


@router.post("/wallet/connect")
def connect_fast5m_wallet(req: WalletConnectRequest):
    """Connect a real Polygon wallet and configure signing credentials."""
    from app.fast5m.wallet import wallet_manager
    res = wallet_manager.connect(
        address=req.address,
        private_key=req.private_key,
        proxy_address=req.proxy_address,
        api_key=req.api_key,
        api_secret=req.api_secret,
        api_passphrase=req.api_passphrase,
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to connect wallet"))
    return res


@router.post("/wallet/mode")
def set_fast5m_wallet_mode(req: WalletModeRequest):
    """Toggle between 'demo' (Virtual $300 Paper) and 'live' (Real Wallet Polymarket CLOB)."""
    from app.fast5m.wallet import wallet_manager
    res = wallet_manager.set_mode(req.mode)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to switch mode"))
    return res


@router.post("/wallet/disconnect")
def disconnect_fast5m_wallet():
    """Disconnect wallet, wipe credentials, and safely revert to demo mode."""
    from app.fast5m.wallet import wallet_manager
    return wallet_manager.disconnect()


@router.post("/wallet/refresh")
def refresh_fast5m_wallet_balances():
    """Fetch fresh on-chain Polygon USDC and POL balances."""
    from app.fast5m.wallet import wallet_manager
    balances = wallet_manager.refresh_balances()
    return {
        "status": "success",
        "balances": balances,
        "wallet": wallet_manager.get_status()
    }

