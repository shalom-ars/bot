import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import Base, Position, Trade
from app.trading.paper_engine import PaperEngine
from app.trading.risk import RiskManager

@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    
    import app.trading.paper_engine
    old_session = app.trading.paper_engine.SessionLocal
    app.trading.paper_engine.SessionLocal = TestingSessionLocal
    
    yield TestingSessionLocal()
    
    app.trading.paper_engine.SessionLocal = old_session

def test_buy_yes_settlement(test_db):
    risk = RiskManager()
    risk.starting_balance = 500.0
    risk.current_balance = 500.0
    engine = PaperEngine(risk)
    
    pos = Position(market_id="mkt_1", condition_id="mkt_1", side="BUY_YES", entry_price=0.4, quantity=100)
    test_db.add(pos)
    trade = Trade(market_id="mkt_1", condition_id="mkt_1", side="BUY_YES", entry_price=0.4, quantity=100, status="OPEN")
    test_db.add(trade)
    test_db.commit()
    
    engine.update_positions("mkt_1", 1.0, is_resolved=True, resolved_price=1.0)
    
    assert risk.daily_pnl == 60.0
    assert risk.current_balance == 560.0
    assert test_db.query(Position).count() == 0
    t = test_db.query(Trade).first()
    assert t.status == "CLOSED"
    assert t.pnl == 60.0

def test_buy_no_settlement(test_db):
    risk = RiskManager()
    risk.starting_balance = 500.0
    risk.current_balance = 500.0
    engine = PaperEngine(risk)
    
    pos = Position(market_id="mkt_2", condition_id="mkt_2", side="BUY_NO", entry_price=0.7, quantity=100)
    test_db.add(pos)
    trade = Trade(market_id="mkt_2", condition_id="mkt_2", side="BUY_NO", entry_price=0.7, quantity=100, status="OPEN")
    test_db.add(trade)
    test_db.commit()
    
    engine.update_positions("mkt_2", 0.0, is_resolved=True, resolved_price=0.0)
    
    assert risk.daily_pnl == pytest.approx(30.0)
    assert risk.current_balance == pytest.approx(530.0)
    assert test_db.query(Position).count() == 0
    t = test_db.query(Trade).first()
    assert t.status == "CLOSED"
    assert t.pnl == pytest.approx(30.0)

def test_double_settlement_idempotency(test_db):
    risk = RiskManager()
    risk.starting_balance = 500.0
    risk.current_balance = 500.0
    engine = PaperEngine(risk)
    
    pos = Position(market_id="mkt_3", condition_id="mkt_3", side="BUY_YES", entry_price=0.4, quantity=100)
    test_db.add(pos)
    trade = Trade(market_id="mkt_3", condition_id="mkt_3", side="BUY_YES", entry_price=0.4, quantity=100, status="OPEN")
    test_db.add(trade)
    test_db.commit()
    
    engine.update_positions("mkt_3", 1.0, is_resolved=True, resolved_price=1.0)
    assert risk.current_balance == 560.0
    
    engine.update_positions("mkt_3", 1.0, is_resolved=True, resolved_price=1.0)
    assert risk.current_balance == 560.0
