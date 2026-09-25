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
from app.db.models import Fast5MTrade, Fast5MSetting, Fast5MUserVault, Fast5MUserSetting, User
from app.api.security import get_current_user_optional
from app.fast5m.engine import fast5m_engine
from app.fast5m.executor import fast_executor

router = APIRouter()


class VaultDepositRequest(BaseModel):
    amount: float


class VaultWithdrawRequest(BaseModel):
    amount: float



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
    # Buffer Timer & Risk Parameters
    buffer_timer_sec: Optional[float] = None
    take_profit_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
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
    # Slippage Circuit Breaker on Exit
    exit_circuit_breaker_enabled: Optional[bool] = None
    max_exit_slippage_pct: Optional[float] = None
    # Dedicated Per-Asset Spread & Liquidity Thresholds
    max_spread_btc: Optional[float] = None
    min_liquidity_usd_btc: Optional[float] = None
    max_spread_eth: Optional[float] = None
    min_liquidity_usd_eth: Optional[float] = None
    max_spread_sol: Optional[float] = None
    min_liquidity_usd_sol: Optional[float] = None
    max_spread_xrp: Optional[float] = None
    min_liquidity_usd_xrp: Optional[float] = None
    max_spread_doge: Optional[float] = None
    min_liquidity_usd_doge: Optional[float] = None
    max_spread_bnb: Optional[float] = None
    min_liquidity_usd_bnb: Optional[float] = None
    max_spread_hype: Optional[float] = None
    min_liquidity_usd_hype: Optional[float] = None
    per_asset_controls: Optional[Dict[str, Any]] = None
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
    timeframe: str = Query("all", pattern="^(today|week|month|all)$"),
    account_mode: Optional[str] = Query("demo", pattern="^(demo|live|all)$"),
    limit: Optional[int] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Retrieve historical trades and comprehensive PnL metrics with lifetime database persistence
    and dynamic timeframe filtering (today, week, month, all-time) separated by account mode (demo vs live).
    Guarantees strict user isolation so that users only see their own trades.
    """
    now_naive = datetime.utcnow()
    base_query = db.query(Fast5MTrade)

    if account_mode == "live":
        base_query = base_query.filter(Fast5MTrade.account_mode == "live")
        if current_user:
            base_query = base_query.filter(Fast5MTrade.user_id == current_user.id)
        else:
            base_query = base_query.filter(Fast5MTrade.id == -1)
    elif account_mode == "demo":
        base_query = base_query.filter((Fast5MTrade.account_mode == "demo") | (Fast5MTrade.account_mode.is_(None)))
    else: # "all"
        if current_user:
            base_query = base_query.filter(
                (Fast5MTrade.account_mode == "demo") | 
                (Fast5MTrade.account_mode.is_(None)) | 
                (Fast5MTrade.user_id == current_user.id)
            )
        else:
            base_query = base_query.filter((Fast5MTrade.account_mode == "demo") | (Fast5MTrade.account_mode.is_(None)))

    if timeframe == "today":
        today_start = now_naive.replace(hour=0, minute=0, second=0, microsecond=0)
        filtered_query = base_query.filter(Fast5MTrade.created_at >= today_start)
    elif timeframe == "week":
        week_start = now_naive - timedelta(days=7)
        filtered_query = base_query.filter(Fast5MTrade.created_at >= week_start)
    elif timeframe == "month":
        month_start = now_naive - timedelta(days=30)
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
            "user_id": getattr(t, "user_id", None),
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
            "execution_type": getattr(t, "execution_type", "SIMULATED_ORDERBOOK") or "SIMULATED_ORDERBOOK",
            "tx_hash": getattr(t, "tx_hash", None),
            "exit_slippage": getattr(t, "exit_slippage", 0.0) or 0.0,
            "buffer_status": getattr(t, "buffer_status", "CLEARED") or "CLEARED",
            "real_orderbook_bid": getattr(t, "real_orderbook_bid", None),
            "exit_price": t.exit_price,
            "pnl": t.pnl,
            "pnl_percent": t.pnl_percent,
            "resolution": t.resolution,
            "created_at": t.created_at.isoformat() if t.created_at else "",
            "closed_at": t.closed_at.isoformat() if t.closed_at else None,
        })

    win_rate = (wins / closed_trades * 100.0) if closed_trades > 0 else 0.0

    # Also compute all-time lifetime stats across closed records matching mode and user
    lifetime_q = db.query(Fast5MTrade).filter(Fast5MTrade.status == "CLOSED")
    if account_mode == "live":
        lifetime_q = lifetime_q.filter(Fast5MTrade.account_mode == "live")
        if current_user:
            lifetime_q = lifetime_q.filter(Fast5MTrade.user_id == current_user.id)
        else:
            lifetime_q = lifetime_q.filter(Fast5MTrade.id == -1)
    elif account_mode == "demo":
        lifetime_q = lifetime_q.filter((Fast5MTrade.account_mode == "demo") | (Fast5MTrade.account_mode.is_(None)))
    else: # "all"
        if current_user:
            lifetime_q = lifetime_q.filter(
                (Fast5MTrade.account_mode == "demo") | 
                (Fast5MTrade.account_mode.is_(None)) | 
                (Fast5MTrade.user_id == current_user.id)
            )
        else:
            lifetime_q = lifetime_q.filter((Fast5MTrade.account_mode == "demo") | (Fast5MTrade.account_mode.is_(None)))

    all_closed_records = lifetime_q.all()
    all_wins = sum(1 for t in all_closed_records if (t.pnl or 0) > 0)
    all_losses = sum(1 for t in all_closed_records if (t.pnl or 0) < 0)
    all_profit = sum(t.pnl for t in all_closed_records if (t.pnl or 0) > 0)
    all_loss = sum(abs(t.pnl) for t in all_closed_records if (t.pnl or 0) < 0)
    all_pnl = all_profit - all_loss
    all_closed_count = len(all_closed_records)
    all_win_rate = (all_wins / all_closed_count * 100.0) if all_closed_count > 0 else 0.0

    # Retrieve user's dedicated vault allocation if available
    user_vault = db.query(Fast5MUserVault).filter(Fast5MUserVault.user_id == current_user.id).first() if current_user else None

    if account_mode == "live":
        from app.fast5m.wallet import wallet_manager
        current_balance = round(user_vault.allocated_balance, 2) if user_vault else round(wallet_manager.total_usdc_balance, 2)
        initial_balance = round(user_vault.initial_deposit, 2) if user_vault else (round(current_balance - all_pnl, 2) if wallet_manager.is_connected else 0.0)
        active_open_trades = len([t for t in fast_executor.get_active_trades() if t.get("account_mode") == "live" and (not current_user or t.get("user_id") == current_user.id)])
    else:
        initial_balance = float(user_vault.allocated_balance if user_vault else fast_executor.settings.get("total_balance_usd", 300.0))
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


def _extract_settings_from_payload(payload: SettingsUpdate) -> Dict[str, str]:
    updates: Dict[str, str] = {}
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

    # Buffer Timer & Risk Parameters
    if payload.buffer_timer_sec is not None:
        updates["buffer_timer_sec"] = str(max(1.0, min(30.0, payload.buffer_timer_sec)))
    if payload.risk_reward_ratio is not None:
        updates["risk_reward_ratio"] = str(round(payload.risk_reward_ratio, 2))
    if payload.take_profit_pct is not None:
        updates["take_profit_pct"] = str(payload.take_profit_pct)
        pos_size = float(payload.position_size_usd or fast_executor.settings.get("position_size_usd", 10.0))
        updates["take_profit_dollar"] = str(round(pos_size * (payload.take_profit_pct / 100.0), 2))
    if payload.stop_loss_pct is not None:
        updates["stop_loss_pct"] = str(payload.stop_loss_pct)
        pos_size = float(payload.position_size_usd or fast_executor.settings.get("position_size_usd", 10.0))
        updates["stop_loss_dollar"] = str(round(pos_size * (payload.stop_loss_pct / 100.0), 2))

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

    # Slippage Circuit Breaker on Exit
    if payload.exit_circuit_breaker_enabled is not None:
        updates["exit_circuit_breaker_enabled"] = "true" if payload.exit_circuit_breaker_enabled else "false"
    if payload.max_exit_slippage_pct is not None:
        updates["max_exit_slippage_pct"] = str(payload.max_exit_slippage_pct)

    # Dedicated Per-Asset Spread & Liquidity Thresholds
    for asset in ["btc", "eth", "sol", "xrp", "doge", "bnb", "hype"]:
        spr = getattr(payload, f"max_spread_{asset}", None)
        if spr is not None:
            updates[f"max_spread_{asset}"] = str(spr)
        liq = getattr(payload, f"min_liquidity_usd_{asset}", None)
        if liq is not None:
            updates[f"min_liquidity_usd_{asset}"] = str(liq)

    if payload.per_asset_controls:
        for a_key, a_cfg in payload.per_asset_controls.items():
            if isinstance(a_cfg, dict):
                a_lower = str(a_key).lower()
                if "max_spread" in a_cfg:
                    updates[f"max_spread_{a_lower}"] = str(a_cfg["max_spread"])
                if "min_liquidity_usd" in a_cfg:
                    updates[f"min_liquidity_usd_{a_lower}"] = str(a_cfg["min_liquidity_usd"])

    return updates


@router.post("/settings")
def update_fast5m_settings(payload: SettingsUpdate):
    """Update Fast 5M settings and optionally persist as permanent custom default baseline."""
    updates = _extract_settings_from_payload(payload)

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
    updates = _extract_settings_from_payload(payload) if payload else {}
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


# ==========================================
# ISOLATED TRADING VAULT & CAPITAL ALLOCATION
# ==========================================

@router.get("/vault")
def get_fast5m_vault(
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Retrieve isolated Fast5M trading allocation vault state,
    calculating active margin in open trades and strictly locked withdrawal limits.
    """
    from app.fast5m.wallet import wallet_manager

    if current_user:
        vault = db.query(Fast5MUserVault).filter(Fast5MUserVault.user_id == current_user.id).first()
        if not vault:
            is_live = current_user.auth_provider == "wallet"
            vault = Fast5MUserVault(
                user_id=current_user.id,
                account_mode="live" if is_live else "demo",
                wallet_address=current_user.wallet_address,
                allocated_balance=0.0 if is_live else 300.0,
                initial_deposit=0.0 if is_live else 300.0,
                total_deposited=0.0 if is_live else 300.0,
                total_withdrawn=0.0
            )
            db.add(vault)
            db.commit()
            db.refresh(vault)
    else:
        vault = None

    allocated_balance = vault.allocated_balance if vault else float(fast_executor.settings.get("total_balance_usd", 300.0))
    account_mode = vault.account_mode if vault else getattr(wallet_manager, "account_mode", "demo")

    # Compute open margin locked in active positions
    active_trades = fast_executor.get_active_trades()
    if current_user:
        user_active_trades = [
            t for t in active_trades 
            if t.get("user_id") == current_user.id or (not t.get("user_id") and t.get("account_mode", "demo") == account_mode)
        ]
    else:
        user_active_trades = [t for t in active_trades if t.get("account_mode", "demo") == account_mode]

    active_margin = round(sum(t.get("cost", 0.0) for t in user_active_trades), 2)
    available_to_withdraw = round(max(0.0, allocated_balance - active_margin), 2)

    return {
        "user_id": current_user.id if current_user else None,
        "account_mode": account_mode,
        "wallet_address": vault.wallet_address if vault else (wallet_manager.wallet_address or None),
        "allocated_balance": round(allocated_balance, 2),
        "initial_deposit": round(vault.initial_deposit if vault else 300.0, 2),
        "total_deposited": round(vault.total_deposited if vault else 300.0, 2),
        "total_withdrawn": round(vault.total_withdrawn if vault else 0.0, 2),
        "active_margin": active_margin,
        "open_trades_count": len(user_active_trades),
        "available_to_withdraw": available_to_withdraw,
        "total_wallet_balance": round(wallet_manager.total_usdc_balance, 2) if wallet_manager.is_connected else 0.0,
        "pol_gas_balance": round(wallet_manager.pol_balance, 4) if wallet_manager.is_connected else 0.0,
        "is_wallet_connected": wallet_manager.is_connected
    }


