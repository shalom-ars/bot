"""
Control & Telemetry Audit Suite — Fast5M Trade Engine
Validates:
  1. Real fill logic vs simulated math
  2. Buffer override enforcement on trailing stops
  3. PnL logic integrity (no artificial clamping)
  4. Slippage calculation correctness
  5. Trailing lock breakeven protection
  6. Epoch expiry resolution logic
  7. Reversal lock in-profit guard
  8. entry_ts integrity after rehydration
"""
import time
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone
from app.db.session import engine, ensure_fast5m_schema

ensure_fast5m_schema(engine)

from app.fast5m.executor import FastExecutor
from app.fast5m.discovery import FastMarketInfo
from app.fast5m.oracle import AssetOracleState

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_market(up_bid=0.55, down_bid=0.45, time_rem=60.0) -> FastMarketInfo:
    """Return a synthetic FastMarketInfo with explicit CLOB bids."""
    m = FastMarketInfo(
        asset="BTC",
        question="BTC Up?",
        condition_id="cond_1",
        up_token_id="up_tok",
        down_token_id="dn_tok",
        epoch_bucket=100,
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
        time_remaining_sec=time_rem,
        up_bid=up_bid,
        up_ask=up_bid + 0.01,
        up_mid=(up_bid + up_bid + 0.01) / 2,
        down_bid=down_bid,
        down_ask=down_bid + 0.01,
        down_mid=(down_bid + down_bid + 0.01) / 2,
    )
    return m

def make_oracle(live_price=90200.0, v10=0.0) -> AssetOracleState:
    state = AssetOracleState(symbol="BTC", strike_price=90000.0)
    state.live_price = live_price
    state.velocity_10s = v10
    return state

def make_trade(
    cost=10.0, entry_price=0.50, shares=20.0,
    outcome="UP", entry_oracle=90000.0, strike=90000.0,
    entry_ts=None, peak_pnl=0.0
):
    """Build a synthetic in-memory active trade dict."""
    return {
        "id": 1,
        "asset": "BTC",
        "outcome": outcome,
        "cost": cost,
        "shares": shares,
        "entry_price": entry_price,
        "strike_price": strike,
        "entry_oracle_price": entry_oracle,
        "account_mode": "demo",
        "entry_ts": entry_ts if entry_ts is not None else time.time() - 30.0,
        "peak_pnl": peak_pnl,
        "current_pnl": 0.0,
        "trailing_armed": False,
        "trailing_floor": 0.0,
    }

# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Real Fill — PnL uses up_bid / down_bid (not synthetic oracle math)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_real_fill_uses_clob_bid_not_synthetic_math():
    """
    Verify that mark-to-market evaluation uses market.up_bid or market.down_bid
    for the share price calculation, NOT the synthetic oracle delta formula.
    """
    executor = FastExecutor()

    trade = make_trade(cost=10.0, entry_price=0.50, shares=20.0, outcome="UP")
    oracle = make_oracle(live_price=90500.0)  # oracle moved up strongly
    market = make_market(up_bid=0.60, down_bid=0.40)  # CLOB up_bid = 0.60

    with patch("app.fast5m.executor.fast_oracle.get_asset_state", return_value=oracle), \
         patch("app.fast5m.executor.fast_markets.get_market", return_value=market), \
         patch("app.fast5m.executor.SessionLocal") as mock_session:

        # Manually compute what the engine should see
        # Real CLOB bid for UP = 0.60; shares = 20.0; cost = 10.0
        expected_value = 20.0 * 0.60   # = 12.00
        expected_pnl = round(expected_value - 10.0, 2)  # = +2.00

        mock_db = MagicMock()
        mock_db_trade = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_db_trade
        mock_session.return_value = mock_db

        await executor._check_single_trade_exit(trade)

    # The engine should have applied real_book_bid = 0.60 to mark PnL
    assert trade["current_share_price"] == 0.60, \
        f"Expected share price=0.60 (CLOB up_bid), got {trade['current_share_price']}"
    assert trade["current_pnl"] == expected_pnl, \
        f"Expected PnL=+${expected_pnl} from real fill, got ${trade['current_pnl']}"



# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Buffer suppresses trailing stop during grace period
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_buffer_suppresses_trailing_stop():
    """
    If trade is still within the grace period buffer (e.g. 2.0s old with 4s buffer),
    AGGRESSIVE_TRAILING_LOCK must be completely suppressed even if peak gain is reached.
    """
    executor = FastExecutor()
    executor.settings["buffer_timer_sec"] = "4.0"
    executor.settings["trailing_stop_activation_pct"] = "0.5"  # low threshold to try to arm
    executor.settings["trailing_stop_distance_pct"] = "0.5"
    executor.settings["trailing_lock_enabled"] = "true"

    # Trade entered 2 seconds ago (WITHIN 4s buffer)
    trade = make_trade(
        cost=10.0, entry_price=0.50, shares=20.0, outcome="UP",
        entry_ts=time.time() - 2.0,  # 2s old — inside buffer
        peak_pnl=0.15                # already has a peak gain
    )

    oracle = make_oracle(live_price=90200.0)
    market = make_market(up_bid=0.52, down_bid=0.48)  # slight move

    with patch("app.fast5m.executor.fast_oracle.get_asset_state", return_value=oracle), \
         patch("app.fast5m.executor.fast_markets.get_market", return_value=market), \
         patch("app.fast5m.executor.SessionLocal") as mock_session:

        mock_db = MagicMock()
        mock_db_trade = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_db_trade
        mock_session.return_value = mock_db

        await executor._check_single_trade_exit(trade)

    # Trailing stop must NOT have fired — trade still in buffer
    assert trade.get("trailing_armed") != True or not (trade.get("current_pnl", 0.0) <= 0), \
        "Trailing stop must be suppressed during grace period buffer"

    # Confirm buffer is active
    assert trade.get("is_in_buffer") is True
    assert trade.get("buffer_remaining_sec", 0.0) > 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Buffer suppresses hard stop loss during grace period
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_buffer_suppresses_hard_stop_loss():
    """
    A stop-loss-sized dip during the grace buffer must NOT close the trade.
    The engine must hold and log suppression.
    """
    executor = FastExecutor()
    executor.settings["buffer_timer_sec"] = "4.0"
    executor.settings["stop_loss_pct"] = "1.0"  # 1% SL

    # Trade entered 1.5 seconds ago (WITHIN 4s buffer)
    trade = make_trade(
        cost=25.0, entry_price=0.50, shares=50.0, outcome="UP",
        entry_ts=time.time() - 1.5,  # 1.5s old
        peak_pnl=0.0
    )

    # Market dipped: up_bid = 0.495 → PnL ≈ -$0.25 (1% loss on $25)
    oracle = make_oracle(live_price=89900.0)
    market = make_market(up_bid=0.495, down_bid=0.505, time_rem=90.0)

    closed_trades_in_db = []
    with patch("app.fast5m.executor.fast_oracle.get_asset_state", return_value=oracle), \
         patch("app.fast5m.executor.fast_markets.get_market", return_value=market), \
         patch("app.fast5m.executor.SessionLocal") as mock_session:

        mock_db = MagicMock()
        mock_db_trade = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_db_trade
        mock_session.return_value = mock_db

        await executor._check_single_trade_exit(trade)

        # DB commit must NOT be called (trade should not close)
        commit_called = mock_db.commit.called

    assert trade.get("is_in_buffer") is True, "Buffer must be active at 1.5s"
    # If commit was called, it means the trade was closed — that's the bug
    assert not commit_called, \
        "Trade must NOT be closed by HARD_STOP_LOSS while grace period buffer is active"


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Trailing lock cannot fire at negative PnL (Breakeven Guard)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trailing_lock_cannot_fire_at_negative_pnl():
    """
    AGGRESSIVE_TRAILING_LOCK must NEVER fire when unrealized_pnl <= 0.
    This was the core bug: trailing_floor = $0.01 and PnL = -$0.25 → -$0.25 < $0.01 → close!
    """
    executor = FastExecutor()
    executor.settings["buffer_timer_sec"] = "4.0"
    executor.settings["trailing_lock_enabled"] = "true"
    executor.settings["trailing_stop_activation_pct"] = "1.0"
    executor.settings["trailing_stop_distance_pct"] = "0.5"

    # Trade expired buffer (40s old), has seen a peak gain, but now deeply negative
    trade = make_trade(
        cost=10.0, entry_price=0.50, shares=20.0, outcome="UP",
        entry_ts=time.time() - 40.0,  # outside buffer
        peak_pnl=0.12  # at some point was in profit
    )

    # CLOB bid has dropped hard → shares now worth $9.75 → PnL = -$0.25
    oracle = make_oracle(live_price=89500.0)
    market = make_market(up_bid=0.4875, down_bid=0.5125, time_rem=60.0)

    resolution_recorded = []
    with patch("app.fast5m.executor.fast_oracle.get_asset_state", return_value=oracle), \
         patch("app.fast5m.executor.fast_markets.get_market", return_value=market), \
         patch("app.fast5m.executor.SessionLocal") as mock_session:

        mock_db = MagicMock()
        mock_db_trade = MagicMock()

        def capture_resolution():
            if hasattr(mock_db_trade, 'resolution'):
                resolution_recorded.append(mock_db_trade.resolution)

        mock_db.query.return_value.filter.return_value.first.return_value = mock_db_trade
        mock_session.return_value = mock_db
        mock_db.commit.side_effect = capture_resolution

        await executor._check_single_trade_exit(trade)

        # If it closed, check it was not "AGGRESSIVE_TRAILING_LOCK"
        if mock_db.commit.called and hasattr(mock_db_trade, 'resolution'):
            assert mock_db_trade.resolution != "AGGRESSIVE_TRAILING_LOCK", \
                f"CRITICAL BUG: Trailing lock fired at negative PnL! resolution={mock_db_trade.resolution}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Trailing floor is >= $0.02 (breakeven minimum, not $0.01)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trailing_floor_minimum_is_breakeven_not_penny():
    """
    trailing_floor = max(0.02, peak - giveback)
    With peak=$0.15 and giveback=$0.05, floor should be max(0.02, 0.10) = $0.10.
    Trailing stop should fire because current_pnl ($0.08) < floor ($0.10) AND pnl > 0.
    """
    executor = FastExecutor()
    executor.settings["buffer_timer_sec"] = "0.0"  # no buffer
    executor.settings["trailing_lock_enabled"] = "true"
    executor.settings["trailing_stop_activation_pct"] = "1.0"  # activates at $0.10 gain on $10
    executor.settings["trailing_stop_distance_pct"] = "0.5"   # giveback = $0.05 on $10

    trade = make_trade(
        cost=10.0, entry_price=0.50, shares=20.0, outcome="UP",
        entry_ts=time.time() - 30.0,
        peak_pnl=0.15  # was at +$0.15 profit
    )

    # Now CLOB bid = 0.504 → current value = $10.08 → current_pnl = +$0.08 (positive but below floor)
    oracle = make_oracle(live_price=90100.0)
    market = make_market(up_bid=0.504, down_bid=0.496, time_rem=60.0)

    resolution_recorded = []
    with patch("app.fast5m.executor.fast_oracle.get_asset_state", return_value=oracle), \
         patch("app.fast5m.executor.fast_markets.get_market", return_value=market), \
         patch("app.fast5m.executor.SessionLocal") as mock_session:

        mock_db = MagicMock()
        mock_db_trade = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_db_trade
        mock_session.return_value = mock_db

        await executor._check_single_trade_exit(trade)

        if mock_db.commit.called:
            resolution_recorded.append(mock_db_trade.resolution)

    expected_floor = max(0.02, round(0.15 - (10.0 * 0.005), 2))  # max(0.02, 0.10) = 0.10
    assert expected_floor == 0.10, f"Expected trailing floor $0.10, got ${expected_floor}"
    assert "AGGRESSIVE_TRAILING_LOCK" in resolution_recorded, \
        f"Trailing lock should have fired (pnl=$0.08 < floor=$0.10). Got: {resolution_recorded}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: No artificial clamping — real slippage is recorded
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_artificial_pnl_clamping_real_slippage_recorded():
    """
    In the old engine, exit PnL was force-clamped to exactly -hard_sl_dollar.
    Now it must equal (shares * real_book_bid) - cost — exposing real spread/slippage.
    """
    executor = FastExecutor()
    executor.settings["buffer_timer_sec"] = "0.0"
    executor.settings["stop_loss_pct"] = "1.0"    # 1% SL → $0.10 on $10
    executor.settings["stop_loss_dollar"] = "0.10"

    trade = make_trade(
        cost=10.0, entry_price=0.50, shares=20.0, outcome="UP",
        entry_ts=time.time() - 20.0,
        peak_pnl=0.0
    )

    # up_bid = 0.487 → value = 20 * 0.487 = $9.74 → PnL = -$0.26 (NOT exactly -$0.10)
    oracle = make_oracle(live_price=89800.0)
    market = make_market(up_bid=0.487, down_bid=0.513, time_rem=60.0)

    recorded_pnl = []
    with patch("app.fast5m.executor.fast_oracle.get_asset_state", return_value=oracle), \
         patch("app.fast5m.executor.fast_markets.get_market", return_value=market), \
         patch("app.fast5m.executor.SessionLocal") as mock_session:

        mock_db = MagicMock()
        mock_db_trade = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_db_trade
        mock_session.return_value = mock_db

        def capture_pnl():
            recorded_pnl.append(mock_db_trade.pnl)

        mock_db.commit.side_effect = capture_pnl
        await executor._check_single_trade_exit(trade)

    if mock_db.commit.called and recorded_pnl:
        actual_pnl = mock_db_trade.pnl
        # The real fill PnL must not be artificially clamped to exactly -0.10
        assert actual_pnl != -0.10, \
            f"PnL was artificially clamped to -$0.10! Real slippage should differ. Got: ${actual_pnl}"
        # Real pnl = 20 * 0.487 - 10.0 = -0.26
        expected_real_pnl = round(20.0 * 0.487 - 10.0, 2)  # -0.26
        assert actual_pnl == expected_real_pnl, \
            f"Expected real-fill PnL=${expected_real_pnl}, got ${actual_pnl}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: Epoch expiry WON resolution — full payout with real PnL
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_epoch_expiry_won_uses_real_payout():
    """
    When epoch expires and oracle is above strike (WON), exit_price = 1.00
    and PnL should be (shares * 1.00) - cost, not a synthetic target.
    """
    executor = FastExecutor()
    executor.settings["buffer_timer_sec"] = "0.0"

    trade = make_trade(
        cost=10.0, entry_price=0.55, shares=18.18, outcome="UP",
        entry_ts=time.time() - 300.0,
        peak_pnl=0.0, strike=90000.0
    )

    oracle = make_oracle(live_price=90500.0)  # above strike → WON
    market = make_market(up_bid=0.55, time_rem=1.5)  # < 3s remaining

    with patch("app.fast5m.executor.fast_oracle.get_asset_state", return_value=oracle), \
         patch("app.fast5m.executor.fast_markets.get_market", return_value=market), \
         patch("app.fast5m.executor.SessionLocal") as mock_session:

        mock_db = MagicMock()
        mock_db_trade = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_db_trade
        mock_session.return_value = mock_db

        await executor._check_single_trade_exit(trade)

    assert mock_db.commit.called, "Trade should be closed on epoch expiry"
    assert mock_db_trade.resolution == "WON"
    assert mock_db_trade.exit_price == 1.0
    expected_pnl = round(18.18 * 1.00 - 10.0, 2)  # +$8.18
    assert mock_db_trade.pnl == expected_pnl, \
        f"WON PnL should be {expected_pnl}, got {mock_db_trade.pnl}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 8: entry_ts precision — rehydrated trades use created_at, not time.time()
