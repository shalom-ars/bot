"""
BTC 5M API endpoints.
Provides dashboard data for the BTC 5M module.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.session import get_db
from app.db.models import BTC5MMarket, BTC5MSignal, BTC5MTrade
from app.api.security import get_current_user
from datetime import datetime, timezone, timedelta

router = APIRouter()


@router.get("/markets")
def get_btc5m_markets(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """All discovered BTC 5M markets with latest CLOB data."""
    markets = db.query(BTC5MMarket).order_by(BTC5MMarket.last_seen.desc()).offset(skip).limit(limit).all()
    total = db.query(BTC5MMarket).count()
    valid = db.query(BTC5MMarket).filter(BTC5MMarket.is_valid == True).count()
    return {
        "total": total,
        "valid": valid,
        "markets": [_format_market(m) for m in markets]
    }


@router.get("/signals")
def get_btc5m_signals(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Recent BTC 5M signals with full audit trail."""
    signals = db.query(BTC5MSignal).order_by(BTC5MSignal.timestamp.desc()).offset(skip).limit(limit).all()
    total = db.query(BTC5MSignal).count()
    enters = db.query(BTC5MSignal).filter(BTC5MSignal.state == "ENTER").count()
    skips  = db.query(BTC5MSignal).filter(BTC5MSignal.state == "SKIP").count()
    return {
        "total": total,
        "enters": enters,
        "skips": skips,
        "signals": [_format_signal(s) for s in signals]
    }


@router.get("/trades")
def get_btc5m_trades(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """BTC 5M paper trades."""
    trades = db.query(BTC5MTrade).order_by(BTC5MTrade.entry_time.desc()).offset(skip).limit(limit).all()
    total  = db.query(BTC5MTrade).count()
    open_  = db.query(BTC5MTrade).filter(BTC5MTrade.status == "OPEN").count()
    closed = db.query(BTC5MTrade).filter(BTC5MTrade.status == "CLOSED").count()

    closed_trades = db.query(BTC5MTrade).filter(BTC5MTrade.status == "CLOSED").all()
    realized_pnl = sum((t.pnl or 0) for t in closed_trades)
    wins  = sum(1 for t in closed_trades if (t.pnl or 0) > 0)
    losses = sum(1 for t in closed_trades if (t.pnl or 0) < 0)
    win_rate = (wins / len(closed_trades) * 100) if closed_trades else 0

    return {
        "total": total,
        "open": open_,
        "closed": closed,
        "realized_pnl": round(realized_pnl, 4),
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2),
        "trades": [_format_trade(t) for t in trades]
    }


import httpx

from app.btc5m.engine import btc5m_engine
from pydantic import BaseModel

class ToggleTradingRequest(BaseModel):
    active: bool

@router.post("/toggle_trading")
def toggle_trading(req: ToggleTradingRequest, db: Session = Depends(get_db)):
    btc5m_engine.trading_active = req.active
    
    # Force engine to clear cached markets if starting fresh
    if req.active:
        if hasattr(btc5m_engine, '_market_states'):
            btc5m_engine._market_states.clear()
        
    from app.db.models import BTC5MAudit
    audit = BTC5MAudit(
        action="START" if req.active else "STOP",
        details="Bot started manually via UI" if req.active else "Bot stopped manually via UI"
    )
    db.add(audit)
    db.commit()
    
    return {"status": "success", "trading_active": btc5m_engine.trading_active}

