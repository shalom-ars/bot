from sqlalchemy import Column, Index, Integer, String, Float, Boolean, DateTime, JSON, ForeignKey
from app.db.session import Base
from sqlalchemy.orm import declarative_base
from datetime import datetime


class Market(Base):
    __tablename__ = "markets"
    id = Column(Integer, primary_key=True, index=True)
    market_id   = Column(String, unique=True, index=True)  # Still represents the token_id instrument
    condition_id = Column(String, index=True, nullable=True) # Ties YES/NO tokens together. NULL means old corrupted record.
    question    = Column(String)
    token       = Column(String)            # primary outcome token name (e.g. "Yes")
    token_id    = Column(String, index=True)  # Redundant but kept for backward compatibility
    current_price = Column(Float)
    best_bid    = Column(Float)
    best_ask    = Column(Float)
    spread      = Column(Float)
    liquidity   = Column(Float)
    volume      = Column(Float)
    end_time    = Column(DateTime, index=True)
    last_update = Column(DateTime, default=datetime.utcnow)
    active      = Column(Boolean, default=True, index=True)
    quarantine_until = Column(DateTime, nullable=True)
    # Resolution fields – populated by the resolution-checker
    resolved       = Column(Boolean, default=False, index=True)
    resolved_at    = Column(DateTime, nullable=True)
    resolution     = Column(String, nullable=True)   # "YES" | "NO" | None


class Trade(Base):
    __tablename__ = "trades"
    id              = Column(Integer, primary_key=True, index=True)
    trade_id        = Column(String, unique=True, index=True)
    market_id       = Column(String, index=True)
    condition_id    = Column(String)
    token_id        = Column(String)
    strategy        = Column(String)
    timestamp       = Column(DateTime, default=datetime.utcnow)
    entry_timestamp = Column(DateTime)
    exit_timestamp  = Column(DateTime)
    side            = Column(String)
    requested_size  = Column(Float)
    approved_size   = Column(Float)
    entry_price     = Column(Float)
    quantity        = Column(Float)
    position_value  = Column(Float)
    model_probability  = Column(Float)
    market_probability = Column(Float)
    edge            = Column(Float)
    confidence      = Column(Float)
    fees            = Column(Float)
    slippage        = Column(Float)
    exit_price      = Column(Float, nullable=True)
    pnl             = Column(Float, nullable=True)
    status          = Column(String)   # OPEN, CLOSED
    reason          = Column(String)


class Position(Base):
    __tablename__ = "positions"
    id            = Column(Integer, primary_key=True, index=True)
    market_id     = Column(String, unique=True)
    condition_id  = Column(String)
    token_id      = Column(String)
    strategy      = Column(String)
    timestamp     = Column(DateTime, default=datetime.utcnow)
    side          = Column(String)
    entry_price   = Column(Float)
    quantity      = Column(Float)
    current_price = Column(Float)
    unrealized_pnl = Column(Float)


class BotEvent(Base):
    __tablename__ = "bot_events"
    id        = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    level     = Column(String)
    message   = Column(String)


class MarketSnapshot(Base):
    """
    One row per CLOB orderbook poll for a single token.
    source is always 'POLYMARKET' for live data.
    is_synthetic is always False for live data; True only for test fixtures.
    """
    __tablename__ = "market_snapshots"
    id                 = Column(Integer, primary_key=True, index=True)
    source             = Column(String, index=True)
    symbol             = Column(String, index=True)
    market_id          = Column(String, index=True)
    token_id           = Column(String, index=True, nullable=True)
    event_timestamp    = Column(DateTime, index=True)
    received_timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    price              = Column(Float)
    bid                = Column(Float, nullable=True)
    ask                = Column(Float, nullable=True)
    spread             = Column(Float, nullable=True)
    bid_depth          = Column(Float, nullable=True)
    ask_depth          = Column(Float, nullable=True)
    imbalance          = Column(Float, nullable=True)
    volume             = Column(Float, nullable=True)
    liquidity          = Column(Float, nullable=True)
    latency_ms         = Column(Integer, nullable=True)
    is_synthetic       = Column(Boolean, default=False)   # MUST be False for real data
    trade_eligible     = Column(Boolean, default=False, index=True)   # passes trade filters
    ineligibility_reason = Column(String, nullable=True)  # why not trade-eligible

# Composite index for fast time-series queries
Index("ix_ms_market_time", MarketSnapshot.market_id, MarketSnapshot.received_timestamp)
Index("ix_ms_token_time",  MarketSnapshot.token_id,  MarketSnapshot.received_timestamp)