# ─────────────────────────────────────────────────────────────────────────────

def test_rehydrate_entry_ts_uses_created_at():
    """
    When _rehydrate_active_trade is called after daemon restart, the entry_ts
    must come from open_trade.created_at (UTC), not time.time() (which would
    reset the buffer timer to 0 and re-expose trades to early SL triggers).
    """
    executor = FastExecutor()

    # Simulate a trade created 120 seconds ago
    created_at_utc = datetime.now(timezone.utc).replace(
        second=0, microsecond=0
    )
    from datetime import timedelta
    created_at_utc = datetime.now(timezone.utc) - timedelta(seconds=120)

    mock_trade = MagicMock()
    mock_trade.id = 77
    mock_trade.asset = "ETH"
    mock_trade.market_id = "mkt_1"
    mock_trade.account_mode = "demo"
    mock_trade.question = "ETH Up?"
    mock_trade.epoch_bucket = 999
    mock_trade.side = "BUY"
    mock_trade.outcome = "UP"
    mock_trade.token_id = "tok_1"
    mock_trade.entry_price = 0.55
    mock_trade.shares = 18.18
    mock_trade.cost = 10.0
    mock_trade.strike_price = 3000.0
    mock_trade.entry_oracle_price = 3010.0
    mock_trade.delta_at_entry = 10.0
    mock_trade.confidence_score = 88.5
    mock_trade.delta_score = 25.0
    mock_trade.obi_score = 20.0
    mock_trade.momentum_score = 18.0
    mock_trade.prediction_rationale = "Test"
    mock_trade.asset_rank = 1
    mock_trade.latency_ms = 14.0
    mock_trade.created_at = created_at_utc  # has tzinfo set

    from app.db.session import SessionLocal
    with patch("app.fast5m.executor.SessionLocal") as mock_session:
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_trade]
        mock_session.return_value = mock_db

        executor._rehydrate_active_trade()

    assert 77 in executor.active_trades, "Trade 77 should be rehydrated"
    rehydrated = executor.active_trades[77]

    expected_ts = created_at_utc.timestamp()
    actual_ts = rehydrated["entry_ts"]
    age = time.time() - actual_ts

    assert abs(actual_ts - expected_ts) < 2.0, \
        f"entry_ts should match created_at ({expected_ts:.1f}), got {actual_ts:.1f} (delta={abs(actual_ts - expected_ts):.2f}s)"
    assert age > 100.0, \
        f"Trade age should be ~120s, not reset to 0. Got: {age:.1f}s"