@router.get("/status")
def get_btc5m_status(db: Session = Depends(get_db)):
    """Returns the current market, next market, and active trade."""
    now = datetime.now(timezone.utc)
    # Since DB timestamps might be naive UTC, strip tzinfo for comparison
    now_naive = now.replace(tzinfo=None)

    current_market = db.query(BTC5MMarket).filter(
        BTC5MMarket.start_time <= now_naive,
        BTC5MMarket.end_time > now_naive
    ).order_by(BTC5MMarket.start_time.desc()).first()

    next_market = db.query(BTC5MMarket).filter(
        BTC5MMarket.start_time > now_naive
    ).order_by(BTC5MMarket.start_time.asc()).first()

    open_trade = db.query(BTC5MTrade).filter(BTC5MTrade.status == "OPEN").first()
    
    open_trade_dict = _format_trade(open_trade) if open_trade else None
    if open_trade_dict:
        trade_market = db.query(BTC5MMarket).filter(BTC5MMarket.market_id == open_trade.market_id).first()
        if trade_market:
            best_bid = trade_market.best_bid
            best_ask = trade_market.best_ask
            
            # If the market expired, Polymarket might drop the book to 0 or spread 1.0. Fallback to last known price history.
            if best_bid is None or best_ask is None or (best_ask - best_bid) > 0.5:
                from app.db.models import BTC5MPriceHistory
                last_hist = db.query(BTC5MPriceHistory).filter(
                    BTC5MPriceHistory.market_id == open_trade.market_id,
                    (BTC5MPriceHistory.best_ask - BTC5MPriceHistory.best_bid) < 0.5
                ).order_by(BTC5MPriceHistory.timestamp.desc()).first()
                if last_hist:
                    best_bid = last_hist.best_bid
                    best_ask = last_hist.best_ask
                else:
                    best_bid = None
                    best_ask = None

            if best_bid is not None and best_ask is not None and (best_ask - best_bid) <= 0.5:
                if open_trade.side == "BUY":
                    current_price = best_bid
                else:
                    current_price = 1.0 - best_ask
                
                unrealized_pnl = (current_price - open_trade.entry_price) * open_trade.quantity
                open_trade_dict["current_price"] = current_price
                open_trade_dict["unrealized_pnl"] = unrealized_pnl
                open_trade_dict["pnl_pct"] = (unrealized_pnl / open_trade.position_size) * 100 if open_trade.position_size > 0 else 0
            else:
                open_trade_dict["current_price"] = None
                open_trade_dict["unrealized_pnl"] = None
                open_trade_dict["pnl_pct"] = None

    import httpx
    # Fetch Chainlink Price
    btc_price = None
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.post("https://polygon-bor-rpc.publicnode.com", json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_call",
                "params": [{"to": "0xc907E116054Ad103354f2D350FD2514433D57F6f", "data": "0x50d25bcd"}, "latest"]
            })
            if resp.status_code == 200:
                res_json = resp.json()
                if "result" in res_json and res_json["result"] != "0x":
                    hex_answer = res_json["result"]
                    btc_price = int(hex_answer, 16) / 100000000.0
    except Exception as e:
        pass

    # Fetch Price-to-Beat.
    #
    # IMPORTANT:
    # Do NOT use the previous market's finalPrice as the active
    # market's Price-to-Beat. finalPrice is settlement data.
    #
    # The active BTC5M Gamma payload does not reliably expose the
    # opening Price-to-Beat field. Until an authoritative active
    # reference value is available, keep this unavailable so the
    # strategy safely SKIPs rather than trading on fabricated data.
    price_to_beat = None

    # Get latest signal scores for current market
    yes_score = 0
    no_score = 0
    latest_sig = db.query(BTC5MSignal).order_by(BTC5MSignal.timestamp.desc()).first()
    if latest_sig and current_market and latest_sig.market_id == current_market.market_id:
        yes_score = getattr(latest_sig, "yes_score", 0.0)
        no_score = getattr(latest_sig, "no_score", 0.0)

    return {
        "trading_active": btc5m_engine.trading_active,
        "current_market": _format_market(current_market) if current_market else None,
        "next_market": _format_market(next_market) if next_market else None,
        "open_trade": open_trade_dict,
        "chainlink_btc_usd": btc_price,
        "price_to_beat": price_to_beat,
        "yes_score": yes_score,
        "no_score": no_score,
        "latest_signal": latest_sig.state if latest_sig else None
    }


@router.get("/skips")
def get_btc5m_skips(db: Session = Depends(get_db), limit: int = 50):
    from app.db.models import BTC5MSkip
    skips = db.query(BTC5MSkip).order_by(BTC5MSkip.timestamp.desc()).limit(limit).all()
    return [{"id": s.id, "market_id": s.market_id, "question": s.question, "yes_score": s.yes_score, "no_score": s.no_score, "net_edge": s.net_edge, "spread": s.spread, "liquidity": s.liquidity, "time_remaining": s.time_remaining, "planned_rr": s.planned_rr, "skip_reason": s.skip_reason, "timestamp": s.timestamp.isoformat() if s.timestamp else None, "actual_resolution": s.actual_resolution, "hypothetical_outcome": s.hypothetical_outcome} for s in skips]

