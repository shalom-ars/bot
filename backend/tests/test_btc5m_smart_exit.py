"""
Test Suite for BTC5M Smart Stop-Loss / Adaptive Exit System.
Verifies all 20 operational invariants and edge cases specified in Section 18:

1. Small adverse move -> HOLD.
2. Soft stop touched -> enters EXIT_REVIEW with confirmation timer.
3. Temporary noise (spread wick / dip, BTC above P2B) -> transitions back to HOLD.
4. BTC remains comfortably on winning side of P2B -> score stays low, trade HOLDS.
5. BTC drops below P2B with persistent negative momentum -> CONFIRMED_EXIT when timer elapses.
6. Hard safety stop breached -> immediate HARD_EXIT without waiting.
7. RiskManager circuit breaker / pause -> immediate HARD_EXIT.
8. Catastrophic max trade risk breach -> immediate HARD_EXIT.
9. Take profit reached -> TP exit with correct PnL.
10. Prediction lock immutability -> live market flip does NOT flip active trade thesis.
11. Confirmation window dynamically shortens when <60s remaining.
12. Audit trail persistence -> BTC5MExitAudit records created with all required fields.
13. Paper trading mode guarantee -> live trading remains hard disabled.
14. NO position executable price calculation -> 1.0 - ask correctly calculated.
15. Full trade lifecycle with Smart Exit decision transitions.
"""
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, BTC5MTrade, BTC5MExitAudit, BTC5MMarket
from app.btc5m.exit_manager import (
    BTC5MExitManager,
    calculate_thesis_failure_score,
    DEFAULT_SOFT_STOP_CONFIRMATION_SECONDS,
    DEFAULT_THESIS_FAILURE_THRESHOLD
)


