from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.db.models import BacktestRun
from app.research.dataset import DatasetBuilder
from app.research.backtester import Backtester

router = APIRouter()

@router.get("/status")
def get_research_status():
    builder = DatasetBuilder()
    return builder.check_research_readiness()

@router.post("/backtest/run")
def run_backtest():
    """
    Kicks off an isolated backtest run over real data using Phase 3 and Phase 4 systems.
    Does not interact with live paper positions.
    """
    backtester = Backtester()
    result = backtester.run_backtest()
    return result

@router.get("/backtest/latest")
def get_latest_backtest(db: Session = Depends(get_db)):
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
