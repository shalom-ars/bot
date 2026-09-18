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
    "min_entry_score": "55.0",
    "min_net_edge": "0.005",
    "min_rr": "1.2",
    "max_spread": "0.05",
    "min_liquidity": "100.0",
    "min_time_remaining": "30.0",
    "max_time_remaining": "300.0",
    "take_profit_delta": "0.30",
    "max_take_profit": "0.95",
    "stop_loss_ratio": "0.50",
    "risk_per_trade": "0.02",
    "max_consecutive_losses": "5",
    "mode": "dynamic",
    "tp_dollar": "3.00",
    "sl_dollar": "2.00",
    "side_bias": "ANY",
    "only_short": "false",
}

DEFAULT_SETTINGS_INSTANCE_2: Dict[str, str] = {
    "trading_active": "true",
    "min_entry_score": "60.0",
    "min_net_edge": "0.015",
    "min_rr": "1.5",
    "max_spread": "0.05",
    "min_liquidity": "100.0",
    "min_time_remaining": "30.0",
    "max_time_remaining": "240.0",
    "take_profit_delta": "0.30",
    "max_take_profit": "0.95",
    "stop_loss_ratio": "0.50",
    "risk_per_trade": "0.02",
    "max_consecutive_losses": "5",
    "mode": "fixed_dollar",
    "tp_dollar": "3.00",
    "sl_dollar": "2.00",
    "side_bias": "NO",
    "only_short": "true",
}

TYPED_FIELDS = {
    "trading_active": bool,
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
    "side_bias": str,
    "only_short": bool,
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
    """Ensure all default keys exist in btc5m_settings for the specified instance."""
    existing = {s.key for s in db.query(BTC5MSetting).all()}
    added = False
    prefix = "" if instance_id in ("instance_1", "default") else f"{instance_id}:"
    defaults = DEFAULT_SETTINGS_INSTANCE_2 if instance_id == "instance_2" else DEFAULT_SETTINGS
    for k, v in defaults.items():
        db_key = f"{prefix}{k}"
        if db_key not in existing:
            db.add(BTC5MSetting(key=db_key, value=v))
            added = True
    if added:
        try:
            db.commit()
            logger.info(f"[BTC5M Settings] Seeded default targeting settings for {instance_id} in database.")
        except Exception as e:
            db.rollback()
            logger.warning(f"[BTC5M Settings] Failed to seed default settings for {instance_id}: {e}")


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
