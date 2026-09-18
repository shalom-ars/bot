import pytest
import math
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

from app.btc5m.strategy import BTC5MStrategy, _compute_fair_probability
from app.btc5m.engine import BTC5MEngine
from app.db.models import BTC5MTrade, BTC5MPriceHistory

def test_no_fair_probability_time_decay():
    """
    Verify that as time remaining decreases (tau shrinks), a negative BTC-P2B delta
    concentrates NO probability much higher due to Brownian motion scaling.
    """
    btc_price = 95000.0
    p2b = 95050.0  # BTC is $50 below P2B
    market_price = 0.50

    # At 280s remaining (early candle), uncertainty is higher
    fair_yes_280 = _compute_fair_probability(
        price=market_price,
        momentum=0.0,
        imbalance=0.0,
        btc_price=btc_price,
        p2b=p2b,
        time_remaining_sec=280.0
    )
    fair_no_280 = 1.0 - fair_yes_280

    # At 30s remaining (late candle), resolution certainty is much higher
    fair_yes_30 = _compute_fair_probability(
        price=market_price,
        momentum=0.0,
        imbalance=0.0,
        btc_price=btc_price,
        p2b=p2b,
        time_remaining_sec=30.0
    )
    fair_no_30 = 1.0 - fair_yes_30

    # Both must heavily favor NO because BTC is $50 under P2B
    assert fair_no_280 > 0.65
    assert fair_no_30 > 0.90
    # Late candle must have strictly higher NO probability than early candle
    assert fair_no_30 > fair_no_280

def test_spot_btc_momentum_boosts_no():
    """
    Verify that negative 1m spot BTC momentum reinforces fair NO probability.
    """
    btc_price = 95000.0
    p2b = 95010.0  # Slight $10 drop
    
    # Flat momentum
    yes_flat = _compute_fair_probability(
        price=0.50,
        momentum=0.0,
        imbalance=0.0,
        btc_price=btc_price,
        p2b=p2b,
        time_remaining_sec=150.0,
        btc_momentum_1m=0.0
    )
    # Spot BTC dropping rapidly (-0.1% or ~$95 drop in 1m)
    yes_dump = _compute_fair_probability(
        price=0.50,
        momentum=0.0,
        imbalance=0.0,
        btc_price=btc_price,
        p2b=p2b,
        time_remaining_sec=150.0,
        btc_momentum_1m=-0.001
    )

    no_flat = 1.0 - yes_flat
    no_dump = 1.0 - yes_dump

    assert no_dump > no_flat

def test_candle_open_stabilization_gate():
    """
    Verify that trades with time_remaining > max_time_remaining (default 240s)
    are skipped to prevent premature entry on candle open noise.
    """
    strategy = BTC5MStrategy(settings_dict={
        "min_entry_score": 50.0,
        "min_net_edge": 0.01,
        "min_time_remaining": 30.0,
        "max_time_remaining": 240.0,
        "max_spread": 0.10,
        "min_liquidity": 10.0,
        "min_rr": 1.0
    })

    # High time remaining (285s) -> Early candle open noise
    features_early = {
        "time_remaining_sec": 285.0,
        "mid_price": 0.50,
        "bid": 0.49,
        "ask": 0.51,
        "spread": 0.02,
        "bid_depth": 500.0,
        "ask_depth": 500.0,
        "short_momentum_1m": 0.0,
        "bid_ask_imbalance": 0.0,
        "ob_pressure": 0.0,
        "rolling_volatility": 0.01,
        "btc_momentum_1m": -0.001
    }

    with patch("app.db.session.SessionLocal") as mock_db:
        mock_session = MagicMock()
        mock_db.return_value = mock_session
        mock_session.query.return_value.filter.return_value.count.return_value = 0

        signal_early = strategy.evaluate(
            market_id="mkt_early",
            condition_id="cond_early",
            question="Will BTC be UP or DOWN?",
            yes_token_id="yes_token",
            no_token_id="no_token",
            features=features_early,
            orderbook_timestamp=datetime.now(timezone.utc),
            btc_price=95000.0,
            price_to_beat=95050.0,
            current_balance=500.0
        )

        assert signal_early.state == "SKIP"
        assert any("Candle open stabilization" in flag for flag in signal_early.skip_flags)

        # Stabilized candle (180s remaining) -> Gate should pass
        features_stable = dict(features_early)
        features_stable["time_remaining_sec"] = 180.0

        signal_stable = strategy.evaluate(
            market_id="mkt_stable",
            condition_id="cond_stable",
            question="Will BTC be UP or DOWN?",
            yes_token_id="yes_token",
            no_token_id="no_token",
            features=features_stable,
            orderbook_timestamp=datetime.now(timezone.utc),
            btc_price=95000.0,
            price_to_beat=95050.0,
            current_balance=500.0
        )

        assert not any("Candle open stabilization" in flag for flag in signal_stable.skip_flags)
        assert signal_stable.predicted_side == "NO"