class RiskDecisionLog(Base):
    __tablename__ = "risk_decisions"
    id            = Column(Integer, primary_key=True, index=True)
    timestamp     = Column(DateTime, default=datetime.utcnow)
    signal_id     = Column(String)
    market_id     = Column(String)
    condition_id  = Column(String)
    decision      = Column(String)
    requested_size = Column(Float)
    approved_size  = Column(Float)
    current_exposure = Column(Float)
    new_exposure   = Column(Float)
    daily_pnl      = Column(Float)
    drawdown       = Column(Float)
    consecutive_losses = Column(Integer)
    reason         = Column(String)

class Signal(Base):
    __tablename__ = "signals"
    id             = Column(Integer, primary_key=True, index=True)
    timestamp      = Column(DateTime, default=datetime.utcnow, index=True)
    market_id      = Column(String, index=True)
    signal_type    = Column(String)
    
    # Phase 3 Fields
    strategy       = Column(String)
    fair_probability = Column(Float)
    calibrated_probability = Column(Float)
    market_prob    = Column(Float)
    model_prob     = Column(Float) # Legacy/fallback
    entry_price    = Column(Float)
    raw_edge       = Column(Float)
    spread_cost    = Column(Float)
    slippage_cost  = Column(Float)
    liquidity_cost = Column(Float)
    fees           = Column(Float)
    net_edge       = Column(Float)
    effective_edge = Column(Float) # Legacy/fallback
    threshold      = Column(Float)
    confidence     = Column(Float)
    uncertainty    = Column(Float)
    correlation_status = Column(String)
    market_quality_status = Column(String)
    model_version  = Column(String)
    reason         = Column(String)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    dataset_version = Column(String)
    model_version = Column(String)
    strategy_version = Column(String)
    train_start = Column(DateTime)
    train_end = Column(DateTime)
    validation_start = Column(DateTime)
    validation_end = Column(DateTime)
    test_start = Column(DateTime)
    test_end = Column(DateTime)
    resolved_markets = Column(Integer)
    valid_samples = Column(Integer)
    trades = Column(Integer)
    win_rate = Column(Float, nullable=True)
    brier_score = Column(Float, nullable=True)
    net_pnl = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    profit_factor = Column(Float, nullable=True)
    status = Column(String)

class PaperTestSession(Base):
    __tablename__ = "paper_test_sessions"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True)
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    status = Column(String)
    initial_balance = Column(Float)
    current_balance = Column(Float)
    equity = Column(Float)
    resolved_markets = Column(Integer, default=0)
    signals = Column(Integer, default=0)
    actionable_signals = Column(Integer, default=0)
    skipped_signals = Column(Integer, default=0)
    paper_trades = Column(Integer, default=0)
    closed_trades = Column(Integer, default=0)
    open_positions = Column(Integer, default=0)
    net_pnl = Column(Float, default=0.0)
    drawdown = Column(Float, default=0.0)
    win_rate = Column(Float, default=0.0)
    profit_factor = Column(Float, default=0.0)
    expectancy = Column(Float, default=0.0)
    average_net_edge = Column(Float, default=0.0)

class PaperDailySnapshot(Base):
    __tablename__ = "paper_daily_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)
    date = Column(DateTime)
    starting_equity = Column(Float)
    ending_equity = Column(Float)
    daily_pnl = Column(Float)
    daily_return = Column(Float)
    trades = Column(Integer)
    wins = Column(Integer)
    losses = Column(Integer)
    drawdown = Column(Float)
    exposure = Column(Float)
    fees = Column(Float)
    slippage = Column(Float)
    signals = Column(Integer)
    skips = Column(Integer)

class LiveOrder(Base):
    __tablename__ = "live_orders"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, unique=True, nullable=True) # API order ID (null before submission)
    client_id = Column(String, unique=True) # Idempotency key
    market_id = Column(String)
    condition_id = Column(String)
    token_id = Column(String)
    side = Column(String)
    price = Column(Float)
    quantity = Column(Float)
    state = Column(String) # CREATED, VALIDATED, SUBMITTED, ACKNOWLEDGED, PARTIALLY_FILLED, FILLED, CANCEL_REQUESTED, CANCELLED, REJECTED, EXPIRED, FAILED
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    error_reason = Column(String, nullable=True)