# ─────────────────────────────────────────────────────────────────────────────
# Test 9: Telemetry fields written on close — execution_type, tx_hash, slippage
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_telemetry_fields_written_on_close():
    """
    When a trade closes (e.g., TAKE_PROFIT), telemetry columns must be populated:
    execution_type, tx_hash, exit_slippage, buffer_status, real_orderbook_bid
    """
    executor = FastExecutor()
    executor.settings["buffer_timer_sec"] = "0.0"
    executor.settings["take_profit_dollar"] = "0.10"  # low TP to trigger easily
    executor.settings["take_profit_pct"] = "1.0"

    trade = make_trade(
        cost=10.0, entry_price=0.50, shares=20.0, outcome="UP",
        entry_ts=time.time() - 30.0,
        peak_pnl=0.0, entry_oracle=90000.0
    )

    # up_bid = 0.52 → value = $10.40 → PnL = +$0.40 > tp_dollar($0.10)
    oracle = make_oracle(live_price=90200.0)
    market = make_market(up_bid=0.52, down_bid=0.48, time_rem=60.0)

    with patch("app.fast5m.executor.fast_oracle.get_asset_state", return_value=oracle), \
         patch("app.fast5m.executor.fast_markets.get_market", return_value=market), \
         patch("app.fast5m.executor.SessionLocal") as mock_session:

        mock_db = MagicMock()
        mock_db_trade = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_db_trade
        mock_session.return_value = mock_db

        await executor._check_single_trade_exit(trade)

    assert mock_db.commit.called, "TAKE_PROFIT should trigger DB commit"
    assert mock_db_trade.resolution == "TAKE_PROFIT"
    assert mock_db_trade.execution_type == "SIMULATED_ORDERBOOK"
    assert mock_db_trade.tx_hash == "SIMULATED_CLOB_ORDERBOOK"
    assert isinstance(mock_db_trade.exit_slippage, float)
    assert isinstance(mock_db_trade.real_orderbook_bid, float)
    assert mock_db_trade.real_orderbook_bid == 0.52
    assert mock_db_trade.buffer_status == "EXPIRED (CLEARED)"