@pytest.mark.asyncio
async def test_wick_resistant_stop_loss():
    """
    Verify that open NO trade does not trigger early SL if:
    1. Trade age < 15 seconds (grace period against entry-block wick)
    2. Trade age >= 15s but mid_price does not confirm the stop breach.
    And triggers when both age >= 15s and mid_price confirms.
    """
    from app.db.models import BTC5MMarket, BTC5MSetting
    engine = BTC5MEngine()
    engine.risk_manager.is_paused = False
    
    # 1. Trade entered only 5 seconds ago
    recent_entry = datetime.now(timezone.utc) - timedelta(seconds=5)
    trade = BTC5MTrade(
        id=101,
        market_id="test_market_101",
        condition_id="cond_101",
        yes_token_id="token_yes",
        side="SELL",
        locked_predicted_side="NO",
        entry_price=0.60,
        stop_loss_price=0.45,
        hard_stop_price=0.30,
        planned_risk=20.0,
        take_profit_price=0.85,
        quantity=100.0,
        position_size=60.0,
        entry_time=recent_entry,
        status="OPEN"
    )

    # NO best bid is 0.40 (below SL 0.45, but above hard stop 0.30)
    # For NO, best_bid = 1.0 - last_hist.best_ask
    # If last_hist.best_ask = 0.60, best_bid = 0.40
    # mid_price = 1.0 - (0.50 + 0.60)/2 = 0.45
    hist_wick = BTC5MPriceHistory(
        market_id="test_market_101",
        best_bid=0.50,
        best_ask=0.60,  # NO bid = 0.40
        timestamp=datetime.now(timezone.utc)
    )

    current_hist = [hist_wick]

    with patch("app.btc5m.engine.SessionLocal") as mock_db, \
         patch("aiohttp.ClientSession.get") as mock_get:
        
        mock_session = MagicMock()
        mock_db.return_value = mock_session

        def mock_query(model):
            q = MagicMock()
            if model == BTC5MTrade:
                q.filter.return_value.all.return_value = [trade]
            elif model == BTC5MMarket:
                q.filter.return_value.first.return_value = None
            elif model == BTC5MPriceHistory:
                q.filter.return_value.order_by.return_value.first.return_value = current_hist[0]
            elif model == BTC5MSetting:
                q.filter.return_value.all.return_value = []
            else:
                q.filter.return_value.all.return_value = []
                q.filter.return_value.first.return_value = None
            return q

        mock_session.query.side_effect = mock_query

        # Mock Gamma API response indicating market is still open (closed: false)
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=[{"markets": [{"conditionId": "cond_101", "closed": False, "outcomes": ["YES", "NO"], "outcomePrices": ["0.6", "0.4"]}]}])
        mock_get.return_value.__aenter__.return_value = mock_resp

        # Run settle trades
        await engine._settle_trades()

        # Trade should NOT be closed because trade is in EXIT_REVIEW confirmation period
        assert trade.status == "OPEN"

        # Now simulate trade age = 25 seconds, but mid_price = 0.51 (above SL + 0.03 = 0.48)
        old_entry = datetime.now(timezone.utc) - timedelta(seconds=25)
        trade.entry_time = old_entry
        # Single-tick wick: ask jumped to 0.60 (NO bid 0.40 <= 0.45), but bid is 0.38
        # mid_price for NO = 1.0 - (0.38 + 0.60)/2 = 0.51 (> 0.48)
        hist_unconfirmed = BTC5MPriceHistory(
            market_id="test_market_101",
            best_bid=0.38,
            best_ask=0.60,
            timestamp=datetime.now(timezone.utc)
        )
        current_hist[0] = hist_unconfirmed

        await engine._settle_trades()
        # Should NOT be closed because mid_price did not confirm
        assert trade.status == "OPEN"

        # Now simulate confirmed breakdown:
        # ask jumped to 0.65 (NO bid 0.35 <= 0.45) AND bid is 0.55
        # mid_price for NO = 1.0 - (0.55 + 0.65)/2 = 0.40 (<= 0.48 confirmed)
        # Advance exit_review_started_at past confirmation threshold (>= 10s)
        trade.exit_review_started_at = datetime.now(timezone.utc) - timedelta(seconds=15)
        trade.hard_stop_price = 0.36  # With NO bid 0.35 <= 0.36, also triggers confirmed hard safety stop
        hist_confirmed = BTC5MPriceHistory(
            market_id="test_market_101",
            best_bid=0.55,
            best_ask=0.65,
            timestamp=datetime.now(timezone.utc)
        )
        current_hist[0] = hist_confirmed

        await engine._settle_trades()
        # Should now trigger EARLY_SL
        assert trade.status == "CLOSED"
        assert trade.resolution == "EARLY_SL"

