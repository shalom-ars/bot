"""
Persistent Targeting and Configuration Manager for BTC 5M Module.
Guarantees settings and targeting parameters survive server reboots and updates.
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.db.models import BTC5MSetting, BTC5MAudit

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS: Dict[str, str] = {
    "trading_active": "true",
    "account_mode": "demo",
    "slot_mode": "single_5m",
    "risk_reward_ratio": "0.0:1",
    "min_entry_score": "85.0",         # Ultra-strict target 95% WR
    "min_net_edge": "0.02",            # Require minimum positive EV
    "min_rr": "0.0",
    "max_spread": "0.015",             # Max 1.5 cents spread
    "min_liquidity": "50.0",           # Deep liquidity only
    "min_time_remaining": "0.0",
    "max_time_remaining": "300.0",
    "take_profit_delta": "0.05",
    "max_take_profit": "0.95",
    "stop_loss_ratio": "1.50",
    "risk_per_trade": "0.02",
    "max_consecutive_losses": "5",
    "mode": "fixed_dollar",
    "tp_dollar": "2.00",               
    "sl_dollar": "1.00",               
    "hard_cap_dollar": "1.20",         
    "side_bias": "ANY",
    "only_short": "false",
    "soft_stop_confirmation_seconds": "3.0",
    "thesis_failure_threshold": "60.0",
    "hard_stop_delta": "0.01",
    "min_entry_price": "0.01",
    "max_entry_price": "0.99",
    "min_p2b_diff": "0.0",
    "min_entry_probability": "0.65",   # 65% minimum ML probability for extreme safety
    "dynamic_sl_delta": "0.20",
    "rsi_period": "14",
    "rsi_overbought": "75.0",
    "rsi_oversold": "25.0",
    "macd_fast": "12",
    "macd_slow": "26",
    "macd_signal": "9",
    "bb_period": "20",
    "bb_std": "2.0",
    "atr_period": "14",
    "atr_trailing_multiplier": "3.0",
    "breakeven_trigger_dollar": "0.02",
    "micro_loss_tolerance": "0.035",
    "mtf_confirmation_enabled": "false",
    "consecutive_loss_dampener_enabled": "false",
    "min_order_book_imbalance": "0.0",
    "cooldown_seconds": "15.0",
    "unanimous_consensus_required": "false",
    "rsi_overbought": "100.0",
    "rsi_oversold": "0.0",
}

DEFAULT_SETTINGS_INSTANCE_2 = DEFAULT_SETTINGS.copy()
DEFAULT_SETTINGS_INSTANCE_2.update({
    "slot_mode": "double_slot_2.5m",
    "min_entry_score": "85.0",         # Ultra-strict target 95% WR
    "min_entry_probability": "0.65",   # Extreme ML confidence
    "min_liquidity": "50.0",           # Deep order book
    "max_spread": "0.015",             # Stop slippage trap (Max 1.5 cents)
    "min_net_edge": "0.02",            # Positive EV requirement
    "micro_loss_tolerance": "10.00",    # $10 Loss Tolerance for full reversal breathing room
    "breakeven_trigger_dollar": "0.50",
    "cooldown_seconds": "20.0",        # Quick recovery for double slot
    "hard_stop_delta": "0.01",
    "tp_dollar": "1.00",               # $1.00 Win Target
    "sl_dollar": "10.00",              # $10.00 Loss Limit for market reversal
    "hard_cap_dollar": "10.00",        # $10.00 Hard Loss Cap
    "dynamic_sl_delta": "0.90",        # Allow contract price fluctuation
    "rsi_period": "14",
    "macd_fast": "12",
    "macd_slow": "26"
})

TYPED_FIELDS = {
    "trading_active": bool,
    "account_mode": str,
    "slot_mode": str,
    "risk_reward_ratio": str,
    "min_entry_score": float,
    "min_net_edge": float,
    "min_rr": float,
    "max_spread": float,
    "min_liquidity": float,
    "min_time_remaining": float,
    "max_time_remaining": float,
    "take_profit_delta": float,
    "max_take_profit": float,
    "stop_loss_ratio": float,
    "risk_per_trade": float,
    "max_consecutive_losses": int,
    "mode": str,
    "tp_dollar": float,
    "sl_dollar": float,
    "hard_cap_dollar": float,
    "side_bias": str,
    "only_short": bool,
    "soft_stop_confirmation_seconds": float,
    "thesis_failure_threshold": float,
    "hard_stop_delta": float,
    "min_entry_price": float,
    "max_entry_price": float,
    "min_p2b_diff": float,
    "min_entry_probability": float,
    "dynamic_sl_delta": float,
    "rsi_period": int,
    "rsi_overbought": float,
    "rsi_oversold": float,
    "macd_fast": int,
    "macd_slow": int,
    "macd_signal": int,
    "bb_period": int,
    "bb_std": float,
    "atr_period": int,
    "atr_trailing_multiplier": float,
    "breakeven_trigger_dollar": float,
    "mtf_confirmation_enabled": bool,
    "consecutive_loss_dampener_enabled": bool,
    "min_order_book_imbalance": float,
    "cooldown_seconds": float,
    "unanimous_consensus_required": bool,
}



def _cast_val(key: str, val: str) -> Any:
    target_type = TYPED_FIELDS.get(key, str)
    if target_type == bool:
        return str(val).strip().lower() in ("true", "1", "yes", "on")
    if target_type == int:
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return int(DEFAULT_SETTINGS.get(key, 5))
    if target_type == float:
        try:
            return float(val)
        except (ValueError, TypeError):
            return float(DEFAULT_SETTINGS.get(key, 0.0))
    return str(val)


def ensure_btc5m_settings(db: Session, instance_id: str = "instance_1") -> None:
    """Ensure all default keys exist in btc5m_settings for the specified instance and sync loosened criteria."""
    existing = {s.key: s for s in db.query(BTC5MSetting).all()}
    modified = False
    prefix = "" if instance_id in ("instance_1", "default") else f"{instance_id}:"
    defaults = DEFAULT_SETTINGS_INSTANCE_2 if instance_id == "instance_2" else DEFAULT_SETTINGS

    # To allow the AI Self-Optimizer to function, we MUST NOT forcefully override its learned settings continually.
    # However, to migrate from the old '0.0' blind-trading values to the new optimal ones, we do a one-time upgrade if the value is dangerously low.
    loosened_sync = {}
    
    if instance_id == "instance_2":
        loosened_sync["slot_mode"] = "double_slot_2.5m"
        loosened_sync["tp_dollar"] = "1.00"
        loosened_sync["sl_dollar"] = "10.00"
        loosened_sync["hard_cap_dollar"] = "10.00"
        loosened_sync["micro_loss_tolerance"] = "10.00"
        loosened_sync["dynamic_sl_delta"] = "0.90"
        loosened_sync["breakeven_trigger_dollar"] = "0.50"
    else:
        loosened_sync["slot_mode"] = "single_5m"
        
    for k, v in defaults.items():
        db_key = f"{prefix}{k}"
        if db_key not in existing:
            db.add(BTC5MSetting(key=db_key, value=v))
            modified = True
        else:
            setting_obj = existing[db_key]
            # ONE-TIME MIGRATION: If the DB currently holds the legacy "0.0" bypass value for critical filters,
            # or the old "1.50" TP for Bot 1, force upgrade it to the new optimal default.
            if k in ["min_entry_score", "min_entry_probability", "min_liquidity"] and setting_obj.value == "0.0":
                setting_obj.value = defaults[k]
                setting_obj.updated_at = datetime.now(timezone.utc)
                modified = True
            elif k == "tp_dollar" and setting_obj.value == "1.50":
                setting_obj.value = defaults[k]
                modified = True
            elif k == "sl_dollar" and setting_obj.value == "0.90":
                setting_obj.value = defaults[k]
                modified = True
            elif k == "max_spread" and setting_obj.value == "1.0":
                setting_obj.value = defaults[k]
                modified = True
            elif k == "micro_loss_tolerance" and setting_obj.value in ["0.10", "0.005"]:
                setting_obj.value = defaults[k]
                modified = True
            elif k in loosened_sync and setting_obj.value != loosened_sync[k]:
                setting_obj.value = loosened_sync[k]
                setting_obj.updated_at = datetime.now(timezone.utc)
                modified = True

    if modified:
        try:
            db.commit()
            logger.info(f"[BTC5M Settings] Seeded and synced loosened targeting settings for {instance_id} in database.")
        except Exception as e:
            db.rollback()
            logger.warning(f"[BTC5M Settings] Failed to seed/sync default settings for {instance_id}: {e}")


def get_btc5m_settings(db: Session, instance_id: str = "instance_1") -> Dict[str, Any]:
    """Retrieve all targeting settings typed appropriately for the specified instance."""
    rows = db.query(BTC5MSetting).all()
    if not rows:
        ensure_btc5m_settings(db, instance_id)
        rows = db.query(BTC5MSetting).all()

    prefix = "" if instance_id in ("instance_1", "default") else f"{instance_id}:"
    defaults = DEFAULT_SETTINGS_INSTANCE_2 if instance_id == "instance_2" else DEFAULT_SETTINGS
    result = {}
    row_map = {r.key: r.value for r in rows}
    for k, default_str in defaults.items():
        db_key = f"{prefix}{k}"
        # Look for prefixed key first, fall back to un-prefixed, then default
        raw_val = row_map.get(db_key, row_map.get(k, default_str))
        result[k] = _cast_val(k, raw_val)
    return result


def update_btc5m_settings(db: Session, updates: Dict[str, Any], user_info: str = "SYSTEM", instance_id: str = "instance_1") -> Dict[str, Any]:
    """Update settings in database persistently and return updated typed settings."""
    prefix = "" if instance_id in ("instance_1", "default") else f"{instance_id}:"
    defaults = DEFAULT_SETTINGS_INSTANCE_2 if instance_id == "instance_2" else DEFAULT_SETTINGS
    for k, v in updates.items():
        if k not in defaults:
            continue
        db_key = f"{prefix}{k}"
        str_val = str(v).lower() if isinstance(v, bool) else str(v)
        setting = db.query(BTC5MSetting).filter(BTC5MSetting.key == db_key).first()
        if setting:
            setting.value = str_val
            setting.updated_at = datetime.now(timezone.utc)
        else:
            db.add(BTC5MSetting(key=db_key, value=str_val))

    audit = BTC5MAudit(
        action="SETTINGS_UPDATE",
        details=f"Targeting settings for {instance_id} updated by {user_info}: {list(updates.keys())}"
    )
    db.add(audit)
    db.commit()
    logger.info(f"[BTC5M Settings] Persisted updated targeting settings for {instance_id}: {updates}")
    return get_btc5m_settings(db, instance_id)
