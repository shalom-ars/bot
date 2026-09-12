import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, time
from app.trading.risk import RiskManager
from app.config import settings

def test_risk_manager_initialization_empty():
    with patch('app.trading.risk.SessionLocal') as MockSession:
        mock_db = MagicMock()
        MockSession.return_value = mock_db
        
        # Empty DB setup
        mock_db.query().filter().order_by().all.return_value = []
        mock_db.query().filter().all.return_value = []
        mock_db.query().all.return_value = []
        
        rm = RiskManager()
        
        assert rm.current_balance == settings.starting_balance
        assert rm.daily_pnl == 0.0
        assert rm.consecutive_losses == 0
        assert rm.current_exposure == 0.0
        assert rm.open_positions_count == 0
        assert rm.is_paused == False
        assert rm.peak_balance == settings.starting_balance

def test_risk_manager_rehydration_losing_streak():
    with patch('app.trading.risk.SessionLocal') as MockSession:
        mock_db = MagicMock()
        MockSession.return_value = mock_db
        
        # Mock 3 consecutive losing trades
        t1 = MagicMock(pnl=-1.0, status="CLOSED")
        t2 = MagicMock(pnl=-2.0, status="CLOSED")
        t3 = MagicMock(pnl=-3.0, status="CLOSED")
        
        # 1st query: daily trades
        # 2nd query: all closed trades
        # 3rd query: open positions
        mock_db.query().filter().all.side_effect = [[t1, t2, t3]]
        mock_db.query().filter().order_by().all.return_value = [t1, t2, t3]
        mock_db.query().all.return_value = []
        
        rm = RiskManager()
        
        assert rm.daily_pnl == -6.0
        assert rm.current_balance == settings.starting_balance - 6.0
        assert rm.consecutive_losses == 3

def test_risk_manager_drawdown_limit():
    with patch('app.trading.risk.SessionLocal') as MockSession:
        mock_db = MagicMock()
        MockSession.return_value = mock_db
        
        # Drawdown trigger, but not a daily loss
        t1 = MagicMock(pnl=-160.0, status="CLOSED") 
        
        mock_db.query().filter().all.side_effect = [[], [t1]] # First is daily_trades (empty), second is all_closed
        mock_db.query().filter().order_by().all.return_value = [t1]
        mock_db.query().all.return_value = []
        
        rm = RiskManager()
        
        assert rm.is_paused == True
        assert "Max drawdown limit reached" in rm.pause_reason

def test_evaluate_trade_max_exposure():
    with patch('app.trading.risk.SessionLocal') as MockSession:
        mock_db = MagicMock()
        MockSession.return_value = mock_db
        
        mock_db.query().filter().all.side_effect = [[], []]
        mock_db.query().filter().order_by().all.return_value = []
        mock_db.query().all.return_value = []
        
        rm = RiskManager()
        rm.current_exposure = rm.starting_balance * rm.max_total_exposure # Maxed out
        
        # Trade evaluation
        signal = {"market_id": "1"}
        info = {"condition_id": "A", "ask_depth": 500}
        
        # Re-mock inside evaluate_trade
        mock_db.query().filter().first.return_value = None
        mock_db.query().filter().all.return_value = []
        
        decision = rm.evaluate_trade(signal, info)
        assert decision["decision"] == "REJECT"
        assert decision["reason"] == "REJECTED_TOTAL_EXPOSURE"

def test_evaluate_trade_liquidity():
    with patch('app.trading.risk.SessionLocal') as MockSession:
        mock_db = MagicMock()
        MockSession.return_value = mock_db
        mock_db.query().filter().all.side_effect = [[], []]
        mock_db.query().filter().order_by().all.return_value = []
        mock_db.query().all.return_value = []
        
        rm = RiskManager()
        
        # Inside evaluate
        mock_db.query().filter().first.return_value = None
        mock_db.query().filter().all.return_value = []
        
        # Empty orderbook
        signal = {"market_id": "1"}
        info = {"condition_id": "A", "ask_depth": 0}
        decision = rm.evaluate_trade(signal, info)
        
        assert decision["decision"] == "REJECT"
        assert decision["reason"] == "REJECTED_LIQUIDITY"

def test_duplicate_trade_protection():
    with patch('app.trading.risk.SessionLocal') as MockSession:
        mock_db = MagicMock()
        MockSession.return_value = mock_db
        mock_db.query().filter().all.side_effect = [[]]
        mock_db.query().filter().order_by().all.return_value = []
        mock_db.query().all.return_value = []
        
        rm = RiskManager()
        
        # Fake an existing position
        mock_db.query().filter().first.return_value = True
        
        signal = {"market_id": "1"}
        info = {"condition_id": "A", "ask_depth": 500}
        decision = rm.evaluate_trade(signal, info)
        
        assert decision["decision"] == "REJECT"
        assert decision["reason"] == "REJECTED_DUPLICATE_POSITION"