@router.get("/stats")
def get_btc5m_stats(db: Session = Depends(get_db)):
    """BTC 5M strategy performance statistics."""
    total_markets   = db.query(BTC5MMarket).count()
    valid_markets   = db.query(BTC5MMarket).filter(BTC5MMarket.is_valid == True).count()
    total_signals   = db.query(BTC5MSignal).count()
    enter_signals   = db.query(BTC5MSignal).filter(BTC5MSignal.state == "ENTER").count()
    skip_signals    = db.query(BTC5MSignal).filter(BTC5MSignal.state == "SKIP").count()
    from app.db.models import BTC5MSkip
    total_skips = db.query(BTC5MSkip).count()
    hypothetical_wins = db.query(BTC5MSkip).filter(BTC5MSkip.hypothetical_outcome == "WIN").count()
    hypothetical_losses = db.query(BTC5MSkip).filter(BTC5MSkip.hypothetical_outcome == "LOSS").count()
    
    total_trades    = db.query(BTC5MTrade).count()
    open_trades     = db.query(BTC5MTrade).filter(BTC5MTrade.status == "OPEN").count()
    closed_trades_q = db.query(BTC5MTrade).filter(BTC5MTrade.status == "CLOSED").all()
    realized_pnl    = sum((t.pnl or 0) for t in closed_trades_q)
    wins            = sum(1 for t in closed_trades_q if (t.pnl or 0) > 0)
    losses          = sum(1 for t in closed_trades_q if (t.pnl or 0) < 0)
    win_rate        = (wins / len(closed_trades_q) * 100) if closed_trades_q else 0
    
    # Calculate R:R
    winning_trades = [t for t in closed_trades_q if (t.pnl or 0) > 0]
    losing_trades = [t for t in closed_trades_q if (t.pnl or 0) < 0]
    avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0
    avg_loss = sum(abs(t.pnl) for t in losing_trades) / len(losing_trades) if losing_trades else 0
    historical_rr = avg_win / avg_loss if avg_loss > 0 else 0
    profit_factor = sum(t.pnl for t in winning_trades) / sum(abs(t.pnl) for t in losing_trades) if losing_trades else 0
    expectancy = (win_rate/100 * avg_win) - ((1 - win_rate/100) * avg_loss)

    # Avg net edge from signals
    enter_sigs = db.query(BTC5MSignal).filter(BTC5MSignal.state == "ENTER").all()
    avg_net_edge = sum(s.net_edge or 0 for s in enter_sigs) / len(enter_sigs) if enter_sigs else 0
    avg_spread   = sum(s.spread or 0 for s in enter_sigs) / len(enter_sigs) if enter_sigs else 0
    avg_slippage = sum(s.slippage_cost or 0 for s in enter_sigs) / len(enter_sigs) if enter_sigs else 0

    # Last activity
    last_signal = db.query(BTC5MSignal).order_by(BTC5MSignal.timestamp.desc()).first()

    return {
        "module": "BTC_5M",
        "data_source": "Polymarket CLOB (live only, no synthetic data)",
        "execution_mode": "paper",
        "live_trading_enabled": False,
        "total_markets_analyzed": total_markets,
        "valid_markets": valid_markets,
        "total_signals": total_signals,
        "enter_signals": enter_signals,
        "skip_signals": skip_signals,
        "total_trades": total_trades,
        "open_trades": open_trades,
        "closed_trades": len(closed_trades_q),
        "total_skips_recorded": total_skips,
        "hypothetical_skip_wins": hypothetical_wins,
        "hypothetical_skip_losses": hypothetical_losses,
        "realized_pnl": round(realized_pnl, 4),
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2),
        "avg_winning_trade": round(avg_win, 2),
        "avg_losing_trade": round(avg_loss, 2),
        "actual_historical_rr": round(historical_rr, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy": round(expectancy, 2),
        "avg_net_edge": round(avg_net_edge, 4),
        "avg_spread": round(avg_spread, 4),
        "avg_slippage": round(avg_slippage, 4),
        "last_signal_at": last_signal.timestamp.isoformat() if last_signal else None,
        "strategy_params": {
            "min_momentum": 0.01,
            "min_imbalance": 0.05,
            "max_volatility": 0.08,
            "max_spread": 0.05,
            "min_depth_usd": 50.0,
            "min_liquidity_usd": 100.0,
            "min_time_remaining_sec": 60,
            "min_net_edge": 0.03,
            "risk_per_trade_pct": 2.0,
            "model_version": "rule_based_btc5m",
        }
    }


