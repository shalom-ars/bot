import pytest
from app.db.session import engine, ensure_fast5m_schema
ensure_fast5m_schema(engine)
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


def test_emergency_stop_start_and_demo_reset():
    from app.fast5m.executor import FastExecutor

    executor = FastExecutor()
    executor.settings["auto_trading_enabled"] = "true"

    # Seed mock active trade
    executor.active_trades[999] = {
        "id": 999,
        "asset": "BTC",
        "outcome": "UP",
        "cost": 10.0,
        "current_pnl": 0.15,
        "peak_pnl": 0.20
    }
    assert len(executor.get_active_trades()) == 1

    # Test Emergency Stop
    stop_res = executor.emergency_stop()
    assert stop_res["status"] == "success"
    assert stop_res["auto_trading_enabled"] is False
    assert len(executor.get_active_trades()) == 0
    assert executor.settings["auto_trading_enabled"] == "false"

    # Test Emergency Start
    start_res = executor.emergency_start()
    assert start_res["status"] == "success"
    assert start_res["auto_trading_enabled"] is True
    assert executor.settings["auto_trading_enabled"] == "true"

    # Test Reset Demo Account preserves live trades and deletes only demo trades
    from app.db.session import SessionLocal
    from app.db.models import Fast5MTrade
    
    db = SessionLocal()
    try:
        demo_t = Fast5MTrade(
            asset="ETH", market_id="mkt_demo", question="ETH Up?", epoch_bucket=100,
            outcome="UP", token_id="tok_1", entry_price=0.5, shares=20, cost=10.0,
            strike_price=2000.0, entry_oracle_price=2005.0, delta_at_entry=5.0,
            confidence_score=85.0, status="CLOSED", account_mode="demo", pnl=0.5
        )
        live_t = Fast5MTrade(
            asset="BTC", market_id="mkt_live", question="BTC Up?", epoch_bucket=100,
            outcome="UP", token_id="tok_2", entry_price=0.5, shares=20, cost=10.0,
            strike_price=60000.0, entry_oracle_price=60050.0, delta_at_entry=50.0,
            confidence_score=92.0, status="CLOSED", account_mode="live", pnl=1.2
        )
        db.add(demo_t)
        db.add(live_t)
        db.commit()
    finally:
        db.close()

    reset_res = executor.reset_demo_account()
    assert reset_res["status"] == "success"
    assert reset_res["balance"] == 300.0
    assert executor.settings["total_balance_usd"] == "300.0"

    db = SessionLocal()
    try:
        remaining_demo = db.query(Fast5MTrade).filter(Fast5MTrade.account_mode == "demo").count()
        remaining_live = db.query(Fast5MTrade).filter(Fast5MTrade.account_mode == "live").count()
        assert remaining_demo == 0
        assert remaining_live >= 1
    finally:
        db.query(Fast5MTrade).filter(Fast5MTrade.market_id == "mkt_live").delete()
        db.commit()
        db.close()


def test_per_asset_filter_controls():
    from app.fast5m.discovery import FastMarketInfo
    from app.fast5m.oracle import AssetOracleState
    from app.fast5m.scorer import FastScorer

    scorer = FastScorer()
    mock_oracle = AssetOracleState(symbol="HYPE", strike_price=25.0)
    mock_oracle.live_price = 25.5
    mock_oracle.delta = 0.5
    mock_oracle.delta_pct = 2.0
    mock_oracle.velocity_10s = 0.01

    from datetime import datetime, timedelta, timezone
    now_dt = datetime.now(timezone.utc)

    # Market with 9% spread and $120 liquidity
    market = FastMarketInfo(
        asset="HYPE",
        condition_id="hype_mkt_1",
        question="HYPE Up?",
        epoch_bucket=12345,
        up_token_id="tok_up",
        down_token_id="tok_down",
        start_time=now_dt,
        end_time=now_dt + timedelta(minutes=5),
        up_ask=0.55,
        down_ask=0.54,
        spread=0.09,
        total_liquidity=120.0,
        time_remaining_sec=150.0
    )

    # 1. With global settings (max_spread=0.20, min_liquidity=100), HYPE would pass
    settings_global = {"max_spread": "0.20", "min_liquidity_usd": "100.0"}
    scored_global = scorer._score_single_asset("HYPE", mock_oracle, market, threshold=50.0, settings=settings_global)
    assert scored_global.is_tradable is True

    # 2. With dedicated HYPE controls (max_spread_hype=0.08), 9% spread is blocked!
    settings_per_asset = {
        "max_spread": "0.20",
        "min_liquidity_usd": "100.0",
        "max_spread_hype": "0.08",
        "min_liquidity_usd_hype": "150.0"
    }
    scored_per_asset = scorer._score_single_asset("HYPE", mock_oracle, market, threshold=50.0, settings=settings_per_asset)
    assert scored_per_asset.is_tradable is False
    assert "spread too wide" in scored_per_asset.rejection_reason.lower()

    # 3. If spread tightens to 5%, but liquidity is $120 < min_liquidity_usd_hype ($150), it is blocked!
    market.spread = 0.05
    scored_liq = scorer._score_single_asset("HYPE", mock_oracle, market, threshold=50.0, settings=settings_per_asset)
    assert scored_liq.is_tradable is False
    assert "liquidity too low" in scored_liq.rejection_reason.lower()

    # 4. Once liquidity reaches $200 and spread is 5%, HYPE is tradable!
    market.total_liquidity = 200.0
    scored_ok = scorer._score_single_asset("HYPE", mock_oracle, market, threshold=50.0, settings=settings_per_asset)
    assert scored_ok.is_tradable is True


