import pytest
from app.fast5m.oracle import AssetOracleState, fast_oracle
from app.fast5m.scorer import FastScorer, ScoredAsset
from app.fast5m.executor import FastExecutor

def test_oracle_technical_indicators():
    state = AssetOracleState(symbol="BTC", strike_price=90000.0)
    # Simulate upward trend
    for p in range(90000, 90200, 10):
        state.update_price(float(p), latency_ms=15.0)

    assert state.rsi_14 > 50.0
    assert state.live_price == 90190.0
    assert state.delta == 190.0
    assert state.bb_pct_b >= 0.5
    assert state.ema_trend >= 0.0

def test_fast_scorer_ranking():
    scorer = FastScorer()
    # Inject prices into fast_oracle
    state_btc = fast_oracle.get_asset_state("BTC")
    state_btc.strike_price = 90000.0
    for p in range(90000, 90300, 10):
        state_btc.update_price(float(p), latency_ms=14.0)

    state_eth = fast_oracle.get_asset_state("ETH")
    state_eth.strike_price = 3000.0
    state_eth.update_price(3000.0, latency_ms=18.0)

    results = scorer.score_all_assets()
    assert len(results) > 0
    btc_scored = next((r for r in results if r.asset == "BTC"), None)
    assert btc_scored is not None
    assert btc_scored.direction == "UP"
    assert btc_scored.composite_score > 50.0
    assert btc_scored.delta_score > 0
    assert btc_scored.momentum_score > 0

def test_executor_balance_and_micro_profit_locking():
    executor = FastExecutor()
    # Check total balance setting
    bal = float(executor.settings.get("total_balance_usd", 300.0))
    assert bal == 300.0
    
    # Check micro-profit scalp target & trailing locking parameters
    tp = float(executor.settings.get("take_profit_dollar", 0.40))
    sl = float(executor.settings.get("stop_loss_dollar", 0.60))
    min_lock = float(executor.settings.get("min_profit_to_lock", 0.15))
    giveback = float(executor.settings.get("reversal_giveback_dollar", 0.06))
    
    assert tp == 0.40
    assert sl == 0.60
    assert min_lock == 0.15
    assert giveback == 0.06
    assert executor.settings.get("trailing_lock_enabled") == "true"
    assert executor.settings.get("reversal_lock_enabled") == "true"