def _format_market(m: BTC5MMarket) -> dict:
    now = datetime.now(timezone.utc)
    end = m.end_time.replace(tzinfo=timezone.utc) if m.end_time and m.end_time.tzinfo is None else m.end_time
    remaining = (end - now).total_seconds() if end else None
    return {
        "market_id": m.market_id,
        "condition_id": m.condition_id,
        "question": m.question,
        "yes_token_id": m.yes_token_id,
        "no_token_id": m.no_token_id,
        "end_time": m.end_time.isoformat() if m.end_time else None,
        "start_time": m.start_time.isoformat() if m.start_time else None,
        "time_remaining_sec": remaining,
        "best_bid": m.best_bid,
        "best_ask": m.best_ask,
        "bid_depth": m.bid_depth,
        "ask_depth": m.ask_depth,
        "spread": m.spread,
        "spread_pct": round((m.spread / m.best_ask * 100), 2) if m.best_ask and m.spread else None,
        "mid_price": m.mid_price,
        "imbalance": m.imbalance,
        "liquidity": m.liquidity,
        "orderbook_timestamp": m.orderbook_timestamp.isoformat() if m.orderbook_timestamp else None,
        "is_valid": m.is_valid,
        "rejection_reason": m.rejection_reason,
        "last_seen": m.last_seen.isoformat() if m.last_seen else None,
    }


def _format_signal(s: BTC5MSignal) -> dict:
    return {
        "id": s.id,
        "market_id": s.market_id,
        "question": s.question,
        "timestamp": s.timestamp.isoformat() if s.timestamp else None,
        "state": s.state,
        "side": s.side,
        "entry_price": s.entry_price,
        "bid": s.bid,
        "ask": s.ask,
        "spread": s.spread,
        "bid_depth": s.bid_depth,
        "ask_depth": s.ask_depth,
        "momentum": s.momentum,
        "imbalance": s.imbalance,
        "ob_pressure": s.ob_pressure,
        "volatility": s.volatility,
        "momentum_persistence": s.momentum_persistence,
        "market_probability": s.market_probability,
        "fair_probability": s.fair_probability,
        "raw_edge": s.raw_edge,
        "spread_cost": s.spread_cost,
        "slippage_cost": s.slippage_cost,
        "fees": s.fees,
        "net_edge": s.net_edge,
        "risk_pct": s.risk_pct,
        "position_size": s.position_size,
        "time_remaining_sec": s.time_remaining_sec,
        "model_version": s.model_version,
        "strategy": s.strategy,
        "reason": s.reason,
    }


def _format_trade(t: BTC5MTrade) -> dict:
    return {
        "id": t.id,
        "market_id": t.market_id,
        "question": t.question,
        "side": t.side,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "quantity": t.quantity,
        "position_size": t.position_size,
        "spread_at_entry": t.spread_at_entry,
        "momentum_at_entry": t.momentum_at_entry,
        "imbalance_at_entry": t.imbalance_at_entry,
        "time_remaining_at_entry": t.time_remaining_at_entry,
        "net_edge": t.net_edge,
        "planned_risk": t.planned_risk,
        "planned_reward": t.planned_reward,
        "planned_rr": t.planned_rr,
        "actual_rr": getattr(t, 'actual_rr', None),
        "stop_loss_price": t.stop_loss_price,
        "take_profit_price": t.take_profit_price,
        "strategy": t.strategy,
        "model_version": t.model_version,
        "entry_reason": t.entry_reason,
        "exit_reason": t.exit_reason,
        "status": t.status,
        "entry_time": t.entry_time.isoformat() if t.entry_time else None,
        "exit_time": t.exit_time.isoformat() if t.exit_time else None,
        "pnl": t.pnl,
        "resolution": t.resolution,
    }

@router.get("/chart")
def get_btc5m_chart(market_id: str, db: Session = Depends(get_db)):
    from app.db.models import BTC5MPriceHistory
    history = db.query(BTC5MPriceHistory).filter(
        BTC5MPriceHistory.market_id == market_id
    ).order_by(BTC5MPriceHistory.timestamp.asc()).all()
    
    data = []
    for h in history:
        data.append({
            "time": h.timestamp.isoformat(),
            "yes_bid": h.best_bid,
            "yes_ask": h.best_ask
        })
    return {"history": data}
