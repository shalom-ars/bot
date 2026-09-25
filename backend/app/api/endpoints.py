from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Market, Trade, Position

router = APIRouter()

@router.get("/markets")
def get_markets(db: Session = Depends(get_db)):
    return db.query(Market).filter(Market.active == True).all()

@router.get("/positions")
def get_positions(db: Session = Depends(get_db)):
    return db.query(Position).all()

@router.get("/trades")
def get_trades(db: Session = Depends(get_db)):
    return db.query(Trade).order_by(Trade.timestamp.desc()).limit(50).all()

@router.get("/health")
def get_health():
    from app.engine.scanner import orchestrator
    from app.config import settings
    health_data = orchestrator.get_health()
    
    # Format according to exact user requirements
    poly_status = health_data.get("poly", {}).get("status", "DISCONNECTED")
    
    return {
        "backend_running": True,
        "polymarket_connected": poly_status == "CONNECTED",
        "research_mode_active": settings.research_mode,
        "paper_execution_active": settings.execution_mode == "paper",
        "internal_health": health_data
    }

@router.get("/debug/polymarket")
async def get_polymarket_debug(db: Session = Depends(get_db)):
    from app.main import orchestrator
    return orchestrator.get_health()

@router.get("/strategy/status")
async def get_strategy_status(db: Session = Depends(get_db)):
    from app.db.models import Signal, Trade, MarketSnapshot
    from app.config import settings

    total_scanned = db.query(MarketSnapshot).count()
    total_signals = db.query(Signal).count()
    buy_signals   = db.query(Signal).filter(Signal.signal_type == "BUY").count()
    sell_signals  = db.query(Signal).filter(Signal.signal_type == "SELL").count()
    skipped       = db.query(Signal).filter(Signal.signal_type == "SKIP").count()
    actionable    = buy_signals + sell_signals

    trades   = db.query(Trade).all()
    paper_trades = len(trades)
    open_positions = len([t for t in trades if t.status == "OPEN"])
    filled_paper_trades = len([t for t in trades if t.status == "CLOSED"])

    net_pnl  = sum(t.pnl for t in trades if t.pnl)
    wins     = len([t for t in trades if t.pnl and t.pnl > 0])
    win_rate = wins / filled_paper_trades if filled_paper_trades else 0.0

    actionable_signals = db.query(Signal).filter(Signal.signal_type != "SKIP").order_by(Signal.id.desc()).limit(100).all()
    avg_net_edge = sum(s.net_edge for s in actionable_signals if s.net_edge is not None) / len(actionable_signals) if actionable_signals else 0.0
    avg_raw_edge = sum(s.raw_edge for s in actionable_signals if s.raw_edge is not None) / len(actionable_signals) if actionable_signals else 0.0
    avg_spread = sum(s.spread_cost for s in actionable_signals if s.spread_cost is not None) / len(actionable_signals) if actionable_signals else 0.0
    avg_slippage = sum(s.slippage_cost for s in actionable_signals if s.slippage_cost is not None) / len(actionable_signals) if actionable_signals else 0.0
    
    # Skip reasons distribution
    skip_records = db.query(Signal.reason).filter(Signal.signal_type == "SKIP").all()
    skip_reasons = {}
    for r in skip_records:
        reason = r[0] or "Unknown"
        skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
        
    # Strategy distribution
    strategy_records = db.query(Signal.strategy).filter(Signal.signal_type != "SKIP").all()
    strategies = {}
    for r in strategy_records:
        strat = r[0] or "Unknown"
        strategies[strat] = strategies.get(strat, 0) + 1

    return {
        "research_mode":       settings.research_mode,
        "live_data":           settings.data_mode == "live",
        "no_trading":          settings.research_mode,
        "synthetic_enabled":   settings.synthetic_bootstrap,
        "signals": {
            "scanned": total_scanned,
            "generated": total_signals,
            "actionable": actionable,
            "buy": buy_signals,
            "sell": sell_signals,
            "skipped": skipped
        },
        "trades": {
            "paper": paper_trades,
            "open_positions": open_positions,
            "filled": filled_paper_trades
        },
        "metrics": {
            "avg_net_edge": avg_net_edge,
            "avg_raw_edge": avg_raw_edge,
            "avg_spread": avg_spread,
            "avg_slippage": avg_slippage,
            "avg_execution_cost": avg_spread + avg_slippage
        },
        "skip_reasons": skip_reasons,
        "strategies": strategies,
        "total_signals":       actionable, # Legacy mapping
        "buy_signals":         buy_signals,
        "win_rate":            win_rate,
        "net_pnl":             net_pnl,
        "avg_edge_last_100":   avg_net_edge, # Point to net edge
    }


@router.get("/research/quality")
async def get_research_quality():
    """
    Returns real-data quality report and the real-backtest gate evaluation.
    """
    from app.research.dataset import get_data_quality_report
    return get_data_quality_report()

