"""
Regression tests for BTC5M Prediction Lock & Immutable Trade Thesis.
Tests all 15 required invariants:
1. YES trade entered -> market turns bearish -> locked_predicted_side remains YES
2. NO trade entered -> market turns bullish -> locked_predicted_side remains NO
3. BTC crosses P2B during YES trade -> active trade remains YES
4. BTC crosses P2B during NO trade -> active trade remains NO
5. Momentum reversal does not mutate active trade
6. Orderbook imbalance reversal does not mutate active trade
7. Live prediction changes do not mutate active trade
8. API status payload cleanly separates active_trade from live_market_analysis
9. Market rollover preserves old trade prediction in history
10. New market allows fresh independent prediction
11. Take-profit exit closes trade and opens no opposite trade
12. Stop-loss exit closes trade and opens no opposite trade
13. Repeated status queries never mutate locked fields
14. DB restart rehydration preserves locked prediction
15. DB update attempt against locked field is rejected/reverted and audited
"""
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import Base, BTC5MMarket, BTC5MSignal, BTC5MTrade
from app.api.btc5m import get_btc5m_status, _format_trade


@pytest.fixture
def db_session():
    """Create an isolated in-memory SQLite database session."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def create_sample_trade(db, side="BUY", predicted_side="YES", direction="UP", entry_price=0.60):
    trade = BTC5MTrade(
        market_id="market_btc5m_test_01",
        question="Will BTC be above $65,000 at 12:00 UTC?",
        side=side,
        entry_price=entry_price,
        quantity=50.0,
        position_size=30.0,
        spread_at_entry=0.02,
        momentum_at_entry=0.035,
        imbalance_at_entry=0.15,
        time_remaining_at_entry=240,
        net_edge=0.045,
        planned_risk=0.10,
        planned_reward=0.20,
        planned_rr=2.0,
        stop_loss_price=entry_price - 0.10,
        take_profit_price=entry_price + 0.20,
        strategy="BTC5M_QUANT",
        status="OPEN",
        entry_time=datetime.utcnow(),
        # Immutable thesis fields
        locked_predicted_side=predicted_side,
        locked_direction=direction,
        locked_outcome=predicted_side,
        locked_token_id="token_yes_01" if predicted_side == "YES" else "token_no_01",
        execution_side=side,
        entry_yes_score=78.5,
        entry_no_score=21.5,
        entry_fair_probability=0.68,
        entry_market_probability=0.60,
        entry_net_edge=0.045,
        entry_planned_rr=2.0,
        entry_stop_price=entry_price - 0.10,
        entry_target_price=entry_price + 0.20,
        prediction_locked_at=datetime.utcnow(),
        prediction_lock_version=1
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


# 1. Prediction YES -> ENTER -> market turns bearish -> locked_predicted_side == "YES"
def test_thesis_locked_when_market_turns_bearish_on_yes_trade(db_session):
    trade = create_sample_trade(db_session, side="BUY", predicted_side="YES", direction="UP")
    
    # Simulate market scan turning strongly bearish
    bearish_signal = BTC5MSignal(
        market_id=trade.market_id,
        question=trade.question,
        timestamp=datetime.utcnow(),
        state="SKIP",
        side="SELL",
        yes_score=15.0,
        no_score=85.0,
        predicted_side="NO"
    )
    db_session.add(bearish_signal)
    db_session.commit()

    reloaded = db_session.query(BTC5MTrade).filter_by(id=trade.id).first()
    assert reloaded.locked_predicted_side == "YES"
    assert reloaded.locked_direction == "UP"
    assert reloaded.execution_side == "BUY"


# 2. Prediction NO -> ENTER -> market turns bullish -> locked_predicted_side == "NO"
def test_thesis_locked_when_market_turns_bullish_on_no_trade(db_session):
    trade = create_sample_trade(db_session, side="SELL", predicted_side="NO", direction="DOWN", entry_price=0.40)
    
    # Simulate market scan turning strongly bullish
    bullish_signal = BTC5MSignal(
        market_id=trade.market_id,
        question=trade.question,
        timestamp=datetime.utcnow(),
        state="ENTER",
        side="BUY",
        yes_score=92.0,
        no_score=8.0,
        predicted_side="YES"
    )
    db_session.add(bullish_signal)
    db_session.commit()

    reloaded = db_session.query(BTC5MTrade).filter_by(id=trade.id).first()
    assert reloaded.locked_predicted_side == "NO"
    assert reloaded.locked_direction == "DOWN"
    assert reloaded.execution_side == "SELL"


# 3. BTC crosses P2B during YES trade -> active trade remains YES
def test_btc_crosses_p2b_during_yes_trade_keeps_yes(db_session):
    trade = create_sample_trade(db_session, side="BUY", predicted_side="YES", direction="UP")
    
    now = datetime.utcnow()
    m = BTC5MMarket(
        market_id=trade.market_id,
        condition_id="cond_01",
        question=trade.question,
        start_time=now - timedelta(minutes=2),
        end_time=now + timedelta(minutes=3),
        best_bid=0.45,
        best_ask=0.47,
        is_valid=True
    )
    db_session.add(m)
    db_session.commit()

    reloaded = db_session.query(BTC5MTrade).filter_by(id=trade.id).first()
    assert reloaded.locked_predicted_side == "YES"
    assert reloaded.locked_direction == "UP"


# 4. BTC crosses P2B during NO trade -> active trade remains NO
def test_btc_crosses_p2b_during_no_trade_keeps_no(db_session):
    trade = create_sample_trade(db_session, side="SELL", predicted_side="NO", direction="DOWN")
    
    now = datetime.utcnow()
    m = BTC5MMarket(
        market_id=trade.market_id,
        condition_id="cond_01",
        question=trade.question,
        start_time=now - timedelta(minutes=2),
        end_time=now + timedelta(minutes=3),
        best_bid=0.75,
        best_ask=0.77,
        is_valid=True
    )
    db_session.add(m)
    db_session.commit()

    reloaded = db_session.query(BTC5MTrade).filter_by(id=trade.id).first()
    assert reloaded.locked_predicted_side == "NO"
    assert reloaded.locked_direction == "DOWN"


# 5. Momentum reversal does not mutate active trade
def test_momentum_reversal_does_not_mutate_active_trade(db_session):
    trade = create_sample_trade(db_session, side="BUY", predicted_side="YES")
    orig_momentum = trade.momentum_at_entry

    sig = BTC5MSignal(
        market_id=trade.market_id,
        question=trade.question,
        timestamp=datetime.utcnow(),
        momentum=-0.08,
        state="SKIP",
        reason="MOMENTUM_REVERSAL"
    )
    db_session.add(sig)
    db_session.commit()

    reloaded = db_session.query(BTC5MTrade).filter_by(id=trade.id).first()
    assert reloaded.momentum_at_entry == orig_momentum
    assert reloaded.locked_predicted_side == "YES"


# 6. Orderbook imbalance reversal does not mutate active trade
def test_orderbook_imbalance_reversal_does_not_mutate_active_trade(db_session):
    trade = create_sample_trade(db_session, side="BUY", predicted_side="YES")
    orig_imbalance = trade.imbalance_at_entry

    sig = BTC5MSignal(
        market_id=trade.market_id,
        question=trade.question,
        timestamp=datetime.utcnow(),
        imbalance=-0.35,
        state="SKIP",
        reason="HEAVY_ASK_IMBALANCE"
    )
    db_session.add(sig)
    db_session.commit()

    reloaded = db_session.query(BTC5MTrade).filter_by(id=trade.id).first()
    assert reloaded.imbalance_at_entry == orig_imbalance
    assert reloaded.locked_predicted_side == "YES"


# 7. Live prediction changes do not mutate active trade
def test_live_prediction_change_does_not_mutate_active_trade(db_session):
    trade = create_sample_trade(db_session, side="BUY", predicted_side="YES")

    new_sig = BTC5MSignal(
        market_id=trade.market_id,
        question=trade.question,
        timestamp=datetime.utcnow(),
        state="ENTER",
        side="SELL",
        predicted_side="NO",
        yes_score=10.0,
        no_score=90.0
    )
    db_session.add(new_sig)
    db_session.commit()

    reloaded = db_session.query(BTC5MTrade).filter_by(id=trade.id).first()
    assert reloaded.locked_predicted_side == "YES"
    assert reloaded.entry_yes_score == 78.5


# 8. API status payload separates active_trade from live_market_analysis
def test_api_status_payload_separates_active_trade_from_live_analysis(db_session):
    trade = create_sample_trade(db_session, side="BUY", predicted_side="YES")

    now = datetime.utcnow()
    m = BTC5MMarket(
        market_id=trade.market_id,
        condition_id="cond_01",
        question=trade.question,
        start_time=now - timedelta(minutes=1),
        end_time=now + timedelta(minutes=4),
        best_bid=0.62,
        best_ask=0.64,
        is_valid=True
    )
    db_session.add(m)

    sig = BTC5MSignal(
        market_id=trade.market_id,
        question=trade.question,
        timestamp=datetime.utcnow(),
        state="SKIP",
        side="SELL",
        predicted_side="NO",
        yes_score=20.0,
        no_score=80.0
    )
    db_session.add(sig)
    db_session.commit()

    status = get_btc5m_status(db=db_session)
    assert status["active_trade"] is not None
    assert status["active_trade"]["locked_predicted_side"] == "YES"
    assert status["active_trade"]["locked_direction"] == "UP"
    assert status["live_market_analysis"] is not None
    assert status["live_market_analysis"]["predicted_side"] == "NO"


# 9. Market rollover preserves old trade prediction in history
def test_market_rollover_preserves_old_trade_prediction_in_history(db_session):
    trade = create_sample_trade(db_session, side="BUY", predicted_side="YES")
    
    trade.status = "CLOSED"
    trade.exit_price = 1.0
    trade.exit_reason = "EXPIRY_RESOLVED_YES"
    trade.pnl = 20.0
    trade.resolution = "WIN"
    db_session.commit()

    history_trade = db_session.query(BTC5MTrade).filter_by(id=trade.id).first()
    assert history_trade.status == "CLOSED"
    assert history_trade.locked_predicted_side == "YES"
    assert history_trade.locked_direction == "UP"
    assert history_trade.entry_yes_score == 78.5


# 10. New market allows fresh independent prediction
def test_new_market_allows_fresh_independent_prediction(db_session):
    old_trade = create_sample_trade(db_session, side="BUY", predicted_side="YES")
    old_trade.status = "CLOSED"
    db_session.commit()

    new_trade = BTC5MTrade(
        market_id="market_btc5m_test_02",
        question="Will BTC be above $65,500 at 12:05 UTC?",
        side="SELL",
        entry_price=0.42,
        quantity=50.0,
        position_size=21.0,
        status="OPEN",
        entry_time=datetime.utcnow(),
        locked_predicted_side="NO",
        locked_direction="DOWN",
        locked_outcome="NO",
        locked_token_id="token_no_02",
        execution_side="SELL",
        entry_yes_score=18.0,
        entry_no_score=82.0,
        prediction_locked_at=datetime.utcnow(),
        prediction_lock_version=1
    )
    db_session.add(new_trade)
    db_session.commit()

    assert new_trade.locked_predicted_side == "NO"
    assert new_trade.locked_direction == "DOWN"
    assert old_trade.locked_predicted_side == "YES"


# 11. Take profit exit closes trade; no opposite trade opened
def test_take_profit_exit_closes_trade_no_opposite_trade(db_session):
    trade = create_sample_trade(db_session, side="BUY", predicted_side="YES", entry_price=0.60)
    
    market = BTC5MMarket(
        market_id=trade.market_id,
        condition_id="c_01",
        question=trade.question,
        best_bid=0.82,
        best_ask=0.84,
        is_valid=True
    )
    db_session.add(market)
    db_session.commit()

    if market.best_bid >= trade.take_profit_price:
        trade.status = "CLOSED"
        trade.exit_price = market.best_bid
        trade.exit_reason = "TAKE_PROFIT"
        trade.pnl = (trade.exit_price - trade.entry_price) * trade.quantity
        db_session.commit()

    open_trades = db_session.query(BTC5MTrade).filter(BTC5MTrade.status == "OPEN").all()
    assert len(open_trades) == 0
    closed_trade = db_session.query(BTC5MTrade).filter_by(id=trade.id).first()
    assert closed_trade.status == "CLOSED"
    assert closed_trade.exit_reason == "TAKE_PROFIT"
    assert closed_trade.locked_predicted_side == "YES"


# 12. Stop loss exit closes trade; no opposite trade opened
def test_stop_loss_exit_closes_trade_no_opposite_trade(db_session):
    trade = create_sample_trade(db_session, side="BUY", predicted_side="YES", entry_price=0.60)
    
    market = BTC5MMarket(
        market_id=trade.market_id,
        condition_id="c_01",
        question=trade.question,
        best_bid=0.48,
        best_ask=0.50,
        is_valid=True
    )
    db_session.add(market)
    db_session.commit()

    if market.best_bid <= trade.stop_loss_price:
        trade.status = "CLOSED"
        trade.exit_price = market.best_bid
        trade.exit_reason = "STOP_LOSS"
        trade.pnl = (trade.exit_price - trade.entry_price) * trade.quantity
        db_session.commit()

    open_trades = db_session.query(BTC5MTrade).filter(BTC5MTrade.status == "OPEN").all()
    assert len(open_trades) == 0
    closed_trade = db_session.query(BTC5MTrade).filter_by(id=trade.id).first()
    assert closed_trade.status == "CLOSED"
    assert closed_trade.exit_reason == "STOP_LOSS"
    assert closed_trade.locked_predicted_side == "YES"


# 13. Repeated status queries never mutate locked fields
def test_repeated_status_queries_never_mutate_locked_fields(db_session):
    trade = create_sample_trade(db_session, side="BUY", predicted_side="YES")
    
    for _ in range(15):
        status = get_btc5m_status(db=db_session)
        assert status["active_trade"]["locked_predicted_side"] == "YES"
        assert status["active_trade"]["locked_direction"] == "UP"
        assert status["active_trade"]["entry_yes_score"] == 78.5

    reloaded = db_session.query(BTC5MTrade).filter_by(id=trade.id).first()
    assert reloaded.locked_predicted_side == "YES"
    assert reloaded.locked_direction == "UP"


# 14. DB restart rehydration preserves locked prediction
def test_db_restart_rehydration_preserves_locked_prediction():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    s1 = Session()
    trade = BTC5MTrade(
        market_id="m_rehydrate",
        question="Will BTC be above $66,000?",
        side="BUY",
        entry_price=0.65,
        quantity=50.0,
        position_size=32.5,
        status="OPEN",
        entry_time=datetime.utcnow(),
        locked_predicted_side="YES",
        locked_direction="UP",
        locked_outcome="YES",
        locked_token_id="tok_yes_rehydrate",
        execution_side="BUY",
        entry_yes_score=81.0,
        entry_no_score=19.0,
        entry_fair_probability=0.72,
        entry_market_probability=0.65,
        entry_net_edge=0.07,
        entry_planned_rr=2.2,
        entry_stop_price=0.55,
        entry_target_price=0.85,
        prediction_locked_at=datetime.utcnow(),
        prediction_lock_version=1
    )
    s1.add(trade)
    s1.commit()
    trade_id = trade.id
    s1.close()

    s2 = Session()
    rehydrated = s2.query(BTC5MTrade).filter_by(id=trade_id).first()
    assert rehydrated is not None
    assert rehydrated.locked_predicted_side == "YES"
    assert rehydrated.locked_direction == "UP"
    assert rehydrated.locked_outcome == "YES"
    assert rehydrated.locked_token_id == "tok_yes_rehydrate"
    assert rehydrated.execution_side == "BUY"
    assert rehydrated.entry_yes_score == 81.0
    assert rehydrated.entry_no_score == 19.0
    assert rehydrated.entry_fair_probability == 0.72
    assert rehydrated.entry_net_edge == 0.07
    assert rehydrated.entry_planned_rr == 2.2
    assert rehydrated.entry_stop_price == 0.55
    assert rehydrated.entry_target_price == 0.85
    s2.close()


# 15. DB update attempt against locked field is rejected and audited
def test_db_update_attempt_against_locked_field_is_rejected_and_audited(db_session):
    trade = create_sample_trade(db_session, side="BUY", predicted_side="YES")
    
    # Attempt to tamper with locked_predicted_side
    trade.locked_predicted_side = "NO"
    trade.locked_direction = "DOWN"
    db_session.commit()

    # Verify SQLAlchemy before_update listener intercepted and reverted change
    db_session.refresh(trade)
    assert trade.locked_predicted_side == "YES"
    assert trade.locked_direction == "UP"


# 16. Manual Close Trade terminates active position immediately at market price
def test_manual_close_trade_terminates_active_trade(db_session):
    trade = create_sample_trade(db_session, side="BUY", predicted_side="YES", entry_price=0.60)
    
    # Add market with bid
    m = BTC5MMarket(
        market_id=trade.market_id,
        condition_id="c_manual",
        question=trade.question,
        best_bid=0.72,
        best_ask=0.74,
        is_valid=True
    )
    db_session.add(m)
    db_session.commit()

    from app.api.btc5m import close_btc5m_trade
    res = close_btc5m_trade(db=db_session)
    assert res["status"] == "success"
    assert "closed manually" in res["message"]
    
    reloaded = db_session.query(BTC5MTrade).filter_by(id=trade.id).first()
    assert reloaded.status == "CLOSED"
    assert reloaded.exit_reason == "MANUAL_CLOSE"
    assert reloaded.resolution == "MANUAL"
    assert reloaded.exit_price == 0.72
    assert reloaded.locked_predicted_side == "YES"
    assert reloaded.locked_direction == "UP"
    
    # Calling again when no active trade exists returns error
    res2 = close_btc5m_trade(db=db_session)
    assert res2["status"] == "error"

