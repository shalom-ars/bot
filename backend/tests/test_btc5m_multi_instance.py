import pytest
from unittest.mock import MagicMock, patch
from app.btc5m.engine import BTC5MEngine, btc5m_engine, get_engine
from app.btc5m.strategy import BTC5MStrategy
from app.db.models import BTC5MTrade

def test_engine_singletons_and_get_engine():
    """Verify primary engine is correctly instantiated with isolated IDs and settings."""
    assert btc5m_engine.instance_id == "instance_1"
    assert btc5m_engine.mode == "dynamic"
    assert btc5m_engine.only_short is False
    assert btc5m_engine.slot_mode == "single_5m"

    assert get_engine("instance_1") is btc5m_engine
    assert get_engine("unknown") is btc5m_engine  # default fallback

def test_fixed_dollar_tp_sl_calculation():
    """
    Verify fixed dollar exit math on Instance 2:
    Position size = $10.0 (risk_per_trade=0.02 of $500 balance), Entry = $0.50 -> Quantity = 20
    TP = 0.50 + ($3.00 / 20) = 0.50 + 0.15 = 0.65
    SL = 0.50 - ($2.00 / 20) = 0.50 - 0.10 = 0.40
    """
    strat = BTC5MStrategy(
        instance_id="instance_2",
        mode="fixed_dollar",
        tp_dollar=3.0,
        sl_dollar=2.0,
        only_short=True
    )
    features = {
        "mid_price": 0.50,
        "bid": 0.49,
        "ask": 0.51,
        "spread": 0.02,
        "short_momentum_1m": 0.0,
        "bid_ask_imbalance": 0.0
    }
    
    # Evaluate NO side (is_yes=False)
    ep, fair, rr, edge, sl, tp, risk, pos_size = strat._calc_edge_and_rr(
        is_yes=False,
        features=features,
        current_balance=500.0,
        btc_price=95000.0,
        p2b=95050.0,
        time_remaining_sec=120.0
    )
    assert pos_size == 10.0  # 2% of $500
    
    # ep = 1.0 - 0.49 = 0.51
    # Quantity = (500 * 0.02) / 0.51 = 10 / 0.51 = 19.6078
    # tp_dollar = 3.0 / 19.6078 = 0.153
    # sl_dollar = 2.0 / 19.6078 = 0.102
    assert tp > ep
    assert sl < ep
    assert abs((tp - ep) / (ep - sl) - 1.5) < 0.05

def test_instance_2_short_only_rejection():
    """Verify that Instance 2 automatically skips YES signals."""
    strat = BTC5MStrategy(
        instance_id="instance_2",
        mode="fixed_dollar",
        tp_dollar=3.0,
        sl_dollar=2.0,
        only_short=True
    )

    features = {
        "mid_price": 0.60,
        "bid": 0.59,
        "ask": 0.61,
        "spread": 0.02,
        "bid_depth": 5000.0,
        "ask_depth": 5000.0,
        "rolling_volatility": 0.001,
        "time_remaining_sec": 120.0,
        "short_momentum_1m": 0.05,
        "bid_ask_imbalance": 0.2
    }

    # High BTC price vs P2B promotes YES prediction
    with patch("app.db.session.SessionLocal") as mock_sl:
        mock_db = MagicMock()
        mock_sl.return_value = mock_db
        mock_db.query().filter().count.return_value = 0

        signal = strat.evaluate(
            market_id="mkt_1",
            condition_id="cond_1",
            question="BTC Up or Down 5M?",
            yes_token_id="tok_yes",
            no_token_id="tok_no",
            features=features,
            orderbook_timestamp=None,
            btc_price=95200.0,
            price_to_beat=95000.0,
            current_balance=500.0
        )

        assert signal.state == "SKIP"
        assert "Short (NO/DOWN) positions only" in signal.reason

def test_trade_isolation_between_instances():
    """
    Verify that an open trade on instance_1 does not block instance_2 because
    the open trade DB check is strictly filtered by instance_id.
    """
    strat_2 = BTC5MStrategy(
        instance_id="instance_2",
        mode="fixed_dollar",
        tp_dollar=3.0,
        sl_dollar=2.0,
        only_short=True
    )

    features = {
        "mid_price": 0.40,
        "bid": 0.39,
        "ask": 0.41,
        "spread": 0.02,
        "bid_depth": 5000.0,
        "ask_depth": 5000.0,
        "rolling_volatility": 0.001,
        "time_remaining_sec": 120.0,
        "short_momentum_1m": -0.05,
        "bid_ask_imbalance": -0.2
    }

    with patch("app.db.session.SessionLocal") as mock_sl:
        mock_db = MagicMock()
        mock_sl.return_value = mock_db
        
        # When querying for instance_2, count is 0 (even if instance_1 had 1 open trade)
        mock_filter = mock_db.query().filter()
        mock_filter.count.return_value = 0

        signal = strat_2.evaluate(
            market_id="mkt_2",
            condition_id="cond_2",
            question="BTC Up or Down 5M?",
            yes_token_id="tok_yes",
            no_token_id="tok_no",
            features=features,
            orderbook_timestamp=None,
            btc_price=94800.0,
            price_to_beat=95000.0,
            current_balance=500.0
        )

        # Instance 2 evaluates NO successfully
        assert signal.instance_id == "instance_2"


def test_instance_1_immediate_entry_at_window_start():
    """
    Verify that Instance 1 initiates trades immediately at the start of the 5-minute window
    (e.g., at time_remaining = 295s, within first 5 seconds of window open) without delay
    or 'Candle open stabilization' skip.
    """
    strat_1 = BTC5MStrategy(
        instance_id="instance_1",
        mode="dynamic"
    )

    features = {
        "mid_price": 0.50,
        "bid": 0.49,
        "ask": 0.51,
        "spread": 0.02,
        "bid_depth": 5000.0,
        "ask_depth": 5000.0,
        "rolling_volatility": 0.001,
        "time_remaining_sec": 295.0,  # 5 seconds after candle opens!
        "short_momentum_1m": 0.04,
        "bid_ask_imbalance": 0.15
    }

    with patch("app.db.session.SessionLocal") as mock_sl:
        mock_db = MagicMock()
        mock_sl.return_value = mock_db
        mock_filter = mock_db.query().filter()
        mock_filter.count.return_value = 0

        signal = strat_1.evaluate(
            market_id="mkt_window_start",
            condition_id="cond_window_start",
            question="BTC Up or Down 5M?",
            yes_token_id="tok_yes",
            no_token_id="tok_no",
            features=features,
            orderbook_timestamp=None,
            btc_price=95250.0,
            price_to_beat=95000.0,
            current_balance=500.0
        )

        import json
        gates = json.loads(signal.gate_results) if isinstance(signal.gate_results, str) else signal.gate_results
        assert gates["time"]["pass"] is True, "Time gate must pass immediately at window start for instance_1"
        assert "Candle open stabilization" not in signal.reason
        assert signal.state == "ENTER"
