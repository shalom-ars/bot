import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from app.btc5m.strategy import BTC5MStrategy
from app.btc5m.settings_manager import DEFAULT_SETTINGS, DEFAULT_SETTINGS_INSTANCE_2
from app.db.models import BTC5MTrade

def test_slot_mode_settings_defaults():
    assert DEFAULT_SETTINGS.get("slot_mode") == "single_5m"
    assert DEFAULT_SETTINGS.get("account_mode") == "demo"
    assert DEFAULT_SETTINGS.get("mode") == "fixed_dollar"
    assert float(DEFAULT_SETTINGS.get("stop_loss_ratio")) == 1.00

    assert DEFAULT_SETTINGS_INSTANCE_2.get("slot_mode") == "single_5m"
    assert DEFAULT_SETTINGS_INSTANCE_2.get("account_mode") == "demo"

def test_risk_reward_1_to_2_math():
    strat = BTC5MStrategy(
        instance_id="instance_1",
        settings_dict={
            "take_profit_delta": 0.20,
            "stop_loss_ratio": 0.50,
            "max_take_profit": 0.95,
            "mode": "dynamic"
        }
    )
    features = {
        "mid_price": 0.50,
        "bid": 0.49,
        "ask": 0.51,
        "spread": 0.02,
        "short_momentum_1m": 0.0,
        "bid_ask_imbalance": 0.0
    }
    # is_yes=True
    ep, fair, rr, edge, sl, tp, risk, pos_size = strat._calc_edge_and_rr(
        is_yes=True,
        features=features,
        current_balance=500.0,
        btc_price=95100.0,
        p2b=95000.0,
        time_remaining_sec=200.0
    )
    # Raw target profit is 0.20 -> reward = tp - ep = 0.20
    # Stop loss is sl_ratio = 0.50 of reward -> risk = ep - sl = 0.10
    # Strict 1:2 Risk-to-Reward ratio on prices:
    raw_rr = (tp - ep) / (ep - sl)
    assert raw_rr == pytest.approx(2.0, rel=1e-2)
    assert ep == pytest.approx(0.51, rel=1e-2)
    assert tp == pytest.approx(0.71, rel=1e-2)
    assert sl == pytest.approx(0.41, rel=1e-2)
    # Net planned RR after accounting for spread friction (0.19 / 0.11)
    assert rr == pytest.approx(1.727, rel=1e-2)

def test_single_5m_slot_enforcement():
    strat = BTC5MStrategy(
        instance_id="instance_1",
        slot_mode="single_5m",
        settings_dict={
            "slot_mode": "single_5m",
            "mode": "dynamic",
            "only_short": False,
            "side_bias": "ANY",
            "max_time_remaining": 300.0,
            "min_time_remaining": 30.0,
            "min_entry_score": 50.0,
            "min_net_edge": 0.005,
            "min_rr": 1.5,
            "take_profit_delta": 0.20,
            "stop_loss_ratio": 0.50
        }
    )
    features = {
        "mid_price": 0.55,
        "bid": 0.54,
        "ask": 0.56,
        "spread": 0.02,
        "bid_depth": 5000.0,
        "ask_depth": 5000.0,
        "rolling_volatility": 0.001,
        "time_remaining_sec": 200.0,
        "short_momentum_1m": 0.05,
        "bid_ask_imbalance": 0.2
    }

    # 1. No prior trades -> passes single slot check (returns ENTER)
    with patch("app.db.session.SessionLocal") as mock_sl:
        mock_db = MagicMock()
        mock_sl.return_value = mock_db
        mock_db.query().filter().all.return_value = []

        signal = strat.evaluate(
            market_id="mkt_1",
            condition_id="cond_1",
            question="BTC 5M Up or Down?",
            yes_token_id="yes_tok",
            no_token_id="no_tok",
            features=features,
            orderbook_timestamp=datetime.now(timezone.utc),
            btc_price=95200.0,
            price_to_beat=95000.0,
            current_balance=500.0
        )
        assert signal.state in ("ENTER", "READY")

    # 2. Market already traded once -> blocked by single_5m rule
    existing_trade = MagicMock(spec=BTC5MTrade)
    existing_trade.market_id = "mkt_1"
    existing_trade.instance_id = "instance_1"
    existing_trade.status = "CLOSED"
    existing_trade.time_remaining_at_entry = 240.0

    with patch("app.db.session.SessionLocal") as mock_sl:
        mock_db = MagicMock()
        mock_sl.return_value = mock_db
        # open_trades = [], existing_market_trades = [existing_trade]
        mock_db.query().filter().all.side_effect = [[], [existing_trade]]

        signal2 = strat.evaluate(
            market_id="mkt_1",
            condition_id="cond_1",
            question="BTC 5M Up or Down?",
            yes_token_id="yes_tok",
            no_token_id="no_tok",
            features=features,
            orderbook_timestamp=datetime.now(timezone.utc),
            btc_price=95200.0,
            price_to_beat=95000.0,
            current_balance=500.0
        )
        assert signal2.state == "SKIP"
        assert "Single trade per 5M candle already executed" in signal2.reason

