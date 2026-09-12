import pytest
from app.engine.strategy import StrategyEngine
from app.db.schemas import MarketTick
from datetime import datetime

class DummyModel:
    def predict(self, features):
        return 0.70, 0.01, "dummy_model"

class DummyModelUntrained:
    def predict(self, features):
        return 0.50, 0.50, "untrained_baseline"

class DummyModelHighUncertainty:
    def predict(self, features):
        return 0.60, 0.10, "dummy_model"

@pytest.fixture
def strategy():
    return StrategyEngine(DummyModel())

def get_tick(price=0.5, spread=0.01, ask_depth=500, bid_depth=500, bid=0.495, ask=0.505, liquidity=1000):
    return MarketTick(
        source="polymarket",
        symbol="YES",
        market_id="m1",
        event_timestamp=datetime.utcnow(),
        received_timestamp=datetime.utcnow(),
        price=price,
        bid=bid,
        ask=ask,
        spread=spread,
        volume=1000.0,
        liquidity=liquidity,
        imbalance=0.0,
        bid_depth=bid_depth,
        ask_depth=ask_depth
    )

def test_yes_edge_calculation(strategy):
    tick = get_tick(ask=0.55, bid=0.53, spread=0.02, ask_depth=1000)
    features = {"time_remaining_sec": 86400}
    # model returns 0.70 prob. Entry price is 0.55 (best_ask).
    # raw_edge = 0.70 - 0.55 = 0.15
    # spread_cost = 0.01
    # order_size = 50.0 (default in evaluate). ask_depth = 1000.
    # liquidity_impact = 50 / 1000 = 0.05. slippage_cost = 0.01 * 0.05 = 0.0005
    # net_edge = 0.15 - 0.01 - 0.0005 = 0.1395
    
    result = strategy.evaluate(tick, features, order_size=50.0)
    
    assert result["signal_type"] == "BUY"
    assert result["strategy"] == "VALUE_EDGE"
    assert result["fair_probability"] == 0.70
    assert result["entry_price"] == 0.55
    assert pytest.approx(result["raw_edge"], 0.001) == 0.15
    assert pytest.approx(result["spread_cost"], 0.001) == 0.01
    assert pytest.approx(result["slippage_cost"], 0.001) == 0.0005
    assert pytest.approx(result["net_edge"], 0.001) == 0.1395

def test_no_forced_trade_negative_edge(strategy):
    tick = get_tick(ask=0.75, bid=0.73, spread=0.02, ask_depth=1000)
    features = {"time_remaining_sec": 86400}
    # model returns 0.70 prob. entry = 0.75. Edge is negative!
    result = strategy.evaluate(tick, features, order_size=50.0)
    assert result["signal_type"] == "SKIP"
    assert "No statistical edge" in result["reason"]

def test_insufficient_liquidity(strategy):
    # order_size is 50.0. ask_depth is 20.0
    tick = get_tick(ask=0.55, ask_depth=20.0)
    features = {"time_remaining_sec": 86400}
    result = strategy.evaluate(tick, features, order_size=50.0)
    assert result["signal_type"] == "SKIP"
    assert "Insufficient liquidity for order size" in result["reason"]

def test_market_quality_rejection(strategy):
    # time_remaining_sec < 3600 AND empty orderbook
    tick = get_tick(ask_depth=0, bid_depth=0)
    features = {"time_remaining_sec": 1800} 
    result = strategy.evaluate(tick, features)
    assert result["signal_type"] == "SKIP"
    assert "Rejected Quality" in result["reason"]
    assert result["market_quality_status"] == "Reject"

def test_untrained_model_skip():
    strat = StrategyEngine(DummyModelUntrained())
    tick = get_tick()
    features = {"time_remaining_sec": 86400}
    result = strat.evaluate(tick, features)
    assert result["signal_type"] == "SKIP"
    assert "Model not trained" in result["reason"]

def test_high_uncertainty_skip():
    strat = StrategyEngine(DummyModelHighUncertainty())
    tick = get_tick()
    features = {"time_remaining_sec": 86400}
    result = strat.evaluate(tick, features)
    assert result["signal_type"] == "SKIP"
    assert "Uncertainty too high" in result["reason"]

def test_dynamic_threshold(strategy):
    # Wide spread dynamically increases threshold.
    # threshold = 0.02 (default) + 0.01 (spread > 0.05) = 0.03
    tick = get_tick(ask=0.60, bid=0.54, spread=0.06, ask_depth=1000)
    features = {"time_remaining_sec": 86400}
    # prob = 0.70. ask = 0.60. raw_edge = 0.10.
    # spread_cost = 0.03.
    # net_edge = 0.10 - 0.03 = 0.07. 
    # 0.07 >= 0.03, so it should still buy, but let's check the recorded threshold
    result = strategy.evaluate(tick, features)
    assert result["signal_type"] == "BUY"
    assert result["threshold"] > 0.02  # Proves dynamic threshold increased