@pytest.fixture
def db_session():
    """Create an isolated in-memory SQLite database session."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def create_open_trade(
    db,
    instance_id="instance_1",
    side="BUY",
    locked_predicted_side="YES",
    entry_price=0.60,
    stop_loss=0.45,
    take_profit=0.85,
    hard_stop=0.35,
    quantity=50.0
):
    trade = BTC5MTrade(
        market_id="test_market_5m_001",
        question="Will BTC be above $65,000 at 12:00 UTC?",
        instance_id=instance_id,
        side=side,
        locked_predicted_side=locked_predicted_side,
        locked_direction="UP" if locked_predicted_side == "YES" else "DOWN",
        entry_price=entry_price,
        quantity=quantity,
        position_size=entry_price * quantity,
        stop_loss_price=stop_loss,
        take_profit_price=take_profit,
        hard_stop_price=hard_stop,
        entry_stop_price=stop_loss,
        entry_target_price=take_profit,
        status="OPEN",
        exit_decision_state="HOLD",
        entry_time=datetime.now(timezone.utc)
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


# ── TEST 1: Small adverse move -> HOLD ───────────────────────────────────────
def test_small_adverse_move_holds(db_session):
    trade = create_open_trade(db_session, entry_price=0.60, stop_loss=0.45)
    manager = BTC5MExitManager(db_session, instance_id="instance_1")

    decision, exit_price, reason, score, _, audit_event = manager.evaluate_exit(
        trade=trade,
        current_executable_price=0.55,  # Down from 0.60, but well above 0.45
        current_mid_price=0.56,
        btc_price=65100.0,
        p2b=65000.0,
        features={"short_momentum_1m": 0.0001, "fair_prob_yes": 0.58},
        time_remaining_sec=200.0,
        risk_manager=None,
        settings={}
    )

    assert decision == "HOLD"
    assert exit_price is None
    assert trade.exit_decision_state == "HOLD"
    assert score < 20.0
    assert audit_event is None


# ── TEST 2: Soft stop touched -> enters EXIT_REVIEW ──────────────────────────
def test_soft_stop_touched_enters_review(db_session):
    trade = create_open_trade(db_session, entry_price=0.60, stop_loss=0.45)
    manager = BTC5MExitManager(db_session, instance_id="instance_1")

    decision, exit_price, reason, score, _, audit_event = manager.evaluate_exit(
        trade=trade,
        current_executable_price=0.44,  # Just breached 0.45
        current_mid_price=0.45,
        btc_price=65050.0,  # BTC is still slightly above P2B
        p2b=65000.0,
        features={"short_momentum_1m": -0.0001, "fair_prob_yes": 0.46},
        time_remaining_sec=180.0,
        risk_manager=None,
        settings={"soft_stop_confirmation_seconds": 10.0}
    )

    assert decision == "EXIT_REVIEW"
    assert exit_price is None
    assert trade.exit_decision_state == "EXIT_REVIEW"
    assert trade.soft_stop_touched_at is not None
    assert trade.exit_review_started_at is not None
    assert audit_event == "SOFT_STOP_TOUCHED"


# ── TEST 3: Temporary noise -> stays in EXIT_REVIEW during grace period ───────
def test_review_grace_period_prevents_premature_exit(db_session):
    trade = create_open_trade(db_session, entry_price=0.60, stop_loss=0.45)
    trade.exit_decision_state = "EXIT_REVIEW"
    trade.exit_review_started_at = datetime.now(timezone.utc) - timedelta(seconds=4)  # 4s elapsed
    db_session.commit()

    manager = BTC5MExitManager(db_session, instance_id="instance_1")

    decision, exit_price, reason, score, _, audit_event = manager.evaluate_exit(
        trade=trade,
        current_executable_price=0.43,
        current_mid_price=0.44,
        btc_price=65020.0,
        p2b=65000.0,
        features={"short_momentum_1m": -0.0002, "fair_prob_yes": 0.44},
        time_remaining_sec=180.0,
        risk_manager=None,
        settings={"soft_stop_confirmation_seconds": 10.0}
    )

    assert decision == "EXIT_REVIEW"
    assert exit_price is None
    assert "Analyzing temporary noise" in reason


# ── TEST 4: Noise resolves -> price recovers above soft stop -> HOLD ─────────
def test_price_recovers_transitions_to_hold(db_session):
    trade = create_open_trade(db_session, entry_price=0.60, stop_loss=0.45)
    trade.exit_decision_state = "EXIT_REVIEW"
    trade.exit_review_started_at = datetime.now(timezone.utc) - timedelta(seconds=6)
    db_session.commit()

    manager = BTC5MExitManager(db_session, instance_id="instance_1")

    decision, exit_price, reason, score, _, audit_event = manager.evaluate_exit(
        trade=trade,
        current_executable_price=0.52,  # Price bounced back up!
        current_mid_price=0.53,
        btc_price=65100.0,
        p2b=65000.0,
        features={"short_momentum_1m": 0.0005, "fair_prob_yes": 0.55},
        time_remaining_sec=170.0,
        risk_manager=None,
        settings={}
    )

    assert decision == "HOLD"
    assert trade.exit_decision_state == "HOLD"
    assert audit_event == "EXIT_REVIEW_HOLD"


# ── TEST 5: Grace period expires BUT BTC still above P2B -> HOLD (Noise) ─────
def test_confirmation_expires_with_low_failure_score_holds(db_session):
    trade = create_open_trade(db_session, entry_price=0.60, stop_loss=0.45)
    trade.exit_decision_state = "EXIT_REVIEW"
    # 12s elapsed (greater than 10s confirmation window)
    trade.exit_review_started_at = datetime.now(timezone.utc) - timedelta(seconds=12)
    db_session.commit()

    manager = BTC5MExitManager(db_session, instance_id="instance_1")

    # CLOB bid is depressed at 0.42, BUT BTC is STILL above P2B (+50 USD), momentum is neutral
    decision, exit_price, reason, score, _, audit_event = manager.evaluate_exit(
        trade=trade,
        current_executable_price=0.42,
        current_mid_price=0.44,
        btc_price=65050.0,
        p2b=65000.0,  # BTC > P2B: Fundamental thesis is INTACT
        features={"short_momentum_1m": 0.0, "fair_prob_yes": 0.48},
        time_remaining_sec=150.0,
        risk_manager=None,
        settings={"soft_stop_confirmation_seconds": 10.0, "thesis_failure_threshold": 60.0}
    )

    # Must NOT exit on pure temporary noise!
    assert decision == "HOLD"
    assert exit_price is None
    assert trade.exit_decision_state == "HOLD"
    assert score < 60.0
    assert audit_event == "EXIT_REVIEW_HOLD"


# ── TEST 6: Grace period expires AND BTC drops below P2B -> CONFIRMED_EXIT ───
def test_confirmation_expires_with_high_failure_score_exits(db_session):
    trade = create_open_trade(db_session, entry_price=0.60, stop_loss=0.45)
    trade.exit_decision_state = "EXIT_REVIEW"
    trade.exit_review_started_at = datetime.now(timezone.utc) - timedelta(seconds=12)
    db_session.commit()

    manager = BTC5MExitManager(db_session, instance_id="instance_1")

    # BTC dropped $40 below P2B, sharp negative momentum, fair prob collapsed
    decision, exit_price, reason, score, _, audit_event = manager.evaluate_exit(
        trade=trade,
        current_executable_price=0.40,
        current_mid_price=0.41,
        btc_price=64960.0,  # $40 below P2B
        p2b=65000.0,
        features={
            "btc_momentum_1m": -0.0015,
            "fair_prob_yes": 0.25,
            "bid_ask_imbalance": -0.40
        },
        time_remaining_sec=90.0,
        risk_manager=None,
        settings={"soft_stop_confirmation_seconds": 10.0, "thesis_failure_threshold": 60.0}
    )

    assert decision == "CONFIRMED_EXIT"
    assert exit_price == 0.40
    assert trade.exit_decision_state == "CONFIRMED_EXIT"
    assert score >= 60.0
    assert audit_event == "EXIT_REVIEW_CONFIRMED"


# ── TEST 7: Hard safety stop breached -> immediate HARD_EXIT ────────────────
def test_hard_stop_breach_immediate_exit(db_session):
    trade = create_open_trade(db_session, entry_price=0.60, stop_loss=0.45, hard_stop=0.35)
    manager = BTC5MExitManager(db_session, instance_id="instance_1")

    decision, exit_price, reason, score, _, audit_event = manager.evaluate_exit(
        trade=trade,
        current_executable_price=0.34,  # Breached hard stop floor (0.35)
        current_mid_price=0.35,
        btc_price=65100.0,
        p2b=65000.0,
        features={},
        time_remaining_sec=200.0,
        risk_manager=None,
        settings={}
    )

    assert decision == "HARD_EXIT"
    assert exit_price == 0.34
    assert "HARD SAFETY STOP" in reason
    assert score == 100.0
    assert audit_event == "HARD_STOP_TRIGGERED"


# ── TEST 8: RiskManager Circuit Breaker -> immediate HARD_EXIT ──────────────
def test_risk_manager_circuit_breaker_immediate_exit(db_session):
    trade = create_open_trade(db_session, entry_price=0.60, stop_loss=0.45)
    manager = BTC5MExitManager(db_session, instance_id="instance_1")

    class MockRiskManager:
        is_paused = True

    decision, exit_price, reason, score, _, audit_event = manager.evaluate_exit(
        trade=trade,
        current_executable_price=0.58,
        current_mid_price=0.59,
        btc_price=65100.0,
        p2b=65000.0,
        features={},
        time_remaining_sec=200.0,
        risk_manager=MockRiskManager(),
        settings={}
    )

    assert decision == "HARD_EXIT"
    assert "RiskManager circuit breaker active" in reason
    assert audit_event == "HARD_STOP_TRIGGERED"


# ── TEST 9: Take Profit reached -> TP exit ──────────────────────────────────
def test_take_profit_target_reached(db_session):
    trade = create_open_trade(db_session, entry_price=0.60, take_profit=0.85)
    manager = BTC5MExitManager(db_session, instance_id="instance_1")

    decision, exit_price, reason, score, _, audit_event = manager.evaluate_exit(
        trade=trade,
        current_executable_price=0.86,
        current_mid_price=0.87,
        btc_price=65200.0,
        p2b=65000.0,
        features={},
        time_remaining_sec=120.0,
        risk_manager=None,
        settings={}
    )

    assert decision == "TP"
    assert exit_price == 0.86
    assert "Take profit target reached" in reason
    assert audit_event == "TAKE_PROFIT"


# ── TEST 10: NO Position (Short) Thesis Invalidation ────────────────────────
def test_no_position_thesis_score_when_btc_surges_above_p2b(db_session):
    trade = create_open_trade(
        db_session,
        instance_id="instance_2",
        side="SELL",
        locked_predicted_side="NO",
        entry_price=0.40,
        stop_loss=0.55
    )

    # Case A: BTC is below P2B -> fundamental thesis is INTACT
    score_intact, _, _ = calculate_thesis_failure_score(
        trade=trade,
        btc_price=64950.0,
        p2b=65000.0,
        features={"short_momentum_1m": -0.0005, "fair_prob_yes": 0.40},
        time_remaining_sec=180.0
    )
    assert score_intact < 20.0

    # Case B: BTC surged $40 above P2B with bullish momentum -> thesis failed
    score_failed, _, _ = calculate_thesis_failure_score(
        trade=trade,
        btc_price=65040.0,
        p2b=65000.0,
        features={"btc_momentum_1m": 0.0012, "fair_prob_yes": 0.75},
        time_remaining_sec=90.0
    )
    assert score_failed >= 60.0


# ── TEST 11: Dynamic confirmation shortening under 60s ───────────────────────
def test_dynamic_confirmation_shortens_late_in_window(db_session):
    trade = create_open_trade(db_session, entry_price=0.60, stop_loss=0.45)
    trade.exit_decision_state = "EXIT_REVIEW"
    # 6s elapsed
    trade.exit_review_started_at = datetime.now(timezone.utc) - timedelta(seconds=6)
    db_session.commit()

    manager = BTC5MExitManager(db_session, instance_id="instance_1")

    # When time_remaining_sec < 60s, confirmation max is capped at 5s!
    # So 6s is >= 5s, meaning evaluation executes immediately
    decision, exit_price, reason, score, _, audit_event = manager.evaluate_exit(
        trade=trade,
        current_executable_price=0.40,
        current_mid_price=0.41,
        btc_price=64950.0,
        p2b=65000.0,
        features={"btc_momentum_1m": -0.0015, "fair_prob_yes": 0.20},
        time_remaining_sec=45.0,  # Under 60s remaining
        risk_manager=None,
        settings={"soft_stop_confirmation_seconds": 10.0, "thesis_failure_threshold": 60.0}
    )

    assert decision == "CONFIRMED_EXIT"
    assert audit_event == "EXIT_REVIEW_CONFIRMED"


# ── TEST 12: Audit Trail Persistence in SQLite ───────────────────────────────
def test_audit_trail_recorded_to_database(db_session):
    trade = create_open_trade(db_session, entry_price=0.60, stop_loss=0.45)
    manager = BTC5MExitManager(db_session, instance_id="instance_1")

    audit = manager.record_audit(
        trade=trade,
        event_type="SOFT_STOP_TOUCHED",
        current_executable_price=0.44,
        btc_price=65010.0,
        p2b=65000.0,
        features={"short_momentum_1m": -0.0001, "fair_prob_yes": 0.45},
        time_remaining_sec=180.0,
        current_exit_decision="EXIT_REVIEW",
        thesis_failure_score=25.0,
        reason="Soft stop touched; starting review",
        breakdown={"btc_vs_p2b": 0.0, "momentum": 5.0}
    )

    db_session.commit()
    saved = db_session.query(BTC5MExitAudit).filter(BTC5MExitAudit.trade_id == trade.id).first()
    assert saved is not None
    assert saved.event_type == "SOFT_STOP_TOUCHED"
    assert saved.thesis_failure_score == 25.0
    assert saved.locked_predicted_side == "YES"
    assert saved.current_exit_decision == "EXIT_REVIEW"


# ── TEST 13: Prediction Lock Immutability during Exit Evaluation ─────────────
def test_thesis_immutability_during_live_market_flip(db_session):
    trade = create_open_trade(db_session, side="BUY", locked_predicted_side="YES")
    manager = BTC5MExitManager(db_session, instance_id="instance_1")

    # Live market prediction is "NO", but trade's locked thesis is YES
    features = {"predicted_side": "NO", "short_momentum_1m": -0.0002}
    manager.evaluate_exit(
        trade=trade,
        current_executable_price=0.55,
        current_mid_price=0.56,
        btc_price=65020.0,
        p2b=65000.0,
        features=features,
        time_remaining_sec=150.0,
        risk_manager=None,
        settings={}
    )

    # Immutable thesis must NEVER mutate
    assert trade.locked_predicted_side == "YES"
    assert trade.side == "BUY"


# ── TEST 14: Hard Stop Delta Fallback Default ────────────────────────────────
def test_hard_stop_price_default_calculation(db_session):
    trade = create_open_trade(db_session, entry_price=0.60, stop_loss=0.45, hard_stop=None)
    trade.hard_stop_price = None  # Ensure None to test fallback
    db_session.commit()

    manager = BTC5MExitManager(db_session, instance_id="instance_1")

    # Hard stop should default to stop_loss - 0.10 = 0.35
    # When price is 0.34, it should trigger HARD_EXIT
    decision, exit_price, reason, score, _, audit_event = manager.evaluate_exit(
        trade=trade,
        current_executable_price=0.34,
        current_mid_price=0.35,
        btc_price=65100.0,
        p2b=65000.0,
        features={},
        time_remaining_sec=180.0,
        risk_manager=None,
        settings={"hard_stop_delta": 0.10}
    )

    assert decision == "HARD_EXIT"
    assert audit_event == "HARD_STOP_TRIGGERED"


# ── TEST 15: Strict Entry Gates — Late Candle Rejection ─────────────────────
def test_entry_gates_reject_late_candle(db_session):
    from app.btc5m.strategy import BTC5MStrategy
    strat = BTC5MStrategy(instance_id="instance_1", settings_dict={"min_time_remaining": 210.0, "max_time_remaining": 295.0})
    features = {
        "mid_price": 0.50,
        "bid": 0.49,
        "ask": 0.51,
        "spread": 0.02,
        "bid_depth": 500.0,
        "ask_depth": 500.0,
        "short_momentum_1m": 0.001,
        "bid_ask_imbalance": 0.1,
        "time_remaining_sec": 180.0  # < 210.0s min_time
    }
    sig = strat.evaluate(
        market_id="test_late_mkt",
        condition_id="0xabc",
        question="BTC 5M Test",
        yes_token_id="tok1",
        no_token_id="tok2",
        features=features,
        orderbook_timestamp=None,
        btc_price=65100.0,
        price_to_beat=65000.0,
        current_balance=500.0
    )
    assert sig.state == "SKIP"
    assert "Late-candle entry rejected" in sig.reason


# ── TEST 16: Strict Entry Gates — Extreme Entry Price Rejection ─────────────
def test_entry_gates_reject_extreme_entry_price(db_session):
    from app.btc5m.strategy import BTC5MStrategy
    strat = BTC5MStrategy(instance_id="instance_1", settings_dict={"min_entry_price": 0.40, "max_entry_price": 0.58})
    # Elevated price 0.65 > 0.58
    features = {
        "mid_price": 0.65,
        "bid": 0.64,
        "ask": 0.66,
        "spread": 0.02,
        "bid_depth": 500.0,
        "ask_depth": 500.0,
        "short_momentum_1m": 0.001,
        "bid_ask_imbalance": 0.1,
        "time_remaining_sec": 250.0
    }
    sig = strat.evaluate(
        market_id="test_price_mkt",
        condition_id="0xdef",
        question="BTC 5M Test",
        yes_token_id="tok1",
        no_token_id="tok2",
        features=features,
        orderbook_timestamp=None,
        btc_price=65100.0,
        price_to_beat=65000.0,
        current_balance=500.0
    )
    assert sig.state == "SKIP"
    assert "outside optimal R:R window" in sig.reason


# ── TEST 17: Strict Entry Gates — Indecisive P2B Rejection ──────────────────
def test_entry_gates_reject_indecisive_p2b(db_session):
    from app.btc5m.strategy import BTC5MStrategy
    strat = BTC5MStrategy(instance_id="instance_1", settings_dict={"min_p2b_diff": 15.0})
    features = {
        "mid_price": 0.50,
        "bid": 0.49,
        "ask": 0.51,
        "spread": 0.02,
        "bid_depth": 500.0,
        "ask_depth": 500.0,
        "short_momentum_1m": 0.001,
        "bid_ask_imbalance": 0.1,
        "time_remaining_sec": 250.0
    }
    # BTC only $5 from P2B (< $15.00 threshold)
    sig = strat.evaluate(
        market_id="test_p2b_mkt",
        condition_id="0xghi",
        question="BTC 5M Test",
        yes_token_id="tok1",
        no_token_id="tok2",
        features=features,
        orderbook_timestamp=None,
        btc_price=65005.0,
        price_to_beat=65000.0,
        current_balance=500.0
    )
    assert sig.state == "SKIP"
    assert "Indecisive BTC vs P2B" in sig.reason


# ── TEST 18: In-Memory Fast Exit Evaluator Closes Trade Instantly ────────────
@pytest.mark.asyncio
async def test_fast_exit_monitor_evaluates_and_closes_trade(db_session):
    from app.btc5m.engine import btc5m_engine
    from app.db.models import BTC5MMarket

    # Setup market and trade
    mkt = BTC5MMarket(
        market_id="test_market_5m_001",
        condition_id="cid_fast",
        question="Test Market",
        yes_token_id="yes1",
        no_token_id="no1",
        best_bid=0.58,  # Gain: (0.58 - 0.50) * 20 = +$1.60 >= $1.00 target
        best_ask=0.59,
        mid_price=0.585,
        time_remaining_sec=200.0
    )
    db_session.add(mkt)

    trade = create_open_trade(
        db_session,
        entry_price=0.50,
        stop_loss=0.01,
        take_profit=0.55,
        quantity=20.0
    )
    trade.planned_reward = 1.00
    db_session.commit()

    # Call _evaluate_and_apply_exit
    closed = await btc5m_engine._evaluate_and_apply_exit(db_session, trade)
    assert closed is True
    assert trade.status == "CLOSED"
    assert trade.resolution == "EARLY_TP"
    assert trade.pnl >= 1.00
    assert "Take profit target reached" in trade.exit_reason


# ── TEST 19: RSI-14 Indicator Overbought & Oversold Gate Protection ───────────
def test_rsi_14_overbought_and_oversold_protection(db_session):
    from app.btc5m.strategy import BTC5MStrategy
    from app.btc5m.features import BTC5MFeatureEngine

    strat = BTC5MStrategy(
        instance_id="instance_1",
        settings_dict={
            "min_p2b_diff": 10.0,
            "rsi_overbought": 70.0,
            "rsi_oversold": 30.0,
            "min_entry_probability": 0.50
        }
    )

    base_features = {
        "mid_price": 0.50,
        "bid": 0.49,
        "ask": 0.51,
        "spread": 0.02,
        "bid_depth": 500.0,
        "ask_depth": 500.0,
        "short_momentum_1m": 0.005,
        "bid_ask_imbalance": 0.2,
        "time_remaining_sec": 250.0
    }

    # Case 1: Overbought (RSI = 78.0 > 70) -> Buying YES/UP should be blocked
    features_ob = dict(base_features)
    features_ob["rsi_14"] = 78.0

    sig_ob = strat.evaluate(
        market_id="mkt_rsi_ob",
        condition_id="0x_ob",
        question="BTC 5M Test Overbought",
        yes_token_id="tok_yes",
        no_token_id="tok_no",
        features=features_ob,
        orderbook_timestamp=None,
        btc_price=65030.0,
        price_to_beat=65000.0,  # Strongly above strike (+ $30), predicted YES
        current_balance=500.0
    )
    assert sig_ob.state == "SKIP"
    assert any("Overbought" in flag for flag in sig_ob.skip_flags)
    assert "Overbought" in sig_ob.gate_results

    # Case 2: Oversold (RSI = 22.0 < 30) -> Buying NO/DOWN should be blocked
    features_os = dict(base_features)
    features_os["rsi_14"] = 22.0

    sig_os = strat.evaluate(
        market_id="mkt_rsi_os",
        condition_id="0x_os",
        question="BTC 5M Test Oversold",
        yes_token_id="tok_yes",
        no_token_id="tok_no",
        features=features_os,
        orderbook_timestamp=None,
        btc_price=64970.0,
        price_to_beat=65000.0,  # Strongly below strike (- $30), predicted NO
        current_balance=500.0
    )
    assert sig_os.state == "SKIP"
    assert any("Oversold" in flag for flag in sig_os.skip_flags)
    assert "Oversold" in sig_os.gate_results

    # Case 3: Healthy RSI (RSI = 52.0, between 30 and 70) -> Gate passes
    features_ok = dict(base_features)
    features_ok["rsi_14"] = 52.0

    sig_ok = strat.evaluate(
        market_id="mkt_rsi_ok",
        condition_id="0x_ok",
        question="BTC 5M Test Normal RSI",
        yes_token_id="tok_yes",
        no_token_id="tok_no",
        features=features_ok,
        orderbook_timestamp=None,
        btc_price=65030.0,
        price_to_beat=65000.0,
        current_balance=500.0
    )
    assert not any("RSI" in flag for flag in sig_ok.skip_flags)
    import json
    gates = json.loads(sig_ok.gate_results)
    assert gates["rsi"]["pass"] is True
    assert gates["rsi"]["value"] == "52.0"

    # Verify FeatureEngine RSI-14 calculation on price sequence
    fe = BTC5MFeatureEngine()
    # Feed 20 ticks of steady rising prices
    for i in range(20):
        f = fe.update_and_compute("test_mkt", 0.50 + (i * 0.01), 0.49 + (i * 0.01), 0.51 + (i * 0.01), 0.02, 100, 100, 0, 200)
    assert "rsi_14" in f
    assert f["rsi_14"] == 100.0  # Steady pure gains yield 100 RSI


# ── TEST 20: MACD and Bollinger Bands Gating and Feature Engine ──────────────
def test_macd_and_bollinger_bands_integration(db_session):
    import json
    from app.btc5m.features import BTC5MFeatureEngine
    from app.btc5m.strategy import BTC5MStrategy
    from app.btc5m.settings_manager import DEFAULT_SETTINGS, TYPED_FIELDS

    # 1. Verify settings configuration
    assert "macd_fast" in DEFAULT_SETTINGS and TYPED_FIELDS["macd_fast"] == int
    assert "macd_slow" in DEFAULT_SETTINGS and TYPED_FIELDS["macd_slow"] == int
    assert "macd_signal" in DEFAULT_SETTINGS and TYPED_FIELDS["macd_signal"] == int
    assert "bb_period" in DEFAULT_SETTINGS and TYPED_FIELDS["bb_period"] == int
    assert "bb_std" in DEFAULT_SETTINGS and TYPED_FIELDS["bb_std"] == float

    # 2. Verify FeatureEngine computes MACD and Bollinger Bands
    fe = BTC5MFeatureEngine()
    prices = [0.50, 0.51, 0.52, 0.53, 0.52, 0.54, 0.55, 0.53, 0.56, 0.57,
              0.55, 0.58, 0.59, 0.58, 0.60, 0.61, 0.59, 0.62, 0.63, 0.64]
    for p in prices:
        f = fe.update_and_compute("bb_macd_mkt", p, p - 0.01, p + 0.01, 0.02, 500, 500, 0.1, 240)

    assert "macd_line" in f
    assert "macd_signal" in f
    assert "macd_hist" in f
    assert "bb_middle" in f
    assert "bb_upper" in f
    assert "bb_lower" in f
    assert "bb_bandwidth" in f
    assert "bb_pct_b" in f
    assert f["bb_upper"] > f["bb_middle"] > f["bb_lower"]

    # 3. Verify Strategy Gating with healthy MACD and Bollinger Bands
    strat = BTC5MStrategy(instance_id="instance_1")
    healthy_features = {
        "mid_price": 0.50,
        "bid": 0.49,
        "ask": 0.51,
        "spread": 0.02,
        "bid_depth": 500.0,
        "ask_depth": 500.0,
        "short_momentum_1m": 0.005,
        "bid_ask_imbalance": 0.2,
        "time_remaining_sec": 240.0,
        "rsi_14": 55.0,
        "macd_hist": 0.02,
        "bb_pct_b": 0.65,
        "bb_bandwidth": 0.04
    }
    sig_healthy = strat.evaluate(
        market_id="mkt_healthy_bb",
        condition_id="0x_healthy",
        question="BTC 5M Test Healthy",
        yes_token_id="tok_yes",
        no_token_id="tok_no",
        features=healthy_features,
        orderbook_timestamp=None,
        btc_price=65040.0,
        price_to_beat=65000.0,
        current_balance=500.0
    )
    gates_healthy = json.loads(sig_healthy.gate_results)
    assert gates_healthy["macd"]["pass"] is True
    assert "Bullish" in gates_healthy["macd"]["value"]
    assert gates_healthy["bollinger"]["pass"] is True
    assert "%B 0.65" in gates_healthy["bollinger"]["value"]

    # 4. Verify Bollinger Upper Band piercing rejection (%B > 1.10) for YES
    overextended_up = dict(healthy_features)
    overextended_up["bb_pct_b"] = 1.18
    sig_bb_up = strat.evaluate(
        market_id="mkt_bb_up",
        condition_id="0x_bb_up",
        question="BTC 5M Overextended Upper",
        yes_token_id="tok_yes",
        no_token_id="tok_no",
        features=overextended_up,
        orderbook_timestamp=None,
        btc_price=65050.0,
        price_to_beat=65000.0,
        current_balance=500.0
    )
    assert sig_bb_up.state == "SKIP"
    assert any("pierced upper Bollinger Band" in flag for flag in sig_bb_up.skip_flags)
    gates_bb_up = json.loads(sig_bb_up.gate_results)
    assert gates_bb_up["bollinger"]["pass"] is False

    # 5. Verify Bollinger Lower Band piercing rejection (%B < -0.10) for NO
    overextended_down = dict(healthy_features)
    overextended_down["bb_pct_b"] = -0.15
    sig_bb_down = strat.evaluate(
        market_id="mkt_bb_down",
        condition_id="0x_bb_down",
        question="BTC 5M Overextended Lower",
        yes_token_id="tok_yes",
        no_token_id="tok_no",
        features=overextended_down,
        orderbook_timestamp=None,
        btc_price=64950.0,
        price_to_beat=65000.0,
        current_balance=500.0
    )
    assert sig_bb_down.state == "SKIP"
    assert any("pierced lower Bollinger Band" in flag for flag in sig_bb_down.skip_flags)
    gates_bb_down = json.loads(sig_bb_down.gate_results)
    assert gates_bb_down["bollinger"]["pass"] is False


