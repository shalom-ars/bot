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


def ensure_btc5m_settings(db: Session) -> None:
    """Ensure all default keys exist in btc5m_settings."""
    existing = {s.key for s in db.query(BTC5MSetting).all()}
    added = False
    for k, v in DEFAULT_SETTINGS.items():
        if k not in existing:
            db.add(BTC5MSetting(key=k, value=v))
            added = True
    if added:
        try:
            db.commit()
            logger.info("[BTC5M Settings] Seeded default targeting settings in database.")
        except Exception as e:
            db.rollback()
            logger.warning(f"[BTC5M Settings] Failed to seed default settings: {e}")


def get_btc5m_settings(db: Session) -> Dict[str, Any]:
    """Retrieve all targeting settings typed appropriately."""
    rows = db.query(BTC5MSetting).all()
    if not rows:
        ensure_btc5m_settings(db)
        rows = db.query(BTC5MSetting).all()

    result = {}
    row_map = {r.key: r.value for r in rows}
    for k, default_str in DEFAULT_SETTINGS.items():
        raw_val = row_map.get(k, default_str)
        result[k] = _cast_val(k, raw_val)
    return result


def update_btc5m_settings(db: Session, updates: Dict[str, Any], user_info: str = "SYSTEM") -> Dict[str, Any]:
    """Update settings in database persistently and return updated typed settings."""
    for k, v in updates.items():
        if k not in DEFAULT_SETTINGS:
            continue
        str_val = str(v).lower() if isinstance(v, bool) else str(v)
        setting = db.query(BTC5MSetting).filter(BTC5MSetting.key == k).first()
        if setting:
            setting.value = str_val
            setting.updated_at = datetime.now(timezone.utc)
        else:
            db.add(BTC5MSetting(key=k, value=str_val))

    audit = BTC5MAudit(
        action="SETTINGS_UPDATE",
        details=f"Targeting settings updated by {user_info}: {list(updates.keys())}"
    )
    db.add(audit)
    db.commit()
    logger.info(f"[BTC5M Settings] Persisted updated targeting settings: {updates}")
    return get_btc5m_settings(db)
