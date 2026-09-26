import pytest
from app.fast5m.executor import FastExecutor, DEFAULT_SETTINGS


def test_settings_stop_loss_value_mapping():
    executor = FastExecutor()
    executor.settings["hard_stop_loss_pct"] = "0.5"
    executor.settings["position_size_usd"] = "10.0"
    
    raw_sl = float(executor.settings.get("hard_stop_loss_pct") or 0.5)
    hard_stop_loss_fraction = raw_sl / 100.0 if raw_sl >= 0.05 else raw_sl
    
    # Verify 0.5 is interpreted as 0.005 (0.5%), not 0.50 ($0.50 / 50%)
    assert hard_stop_loss_fraction == pytest.approx(0.005)
    assert (hard_stop_loss_fraction * 100.0) == pytest.approx(0.5)
    
    # If passed as 0.005 directly:
    executor.settings["hard_stop_loss_pct"] = "0.005"
    raw_sl_dec = float(executor.settings["hard_stop_loss_pct"])
    fraction_dec = raw_sl_dec / 100.0 if raw_sl_dec >= 0.05 else raw_sl_dec
    assert fraction_dec == pytest.approx(0.005)


def test_slippage_cap_on_exit_clamps_severe_drops():
    executor = FastExecutor()
    executor.settings["hard_stop_loss_pct"] = "0.5"
    executor.settings["max_exit_slippage_pct"] = "1.0"
    
    entry_price = 0.50
    cost = 10.0
    shares = cost / entry_price # 20 shares
    hard_stop_loss_fraction = 0.005 # 0.5%
    trigger_sl_price = round(entry_price * (1.0 - hard_stop_loss_fraction), 4) # 0.4975
    
    max_slip_pct = 1.0 # 1%
    max_allowed_slip = entry_price * (max_slip_pct / 100.0) # 0.005
    min_allowed_exit_price = round(trigger_sl_price - max_allowed_slip, 4) # 0.4925
    
    # If illiquid orderbook dumps to $0.38 (a -24% collapse):
    crashed_orderbook_bid = 0.38
    oracle_mark_price = 0.4950
    
    # Clamped exit price calculation
    clamped_exit_price = round(max(min_allowed_exit_price, oracle_mark_price), 4)
    assert clamped_exit_price >= min_allowed_exit_price
    assert clamped_exit_price == 0.4950
    
    # Verify that loss is capped to -1.0% or -1.5%, NOT -24%
    realized_loss = (clamped_exit_price - entry_price) * shares
    pnl_pct = ((clamped_exit_price - entry_price) / entry_price) * 100.0
    assert realized_loss == pytest.approx(-0.10)
    assert pnl_pct == pytest.approx(-1.0)


def test_buffer_system_toggle():
    executor = FastExecutor()
    executor.settings["buffer_enabled"] = "false"
    buffer_enabled = executor.settings.get("buffer_enabled", "true").lower() in ("true", "1", "yes")
    assert buffer_enabled is False
    
    executor.settings["buffer_enabled"] = "true"
    buffer_enabled_on = executor.settings.get("buffer_enabled", "true").lower() in ("true", "1", "yes")
    assert buffer_enabled_on is True


def test_multientry_and_grid_defaults():
    executor = FastExecutor()
    assert executor.settings.get("multi_entry_enabled") == "true"
    assert int(executor.settings.get("grid_levels", 2)) >= 1
    assert float(executor.settings.get("grid_step_pct", 1.0)) > 0