def test_slippage_circuit_breaker_on_exit():
    import asyncio
    import time
    from datetime import datetime, timedelta, timezone
    from app.fast5m.executor import FastExecutor
    from app.fast5m.discovery import fast_markets, FastMarketInfo
    from app.fast5m.oracle import fast_oracle
    from app.db.session import SessionLocal
    from app.db.models import Fast5MTrade

    now_dt = datetime.now(timezone.utc)
    executor = FastExecutor()
    executor.settings.update({
        "stop_loss_pct": "3.0",
        "exit_circuit_breaker_enabled": "true",
        "max_exit_slippage_pct": "5.0", # Max 5% slippage beyond target SL
    })

    # Register mock market in fast_markets
    mock_market = FastMarketInfo(
        asset="HYPE",
        condition_id="hype_cb_mkt",
        question="HYPE Up?",
        epoch_bucket=99999,
        up_token_id="tok_up",
        down_token_id="tok_down",
        start_time=now_dt,
        end_time=now_dt + timedelta(minutes=5),
        up_bid=0.25, # Vacuum bid!
        up_ask=0.55,
        down_bid=0.45,
        down_ask=0.50,
        spread=0.04,
        total_liquidity=500.0,
        time_remaining_sec=120.0
    )
    fast_markets.markets["HYPE"] = mock_market

    # Seed mock trade in DB
    db = SessionLocal()
    try:
        trade_rec = Fast5MTrade(
            asset="HYPE",
            market_id="hype_cb_mkt",
            question="HYPE Up?",
            epoch_bucket=99999,
            side="BUY",
            outcome="UP",
            token_id="tok_up",
            entry_price=0.50,
            shares=20.0,
            cost=10.0,
            strike_price=25.0,
            entry_oracle_price=25.0,
            delta_at_entry=0.0,
            confidence_score=90.0,
            status="OPEN",
            account_mode="demo"
        )
        db.add(trade_rec)
        db.commit()
        db.refresh(trade_rec)
        t_id = trade_rec.id
    finally:
        db.close()

    # Setup oracle state for HYPE
    state_hype = fast_oracle.get_asset_state("HYPE")
    state_hype.live_price = 25.0
    state_hype.strike_price = 25.0

    mock_trade = {
        "id": t_id,
        "asset": "HYPE",
        "outcome": "UP",
        "token_id": "tok_up",
        "entry_price": 0.50,
        "shares": 20.0,
        "cost": 10.0,
        "strike_price": 25.0,
        "entry_ts": time.time() - 10.0, # Buffer expired
        "peak_pnl": 0.0,
        "current_pnl": 0.0,
        "account_mode": "demo"
    }
    executor.active_trades[t_id] = mock_trade

    # Target SL is entry (0.50) * 0.97 = 0.485.
    # Vacuum bid is 0.25 (a 50% loss!).
    # Circuit breaker tolerance: min acceptable bid is ~0.460.
    asyncio.run(executor._check_single_trade_exit(mock_trade))

    # 1. VERIFY: Trade was NOT market dumped into the 0.25 vacuum bid!
    assert t_id in executor.active_trades
    assert mock_trade.get("circuit_breaker_active") is True
    assert mock_trade.get("circuit_breaker_min_acceptable") == 0.460

    # 2. Simulate liquidity replenishment: orderbook bid recovers to 0.475
    mock_market.up_bid = 0.475
    asyncio.run(executor._check_single_trade_exit(mock_trade))

    # 3. VERIFY: Position now safely filled at 0.475 under CIRCUIT_BREAKER_SL_FILLED
    assert t_id not in executor.active_trades

    db = SessionLocal()
    try:
        closed_trade = db.query(Fast5MTrade).filter(Fast5MTrade.id == t_id).first()
        assert closed_trade.status == "CLOSED"
        assert closed_trade.resolution == "CIRCUIT_BREAKER_SL_FILLED"
        assert closed_trade.exit_price == 0.475
        assert closed_trade.pnl == -0.50 # Realized loss only -$0.50 (-5%), NOT -$5.00 (-50%)!
    finally:
        db.query(Fast5MTrade).filter(Fast5MTrade.id == t_id).delete()
        db.commit()
        db.close()