def test_double_slot_2_5m_enforcement():
    strat = BTC5MStrategy(
        instance_id="instance_2",
        slot_mode="double_slot_2.5m",
        settings_dict={
            "slot_mode": "double_slot_2.5m",
            "mode": "dynamic",
            "only_short": False,
            "side_bias": "ANY",
            "max_time_remaining": 300.0,
            "min_time_remaining": 30.0,
            "min_entry_score": 50.0,
            "min_net_edge": 0.005,
            "min_rr": 1.5,
            "take_profit_delta": 0.20,
            "stop_loss_ratio": 0.50
        }
    )

    # Slot 1: time_remaining = 240s (> 150s)
    features_slot1 = {
        "mid_price": 0.55,
        "bid": 0.54,
        "ask": 0.56,
        "spread": 0.02,
        "bid_depth": 5000.0,
        "ask_depth": 5000.0,
        "rolling_volatility": 0.001,
        "time_remaining_sec": 240.0,
        "short_momentum_1m": 0.05,
        "bid_ask_imbalance": 0.2
    }

    # Case A: Slot 1 empty -> trade allowed
    with patch("app.db.session.SessionLocal") as mock_sl:
        mock_db = MagicMock()
        mock_sl.return_value = mock_db
        mock_db.query().filter().all.return_value = []

        sig1 = strat.evaluate(
            market_id="mkt_1",
            condition_id="cond_1",
            question="BTC 5M Up or Down?",
            yes_token_id="yes_tok",
            no_token_id="no_tok",
            features=features_slot1,
            orderbook_timestamp=datetime.now(timezone.utc),
            btc_price=95200.0,
            price_to_beat=95000.0,
            current_balance=500.0
        )
        assert sig1.state in ("ENTER", "READY")

    # Case B: Slot 1 already traded -> next evaluation in Slot 1 (>150s) skipped
    trade_slot1 = MagicMock(spec=BTC5MTrade)
    trade_slot1.market_id = "mkt_1"
    trade_slot1.instance_id = "instance_2"
    trade_slot1.status = "OPEN"
    trade_slot1.time_remaining_at_entry = 240.0

    with patch("app.db.session.SessionLocal") as mock_sl:
        mock_db = MagicMock()
        mock_sl.return_value = mock_db
        # open_trades = [trade_slot1], existing_market_trades = [trade_slot1]
        mock_db.query().filter().all.side_effect = [[trade_slot1], [trade_slot1]]

        sig1_blocked = strat.evaluate(
            market_id="mkt_1",
            condition_id="cond_1",
            question="BTC 5M Up or Down?",
            yes_token_id="yes_tok",
            no_token_id="no_tok",
            features=features_slot1,
            orderbook_timestamp=datetime.now(timezone.utc),
            btc_price=95200.0,
            price_to_beat=95000.0,
            current_balance=500.0
        )
        assert sig1_blocked.state == "SKIP"
        assert "Slot 1 (first 2.5m) already traded" in sig1_blocked.reason

    # Case C: Move into Slot 2 (120s <= 150s) -> allowed even though Slot 1 was traded!
    features_slot2 = dict(features_slot1)
    features_slot2["time_remaining_sec"] = 120.0

    with patch("app.db.session.SessionLocal") as mock_sl:
        mock_db = MagicMock()
        mock_sl.return_value = mock_db
        # open_trades = [trade_slot1], existing_market_trades = [trade_slot1]
        mock_db.query().filter().all.side_effect = [[trade_slot1], [trade_slot1]]

        sig2 = strat.evaluate(
            market_id="mkt_1",
            condition_id="cond_1",
            question="BTC 5M Up or Down?",
            yes_token_id="yes_tok",
            no_token_id="no_tok",
            features=features_slot2,
            orderbook_timestamp=datetime.now(timezone.utc),
            btc_price=95200.0,
            price_to_beat=95000.0,
            current_balance=500.0
        )
        assert sig2.state in ("ENTER", "READY")

    # Case D: Slot 2 already traded -> second trade in Slot 2 skipped
    trade_slot2 = MagicMock(spec=BTC5MTrade)
    trade_slot2.market_id = "mkt_1"
    trade_slot2.instance_id = "instance_2"
    trade_slot2.status = "OPEN"
    trade_slot2.time_remaining_at_entry = 120.0

    with patch("app.db.session.SessionLocal") as mock_sl:
        mock_db = MagicMock()
        mock_sl.return_value = mock_db
        # open_trades = [trade_slot1, trade_slot2], existing_market_trades = [trade_slot1, trade_slot2]
        mock_db.query().filter().all.side_effect = [
            [trade_slot1, trade_slot2],
            [trade_slot1, trade_slot2]
        ]

        sig2_blocked = strat.evaluate(
            market_id="mkt_1",
            condition_id="cond_1",
            question="BTC 5M Up or Down?",
            yes_token_id="yes_tok",
            no_token_id="no_tok",
            features=features_slot2,
            orderbook_timestamp=datetime.now(timezone.utc),
            btc_price=95200.0,
            price_to_beat=95000.0,
            current_balance=500.0
        )
        assert sig2_blocked.state == "SKIP"
        assert "Slot 2 (second 2.5m) already traded" in sig2_blocked.reason