class CircuitBreakerEvent(Base):
    __tablename__ = "circuit_breaker_events"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    event_type = Column(String)
    reason = Column(String)
    resolved = Column(Boolean, default=False)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    action = Column(String)
    details = Column(String)

# --- PHASE 8 SAAS MODELS ---

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="USER")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    plan = Column(String, default="FREE")
    status = Column(String, default="ACTIVE")
    provider_subscription_id = Column(String, nullable=True)
    current_period_end = Column(DateTime, nullable=True)

class UserPortfolio(Base):
    __tablename__ = "user_portfolios"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    paper_status = Column(String, default="STOPPED")
    initial_balance = Column(Float, default=500.0)
    current_balance = Column(Float, default=500.0)
    equity = Column(Float, default=500.0)
    exposure = Column(Float, default=0.0)
    realized_pnl = Column(Float, default=0.0)
    unrealized_pnl = Column(Float, default=0.0)
    drawdown = Column(Float, default=0.0)
    trades = Column(Integer, default=0)
    wins = Column(Integer, default=0)

class UserTrade(Base):
    __tablename__ = "user_trades"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    market_id = Column(String)
    condition_id = Column(String)
    token_id = Column(String)
    side = Column(String)
    entry_price = Column(Float)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Float)
    pnl = Column(Float, nullable=True)
    status = Column(String) # OPEN, CLOSED
    entry_time = Column(DateTime, default=datetime.utcnow)
    exit_time = Column(DateTime, nullable=True)

class UserPosition(Base):
    __tablename__ = "user_positions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    market_id = Column(String)
    condition_id = Column(String)
    token_id = Column(String)
    side = Column(String)
    entry_price = Column(Float)
    quantity = Column(Float)

class UserSetting(Base):
    __tablename__ = "user_settings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    max_position_risk = Column(Float, default=0.02)
    max_drawdown = Column(Float, default=0.15)
    notifications_enabled = Column(Boolean, default=True)

class UsageRecord(Base):
    __tablename__ = "usage_records"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    endpoint = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

class DataCollectionStats(Base):
    """
    Single-row stats table updated by the orchestrator.
    Gives the dashboard O(1) reads instead of full table scans.
    """
    __tablename__ = "data_collection_stats"
    id                   = Column(Integer, primary_key=True, default=1)
    collection_started   = Column(DateTime, nullable=True)
    last_snapshot        = Column(DateTime, nullable=True)
    total_snapshots      = Column(Integer, default=0)
    unique_markets       = Column(Integer, default=0)
    resolved_markets     = Column(Integer, default=0)
    unresolved_markets   = Column(Integer, default=0)
    valid_training_samples = Column(Integer, default=0)
    invalid_samples      = Column(Integer, default=0)
    api_errors           = Column(Integer, default=0)
    orderbook_failures   = Column(Integer, default=0)


# ══════════════════════════════════════════════════════════════
# BTC 5M Module Models
# ══════════════════════════════════════════════════════════════


class BTC5MPriceHistory(Base):
    __tablename__ = "btc5m_price_history"
    id              = Column(Integer, primary_key=True, index=True)
    market_id       = Column(String, index=True)
    timestamp       = Column(DateTime, default=datetime.utcnow, index=True)
    best_bid        = Column(Float)
    best_ask        = Column(Float)

class BTC5MMarket(Base):
    """Discovered BTC 5-minute prediction markets from Polymarket."""
    __tablename__ = "btc5m_markets"
    id              = Column(Integer, primary_key=True, index=True)
    market_id       = Column(String, unique=True, index=True)   # YES token_id
    condition_id    = Column(String, index=True, nullable=True)
    question        = Column(String)
    yes_token_id    = Column(String, index=True)
    no_token_id     = Column(String, nullable=True)
    start_time      = Column(DateTime, nullable=True)
    end_time        = Column(DateTime, nullable=True, index=True)
    # Latest CLOB snapshot
    best_bid        = Column(Float, nullable=True)
    best_ask        = Column(Float, nullable=True)
    bid_depth       = Column(Float, nullable=True)
    ask_depth       = Column(Float, nullable=True)
    spread          = Column(Float, nullable=True)
    mid_price       = Column(Float, nullable=True)
    imbalance       = Column(Float, nullable=True)
    liquidity       = Column(Float, nullable=True)
    time_remaining_sec = Column(Float, nullable=True)
    orderbook_timestamp = Column(DateTime, nullable=True)
    is_valid        = Column(Boolean, default=False)
    rejection_reason = Column(String, nullable=True)
    last_seen       = Column(DateTime, default=datetime.utcnow)