@router.post("/vault/deposit")
def deposit_to_vault(
    req: VaultDepositRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Allocate capital from primary wallet balance or demo reserves into the Fast5M trading vault.
    Sets the bot's hard capital ceiling to this allocated amount.
    """
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Deposit amount must be strictly greater than $0.00.")

    from app.fast5m.wallet import wallet_manager
    if current_user:
        vault = db.query(Fast5MUserVault).filter(Fast5MUserVault.user_id == current_user.id).first()
        if not vault:
            is_live = current_user.auth_provider == "wallet"
            vault = Fast5MUserVault(
                user_id=current_user.id,
                account_mode="live" if is_live else "demo",
                wallet_address=current_user.wallet_address,
                allocated_balance=0.0 if is_live else 300.0,
                initial_deposit=0.0 if is_live else 300.0
            )
            db.add(vault)
    else:
        vault = None

    account_mode = vault.account_mode if vault else getattr(wallet_manager, "account_mode", "demo")

    if account_mode == "live" and wallet_manager.is_connected:
        wallet_manager.refresh_balances()
        if req.amount > wallet_manager.total_usdc_balance:
            raise HTTPException(
                status_code=400,
                detail=f"Allocation amount (${req.amount:.2f}) exceeds total connected Polygon USDC balance (${wallet_manager.total_usdc_balance:.2f})."
            )

    if vault:
        vault.allocated_balance = round(vault.allocated_balance + req.amount, 2)
        vault.total_deposited = round(vault.total_deposited + req.amount, 2)
        db.commit()
        new_total = vault.allocated_balance
    else:
        curr = float(fast_executor.settings.get("total_balance_usd", 300.0))
        new_total = round(curr + req.amount, 2)

    fast_executor.update_settings({"total_balance_usd": str(new_total)})
    return {
        "success": True,
        "message": f"Successfully allocated ${req.amount:.2f} to Fast5M Trading Vault.",
        "allocated_balance": new_total
    }


@router.post("/vault/withdraw")
def withdraw_from_vault(
    req: VaultWithdrawRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    De-allocate trading funds back to primary wallet reserve.
    Enforces strict safety locking: Available to Withdraw = Allocated Balance - Active Margin in Open Trades.
    """
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Withdrawal amount must be strictly greater than $0.00.")

    from app.fast5m.wallet import wallet_manager
    if current_user:
        vault = db.query(Fast5MUserVault).filter(Fast5MUserVault.user_id == current_user.id).first()
    else:
        vault = None

    allocated_balance = vault.allocated_balance if vault else float(fast_executor.settings.get("total_balance_usd", 300.0))
    account_mode = vault.account_mode if vault else getattr(wallet_manager, "account_mode", "demo")

    # Calculate active margin currently committed to open trades
    active_trades = fast_executor.get_active_trades()
    if current_user:
        user_active_trades = [
            t for t in active_trades 
            if t.get("user_id") == current_user.id or (not t.get("user_id") and t.get("account_mode", "demo") == account_mode)
        ]
    else:
        user_active_trades = [t for t in active_trades if t.get("account_mode", "demo") == account_mode]

    active_margin = round(sum(t.get("cost", 0.0) for t in user_active_trades), 2)
    available_to_withdraw = round(max(0.0, allocated_balance - active_margin), 2)

    if req.amount > available_to_withdraw:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot withdraw ${req.amount:.2f}: ${active_margin:.2f} is currently locked as active margin in {len(user_active_trades)} open trade(s). Maximum available to withdraw is ${available_to_withdraw:.2f}."
        )

    if vault:
        vault.allocated_balance = round(vault.allocated_balance - req.amount, 2)
        vault.total_withdrawn = round(vault.total_withdrawn + req.amount, 2)
        db.commit()
        new_total = vault.allocated_balance
    else:
        curr = float(fast_executor.settings.get("total_balance_usd", 300.0))
        new_total = round(max(0.0, curr - req.amount), 2)

    fast_executor.update_settings({"total_balance_usd": str(max(1.0, new_total))})
    return {
        "success": True,
        "message": f"Successfully de-allocated ${req.amount:.2f} back to wallet reserve.",
        "allocated_balance": new_total,
        "available_to_withdraw": round(max(0.0, new_total - active_margin), 2)
    }