@router.get("/research/status")
async def get_research_status():
    from app.research.dataset import DatasetBuilder
    builder = DatasetBuilder()
    return builder.check_research_readiness()

@router.post("/backtest/run")
async def run_backtest():
    """
    Kicks off an isolated backtest run over real data using Phase 3 and Phase 4 systems.
    Does not interact with live paper positions.
    """
    from app.research.backtester import Backtester
    backtester = Backtester()
    return backtester.run_backtest()

@router.get("/backtest/latest")
async def get_latest_backtest(db: Session = Depends(get_db)):
    from sqlalchemy import desc
    from app.db.models import BacktestRun
    latest = db.query(BacktestRun).order_by(desc(BacktestRun.created_at)).first()
    if not latest:
        return {"status": "NONE"}
    return {
        "status": latest.status,
        "run_id": latest.run_id,
        "trades": latest.trades,
        "win_rate": latest.win_rate,
        "net_pnl": latest.net_pnl,
        "max_drawdown": latest.max_drawdown,
        "resolved_markets": latest.resolved_markets,
        "valid_samples": latest.valid_samples,
        "brier_score": latest.brier_score
    }

@router.get("/paper-test/health")
async def get_paper_test_health(db: Session = Depends(get_db)):
    from app.engine.scanner import orchestrator
    from app.config import settings
    from app.db.models import MarketSnapshot
    
    snaps = db.query(MarketSnapshot).count()
    
    # orchestrator.paper_controller handles long term stats
    pc_status = {}
    if hasattr(orchestrator, 'paper_controller'):
        orchestrator.paper_controller.update_session_stats()
        pc_status = orchestrator.paper_controller.get_health_status()
        
    return {
        "collector_status": "ACTIVE" if orchestrator.running else "STOPPED",
        "data_mode": settings.data_mode,
        "execution_mode": settings.execution_mode,
        "live_trading": settings.execution_mode == "live",
        "database_status": "OK",
        "snapshot_count": snaps,
        **pc_status
    }

@router.get("/live/status")
async def get_live_status():
    from app.config import settings
    return {
        "execution_mode": settings.execution_mode,
        "live_trading_enabled": settings.live_trading_enabled,
        "kill_switch_active": settings.live_trading_kill_switch,
        "configured_live_capital": settings.live_initial_capital,
        "live_orders_submitted": 0, # Placeholder for Phase 7
        "status": "DISABLED_BY_CONFIG" if settings.execution_mode == "paper" else "ACTIVE"
    }

@router.get("/live/eligibility")
async def get_live_eligibility():
    from app.trading.eligibility import LiveEligibilityGate
    return LiveEligibilityGate.check_eligibility()

@router.get("/risk/status")
async def get_risk_status(db: Session = Depends(get_db)):
    from app.engine.scanner import orchestrator
    
    risk = orchestrator.paper_engine.risk
    
    return {
        "status": "RUNNING" if not risk.is_paused else "PAUSED",
        "trading_allowed": not risk.is_paused,
        "pause_reason": risk.pause_reason,
        "balance": risk.current_balance,
        "equity": risk.current_balance + sum(p.unrealized_pnl for p in db.query(Position).all() if p.unrealized_pnl),
        "available_balance": risk.current_balance - risk.current_exposure,
        "open_exposure": risk.current_exposure,
        "market_exposure": "Aggregated dynamically",
        "condition_exposure": "Aggregated dynamically",
        "daily_pnl": risk.daily_pnl,
        "daily_loss_limit": risk.max_daily_loss * risk.starting_balance,
        "peak_equity": risk.peak_balance,
        "drawdown": (risk.peak_balance - risk.current_balance) / risk.peak_balance if risk.peak_balance > 0 else 0.0,
        "drawdown_limit": risk.max_drawdown,
        "consecutive_losses": risk.consecutive_losses,
        "consecutive_loss_limit": risk.max_consecutive_losses,
        "open_positions": risk.open_positions_count,
        "risk_per_trade_limit": risk.risk_per_trade * risk.current_balance
    }

@router.get("/pnl")
def get_pnl(db: Session = Depends(get_db)):
    # simple mock calculation
    trades = db.query(Trade).filter(Trade.status == "CLOSED").all()
    realized = sum(t.pnl for t in trades if t.pnl)
    positions = db.query(Position).all()
    unrealized = sum(p.unrealized_pnl for p in positions if p.unrealized_pnl)
    return {"realized": realized, "unrealized": unrealized, "total": realized + unrealized}

@router.post("/demo/reset")
@router.post("/trades/demo/reset")
def reset_demo_router_alias(
    db: Session = Depends(get_db)
):
    from app.fast5m.executor import fast_executor
    return fast_executor.reset_demo_account(user_id=None)