class BTC5MSignal(Base):
    """Full signal audit trail for every BTC 5M evaluation."""
    __tablename__ = "btc5m_signals"
    id              = Column(Integer, primary_key=True, index=True)
    market_id       = Column(String, index=True)
    condition_id    = Column(String, nullable=True)
    question        = Column(String)
    yes_token_id    = Column(String, nullable=True)
    no_token_id     = Column(String, nullable=True)
    timestamp       = Column(DateTime, default=datetime.utcnow, index=True)
    state           = Column(String, index=True)  # WATCH/SETUP/READY/ENTER/SKIP/HOLD/EXIT/RESOLVED
    side            = Column(String)              # BUY/SELL/NONE
    entry_price     = Column(Float, nullable=True)
    bid             = Column(Float, nullable=True)
    ask             = Column(Float, nullable=True)
    spread          = Column(Float, nullable=True)
    bid_depth       = Column(Float, nullable=True)
    ask_depth       = Column(Float, nullable=True)
    momentum        = Column(Float, nullable=True)
    imbalance       = Column(Float, nullable=True)
    ob_pressure     = Column(Float, nullable=True)
    volatility      = Column(Float, nullable=True)
    yes_score       = Column(Float, nullable=True)
    no_score        = Column(Float, nullable=True)
    yes_prob        = Column(Float, nullable=True)
    no_prob         = Column(Float, nullable=True)
    predicted_side  = Column(String, nullable=True)
    gate_results    = Column(String, nullable=True)
    yes_breakdown   = Column(String, nullable=True)
    no_breakdown    = Column(String, nullable=True)
    momentum_persistence = Column(Float, nullable=True)
    market_probability   = Column(Float, nullable=True)
    fair_probability     = Column(Float, nullable=True)
    raw_edge        = Column(Float, nullable=True)
    spread_cost     = Column(Float, nullable=True)
    slippage_cost   = Column(Float, nullable=True)
    fees            = Column(Float, nullable=True)
    net_edge        = Column(Float, nullable=True)
    risk_pct        = Column(Float, nullable=True)
    position_size   = Column(Float, nullable=True)
    time_remaining_sec = Column(Float, nullable=True)
    model_version   = Column(String, nullable=True)
    strategy        = Column(String, nullable=True)
    reason          = Column(String)


class BTC5MTrade(Base):
    """Paper trades executed by the BTC 5M strategy."""
    __tablename__ = "btc5m_trades"
    id              = Column(Integer, primary_key=True, index=True)
    market_id       = Column(String, index=True)
    condition_id    = Column(String, nullable=True)
    question        = Column(String)
    yes_token_id    = Column(String, nullable=True)
    no_token_id     = Column(String, nullable=True)
    side            = Column(String)
    entry_price     = Column(Float)
    exit_price      = Column(Float, nullable=True)
    quantity        = Column(Float)
    position_size   = Column(Float)
    spread_at_entry = Column(Float, nullable=True)
    fees            = Column(Float, nullable=True)
    slippage        = Column(Float, nullable=True)
    net_edge        = Column(Float, nullable=True)
    momentum_at_entry   = Column(Float, nullable=True)
    imbalance_at_entry  = Column(Float, nullable=True)
    time_remaining_at_entry = Column(Float, nullable=True)
    yes_score           = Column(Float, nullable=True)
    no_score            = Column(Float, nullable=True)
    planned_risk    = Column(Float, nullable=True)
    planned_reward  = Column(Float, nullable=True)
    planned_rr      = Column(Float, nullable=True)
    stop_loss_price = Column(Float, nullable=True)
    take_profit_price = Column(Float, nullable=True)
    actual_rr       = Column(Float, nullable=True)
    strategy        = Column(String, default="BTC_5M")
    model_version   = Column(String, nullable=True)
    entry_reason    = Column(String, nullable=True)
    exit_reason     = Column(String, nullable=True)
    status          = Column(String, default="OPEN", index=True)  # OPEN/CLOSED
    entry_time      = Column(DateTime, default=datetime.utcnow, index=True)
    exit_time       = Column(DateTime, nullable=True)
    pnl             = Column(Float, nullable=True)
    resolution      = Column(String, nullable=True)   # YES/NO/NONE

    # ══════════════════════════════════════════════════════════════
    # IMMUTABLE TRADE THESIS FIELDS (WRITE-ONCE AT ENTRY)
    # ══════════════════════════════════════════════════════════════
    locked_predicted_side = Column(String, nullable=True)  # "YES" | "NO"
    locked_direction      = Column(String, nullable=True)  # "YES" | "NO"
    locked_outcome        = Column(String, nullable=True)  # "UP" | "DOWN"
    locked_token_id       = Column(String, nullable=True)  # YES or NO token ID
    execution_side        = Column(String, default="BUY", nullable=True)  # Always "BUY"
    entry_yes_score       = Column(Float, nullable=True)
    entry_no_score        = Column(Float, nullable=True)
    entry_fair_probability= Column(Float, nullable=True)
    entry_market_probability = Column(Float, nullable=True)
    entry_net_edge        = Column(Float, nullable=True)
    entry_planned_rr      = Column(Float, nullable=True)
    entry_stop_price      = Column(Float, nullable=True)
    entry_target_price    = Column(Float, nullable=True)
    prediction_locked_at  = Column(DateTime, nullable=True)
    prediction_lock_version = Column(String, default="1.0", nullable=True)


