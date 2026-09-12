import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import Base, Market, MarketSnapshot, User, UserPortfolio, UserPosition, UserTrade, Signal, UserSetting
from app.engine.user_engine import execute_saas_user_trades, resolve_saas_user_trades

from app.db.session import SessionLocal
from datetime import datetime

from unittest.mock import patch

@pytest.fixture
def test_db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_e2e_paper_lifecycle(test_db):
    with patch('app.engine.user_engine.SessionLocal', return_value=test_db):
        
        # 1. Setup Data
        user = User(email="test@example.com", hashed_password="pw")
        test_db.add(user)
        test_db.commit()
        
        portfolio = UserPortfolio(user_id=user.id, initial_balance=500.0, current_balance=500.0, equity=500.0)
        test_db.add(portfolio)
        
        setting = UserSetting(user_id=user.id, max_position_risk=0.05)
        test_db.add(setting)
        
        market = Market(market_id="m1", condition_id="c1", token="Yes", token_id="t1", active=True, question="Test?")
        test_db.add(market)
        test_db.commit()

        # 4. Strategy -> Signal
        signal_data = {
            "signal_id": "sig_1",
            "market_id": "m1",
            "condition_id": "c1",
            "token_id": "t1",
            "side": "BUY",
            "signal_type": "BUY",
            "fair_probability": 0.6,
            "entry_price": 0.52,
            "raw_edge": 0.08,
            "spread_cost": 0.04,
            "slippage": 0.01,
            "liquidity_cost": 0.0,
            "fees": 0.01,
            "net_edge": 0.02,
            "confidence": 0.9,
            "timestamp": datetime.utcnow()
        }
        
        market_info = {
            "question": "Test?",
            "tokens": "['t1','t2']"
        }

        # 6. Paper BUY for all users
        execute_saas_user_trades(signal_data, market_info, 0.52)
        
        # Check Portfolio and Position
        test_db.commit()
        
        user_id = 1
        pos = test_db.query(UserPosition).filter_by(user_id=user_id).first()
        assert pos is not None
        assert pos.market_id == "m1"
        assert pos.side == "BUY"
        assert pos.entry_price == 0.53  # Because of 0.01 simulated slippage
        
        # 7. Resolution & Settlement (YES Wins)
        resolve_saas_user_trades("m1", "YES")
        
        test_db.commit()
        
        # Position should be closed
        pos_after = test_db.query(UserPosition).filter_by(user_id=user_id).first()
        assert pos_after is None
        
        # Trade should be recorded
        trade = test_db.query(UserTrade).filter_by(user_id=user_id).first()
        assert trade is not None
        assert trade.status == "CLOSED"
        assert trade.exit_price == 1.0 # Payout is $1
        assert trade.pnl > 0 
        
        # Balance should be updated
        port_after = test_db.query(UserPortfolio).filter_by(user_id=user_id).first()
        assert port_after.current_balance > 500.0
        assert port_after.realized_pnl > 0
