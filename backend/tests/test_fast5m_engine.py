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
    
    # Check strict 1:1 Risk-to-Reward ratio ($0.50 TP / $0.50 SL)
    tp = float(executor.settings.get("take_profit_dollar", 0.50))
    sl = float(executor.settings.get("stop_loss_dollar", 0.50))
    min_lock = float(executor.settings.get("min_profit_to_lock", 0.15))
    giveback = float(executor.settings.get("reversal_giveback_dollar", 0.06))
    
    assert tp == 0.50
    assert sl == 0.50
    assert tp == sl # Strict 1:1 Risk-to-Reward symmetry
    assert min_lock == 0.15
    assert giveback == 0.06
    assert executor.settings.get("trailing_lock_enabled") == "true"
    assert executor.settings.get("reversal_lock_enabled") == "true"

def test_executor_save_and_restore_defaults():
    executor = FastExecutor()
    # Modify settings to custom configuration
    executor.update_settings({
        "take_profit_dollar": "0.75",
        "stop_loss_dollar": "0.50",
        "filter_delta_weight": "45.0",
        "filter_rsi_enabled": "false"
    })
    assert float(executor.settings["take_profit_dollar"]) == 0.75
    
    # Save as custom default baseline
    defaults = executor.save_as_default()
    assert float(defaults["take_profit_dollar"]) == 0.75
    assert float(defaults["filter_delta_weight"]) == 45.0
    assert defaults["filter_rsi_enabled"] == "false"

    # Now change active settings to something else
    executor.update_settings({"take_profit_dollar": "1.20"})
    assert float(executor.settings["take_profit_dollar"]) == 1.20

    # Restore to default
    restored = executor.restore_defaults()
    assert float(restored["take_profit_dollar"]) == 0.75
    assert float(restored["filter_delta_weight"]) == 45.0
    assert restored["filter_rsi_enabled"] == "false"


def test_multi_pair_execution_and_aggressive_trailing():
    executor = FastExecutor()
    assert int(executor.settings["max_active_pools"]) == 3
    assert float(executor.settings["multi_pair_min_score"]) == 90.0
    assert float(executor.settings["trailing_stop_activation_pct"]) == 1.0
    assert float(executor.settings["trailing_stop_distance_pct"]) == 0.5
    assert float(executor.settings["max_portfolio_margin_pct"]) == 30.0

    # Test active_trades dictionary and property
    assert len(executor.get_active_trades()) == 0
    assert executor.active_trade is None

    # Simulate opening 2 concurrent trades
    executor.active_trades[101] = {
        "id": 101, "asset": "BTC", "outcome": "UP", "cost": 10.0,
        "shares": 20.0, "entry_price": 0.50, "strike_price": 90000.0,
        "confidence_score": 92.5
    }
    executor.active_trades[102] = {
        "id": 102, "asset": "ETH", "outcome": "DOWN", "cost": 10.0,
        "shares": 20.0, "entry_price": 0.50, "strike_price": 3100.0,
        "confidence_score": 91.0
    }

    assert len(executor.get_active_trades()) == 2
    assert executor.active_trade["id"] == 102 # Latest trade


def test_wallet_manager_connect_and_mode_switching():
    from app.fast5m.wallet import wallet_manager

    # Test initial demo state
    status = wallet_manager.get_status()
    assert status["account_mode"] == "demo"
    assert status["chain_id"] == 137

    # Test connect with valid Polygon address & mock signer key
    dummy_addr = "0x1234567890123456789012345678901234567890"
    dummy_pk = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    res = wallet_manager.connect(address=dummy_addr, private_key=dummy_pk)
    assert res["success"] is True
    assert wallet_manager.is_connected is True
    assert wallet_manager.has_signer is True

    # Test mode toggle
    mode_res = wallet_manager.set_mode("live")
    assert mode_res["success"] is True
    assert wallet_manager.account_mode == "live"

    # Test disconnect
    dc_res = wallet_manager.disconnect()
    assert dc_res["success"] is True
    assert wallet_manager.is_connected is False
    assert wallet_manager.account_mode == "demo"