import logging
_thesis_logger = logging.getLogger("btc5m.thesis_lock")

# Immutable thesis fields protected from mutation after write-once entry
LOCKED_TRADE_THESIS_FIELDS = frozenset([
    "locked_predicted_side",
    "locked_direction",
    "locked_outcome",
    "locked_token_id",
    "execution_side",
    "entry_yes_score",
    "entry_no_score",
    "entry_fair_probability",
    "entry_market_probability",
    "entry_net_edge",
    "entry_planned_rr",
    "entry_stop_price",
    "entry_target_price",
    "prediction_locked_at",
    "entry_price",
    "market_id",
    "condition_id",
    "side",
    "strategy",
    "model_version"
])

from sqlalchemy import event, inspect as sa_inspect

@event.listens_for(BTC5MTrade, 'before_update')
def protect_locked_trade_thesis(mapper, connection, target):
    """
    Guarantees that a trade's thesis is strictly WRITE-ONCE and immutable.
    Any attempt to mutate locked prediction/entry fields is rejected,
    preserving the original values and logging an audit event.
    """
    state = sa_inspect(target)
    for attr in state.attrs:
        if attr.key in LOCKED_TRADE_THESIS_FIELDS:
            history = attr.history
            if history.has_changes():
                old_val = history.deleted[0] if history.deleted else None
                if old_val is not None:
                    _thesis_logger.warning(
                        f"[SECURITY/THESIS LOCK] Rejected attempt to mutate immutable field '{attr.key}' "
                        f"on trade id={target.id} from '{old_val}' to '{history.added[0]}'. Preserving original thesis."
                    )
                    setattr(target, attr.key, old_val)


class BTC5MSkip(Base):
    """Skipped BTC 5M markets."""
    __tablename__ = "btc5m_skips"
    id              = Column(Integer, primary_key=True, index=True)
    market_id       = Column(String, index=True)
    question        = Column(String)
    yes_score       = Column(Float)
    no_score        = Column(Float)
    yes_prob        = Column(Float)
    no_prob         = Column(Float)
    net_edge        = Column(Float)
    spread          = Column(Float)
    liquidity       = Column(Float)
    volatility      = Column(Float)
    time_remaining  = Column(Float)
    planned_rr      = Column(Float)
    skip_reason     = Column(String)
    timestamp       = Column(DateTime, default=lambda: __import__('datetime').datetime.now(__import__('datetime').timezone.utc))
    actual_resolution    = Column(String, nullable=True)
    hypothetical_outcome = Column(String, nullable=True)
    predicted_side       = Column(String, nullable=True)
    gate_results         = Column(String, nullable=True)
    yes_breakdown        = Column(String, nullable=True)
    no_breakdown         = Column(String, nullable=True)

class BTC5MAudit(Base):
    """Audit log for BTC 5M module."""
    __tablename__ = "btc5m_audit"
    id          = Column(Integer, primary_key=True, index=True)
    action      = Column(String) # "START" or "STOP"
    timestamp   = Column(DateTime, default=lambda: __import__('datetime').datetime.now(__import__('datetime').timezone.utc))
    details     = Column(String)


class BTC5MSetting(Base):
    """Persistent key-value targeting and configuration settings for BTC 5M module."""
    __tablename__ = "btc5m_settings"
    key         = Column(String(64), primary_key=True, index=True)
    value       = Column(String(256), nullable=False)
    updated_at  = Column(DateTime, default=lambda: __import__('datetime').datetime.now(__import__('datetime').timezone.utc))

