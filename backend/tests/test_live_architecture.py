import pytest
from unittest.mock import patch, MagicMock
from app.trading.eligibility import LiveEligibilityGate
from app.trading.live_engine import LiveExecutionEngine
from app.config import settings

def test_eligibility_gate_defaults_to_false():
    # By default, settings are execution_mode='paper', live_trading_enabled=False
    status = LiveEligibilityGate.check_eligibility()
    assert status["eligible"] is False
    # Check that reasons exist
    assert len(status["reasons"]) > 0
    assert any("CONFIG: live_trading_enabled is False" in r for r in status["reasons"])

@patch('app.trading.eligibility.settings')
@patch('app.trading.eligibility.SessionLocal')
def test_eligibility_gate_fails_on_paper_drawdown(mock_session, mock_settings):
    mock_settings.live_trading_enabled = True
    mock_settings.execution_mode = "live"
    mock_settings.live_trading_kill_switch = False
    mock_settings.min_resolved_markets = 10
    
    mock_db = MagicMock()
    mock_session.return_value = mock_db
    
    # Mock paper test session with bad drawdown
    mock_paper_session = MagicMock(closed_trades=60, drawdown=0.20)
    mock_db.query().filter().first.return_value = mock_paper_session
    
    # Mock resolved markets
    mock_db.query().filter().count.side_effect = [15, 0] # 15 resolved markets, 0 circuit breakers
    
    status = LiveEligibilityGate.check_eligibility()
    assert status["eligible"] is False
    assert any("Excessive paper drawdown" in r for r in status["reasons"])

@patch('app.trading.live_engine.settings')
def test_live_engine_paper_mode_guard(mock_settings):
    mock_settings.execution_mode = "paper"
    
    risk_mock = MagicMock()
    engine = LiveExecutionEngine(risk_mock)
    
    signal = {"id": "1", "market_id": "m1", "token_id": "t1"}
    info = {"ask_price": 0.5, "condition_id": "c1"}
    
    result = engine.execute_signal(signal, info)
    
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "EXECUTION_MODE_IS_PAPER"
    
@patch('app.trading.live_engine.settings')
def test_live_engine_kill_switch_guard(mock_settings):
    mock_settings.execution_mode = "live"
    mock_settings.live_trading_kill_switch = True
    
    risk_mock = MagicMock()
    engine = LiveExecutionEngine(risk_mock)
    
    signal = {"id": "1", "market_id": "m1", "token_id": "t1"}
    info = {"ask_price": 0.5, "condition_id": "c1"}
    
    result = engine.execute_signal(signal, info)
    
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "KILL_SWITCH_ACTIVE"

@patch('app.trading.live_engine.settings')
@patch('app.trading.live_engine.LiveEligibilityGate')
def test_live_engine_eligibility_guard(mock_gate, mock_settings):
    mock_settings.execution_mode = "live"
    mock_settings.live_trading_kill_switch = False
    
    mock_gate.check_eligibility.return_value = {"eligible": False, "reasons": ["Some failure"]}
    
    risk_mock = MagicMock()
    engine = LiveExecutionEngine(risk_mock)
    
    signal = {"id": "1", "market_id": "m1", "token_id": "t1"}
    info = {"ask_price": 0.5, "condition_id": "c1"}
    
    result = engine.execute_signal(signal, info)
    
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "ELIGIBILITY_GATE_FAILED"

@patch('app.trading.live_engine.settings')
@patch('app.trading.live_engine.LiveEligibilityGate')
@patch('app.trading.live_engine.SessionLocal')
def test_live_engine_order_phase7_halt(mock_session, mock_gate, mock_settings):
    # Tests that even if EVERYTHING passes, Phase 7 prevents real execution.
    mock_settings.execution_mode = "live"
    mock_settings.live_trading_kill_switch = False
    mock_gate.check_eligibility.return_value = {"eligible": True, "reasons": []}
    
    risk_mock = MagicMock()
    risk_mock.evaluate_trade.return_value = {"decision": "APPROVE", "size": 10.0}
    
    mock_db = MagicMock()
    mock_session.return_value = mock_db
    
    engine = LiveExecutionEngine(risk_mock)
    
    signal = {"id": "1", "market_id": "m1", "token_id": "t1"}
    info = {"ask_price": 0.5, "condition_id": "c1"}
    
    result = engine.execute_signal(signal, info)
    
    # Phase 7 constraint
    assert result["status"] == "FAILED"
    assert result["reason"] == "LIVE_ORDER_SUBMISSION_DISABLED_PHASE7"
    
    # Verify State Machine tracked it
    mock_db.add.assert_called()
    mock_db.commit.assert_called()
