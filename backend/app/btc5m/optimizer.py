"""
BTC 5M Adaptive Strategy Optimizer & Autonomous Self-Learning Engine.

Continuously analyzes winning and losing trades, performs post-mortem root-cause
diagnostics on every lost trade, and dynamically optimizes strategy filters,
entry score thresholds, risk-reward parameters, and indicators within strict safety bounds.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List
from sqlalchemy.orm import Session
from sqlalchemy import desc

import os
from app.db.models import BTC5MTrade, BTC5MSelfLearningLog
from app.btc5m.settings_manager import get_btc5m_settings, update_btc5m_settings

logger = logging.getLogger(__name__)

OPTIMIZER_LOG_FILE = os.environ.get(
    "OPTIMIZER_LOG_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "self_learning_optimizer.log")
)


def append_optimizer_log_entry(
    event_type: str,
    instance_id: str,
    trade_id: Optional[int],
    outcome: str,
    root_cause: str,
    error_analysis: str,
    param_adjusted: str,
    old_value: str,
    new_value: str,
    adaptation_delta: str,
    pnl: Optional[float] = None
) -> None:
    """Appends an immutable audit entry to the physical self_learning_optimizer.log file on disk."""
    try:
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        pnl_str = f" | PnL: ${pnl:+.2f}" if pnl is not None else ""
        trade_str = f"Trade #{trade_id}" if trade_id is not None else "Periodic Sweep"
        
        # Initialize file with header if missing
        if not os.path.exists(OPTIMIZER_LOG_FILE):
            os.makedirs(os.path.dirname(OPTIMIZER_LOG_FILE), exist_ok=True)
            with open(OPTIMIZER_LOG_FILE, "w", encoding="utf-8") as f:
                f.write(
                    "================================================================================\n"
                    "JONANDA BTC 5M AUTONOMOUS SELF-LEARNING OPTIMIZER LOG FILE\n"
                    f"Initialized: {now_str} | Module: BTC 5M Multi-Factor Engine\n"
                    "Tracks persistent post-mortem error analyses, filter tuning, and optimization sweeps.\n"
                    "================================================================================\n\n"
                )

        entry = (
            f"--------------------------------------------------------------------------------\n"
            f"[{now_str}] [{event_type.upper()}] Instance: {instance_id} | {trade_str}{pnl_str}\n"
            f"Outcome: {outcome} | Root Cause: {root_cause}\n"
            f"Diagnostic Analysis: {error_analysis}\n"
            f"Parameter Tuned: {param_adjusted}\n"
            f"Value Transition: {old_value} -> {new_value} (Delta: {adaptation_delta})\n"
            f"Status: APPLIED & COMMITTED TO RUNTIME ENGINE\n"
            f"--------------------------------------------------------------------------------\n\n"
        )
        with open(OPTIMIZER_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as e:
        logger.warning(f"[Self-Learning Optimizer] Failed to write to disk log {OPTIMIZER_LOG_FILE}: {e}")


def read_optimizer_log_file(max_lines: int = 500) -> str:
    """Reads the tail of self_learning_optimizer.log file."""
    if not os.path.exists(OPTIMIZER_LOG_FILE):
        return (
            "================================================================================\n"
            "JONANDA BTC 5M AUTONOMOUS SELF-LEARNING OPTIMIZER LOG FILE\n"
            "Status: STANDBY / ACTIVE LISTENING\n"
            "No log events recorded yet. The engine logs every lost-trade post-mortem diagnosis\n"
            "and continuous optimization sweep automatically to this file.\n"
            "================================================================================"
        )
    try:
        with open(OPTIMIZER_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return "".join(lines[-max_lines:])
    except Exception as e:
        return f"Error reading log file {OPTIMIZER_LOG_FILE}: {e}"


# Strict Safety Boundaries to prevent over-tightening or reckless widening
SAFETY_BOUNDS: Dict[str, Tuple[float, float]] = {
    "min_entry_score": (35.0, 65.0),
    "min_entry_probability": (0.35, 0.60),
    "min_net_edge": (-0.035, 0.005),
    "min_order_book_imbalance": (0.01, 0.05),
    "min_p2b_diff": (0.5, 8.0),
    "min_entry_price": (0.25, 0.45),
    "max_entry_price": (0.55, 0.75),
    "tp_dollar": (0.80, 2.50),
    "sl_dollar": (1.50, 3.50),
    "dynamic_sl_delta": (0.15, 0.35),
    "soft_stop_confirmation_seconds": (2.0, 8.0),
    "rsi_overbought": (64.0, 78.0),
    "rsi_oversold": (22.0, 36.0),
}


class BTC5MSelfLearningOptimizer:
    """
    Autonomous self-learning agent for BTC 5M Quantitative Trading.
    Diagnoses prediction errors, adapts filters, and records audit logs.
    """

    def __init__(self, instance_id: str = "instance_1"):
        self.instance_id = instance_id

    def analyze_closed_trade(self, db: Session, trade: BTC5MTrade) -> Optional[BTC5MSelfLearningLog]:
        """
        Invoked immediately upon trade closure.
        If the trade was a loss, performs root-cause prediction error diagnosis
        and tunes strategy filters to prevent repeating the mistake.
        """
        try:
            if trade.pnl is None:
                return None

            # Only lost trades require post-mortem parameter correction
            if trade.pnl >= 0:
                logger.info(f"[Self-Learning Optimizer] Trade #{trade.id} was profitable (+${trade.pnl:.2f}). No loss correction needed.")
                return None

            current_settings = get_btc5m_settings(db, instance_id=self.instance_id)

            # 1. Diagnose Root Cause of the Prediction Error
            root_cause, error_analysis, target_param, adjustment_delta = self._diagnose_prediction_error(
                trade=trade,
                settings=current_settings
            )

            # 2. Compute New Value with Safety Clamping
            old_val_raw = current_settings.get(target_param)
            try:
                old_val_float = float(old_val_raw)
            except (ValueError, TypeError):
                old_val_float = 40.0

            bounds = SAFETY_BOUNDS.get(target_param, (old_val_float * 0.7, old_val_float * 1.3))
            new_val_float = max(bounds[0], min(bounds[1], old_val_float + adjustment_delta))
            
            # Format according to parameter precision
            if target_param in ("min_entry_score", "min_p2b_diff", "rsi_overbought", "rsi_oversold"):
                old_val_str = f"{old_val_float:.1f}"
                new_val_str = f"{new_val_float:.1f}"
            elif target_param in ("tp_dollar", "sl_dollar", "dynamic_sl_delta", "min_entry_price", "max_entry_price"):
                old_val_str = f"{old_val_float:.2f}"
                new_val_str = f"{new_val_float:.2f}"
            else:
                old_val_str = f"{old_val_float:.3f}"
                new_val_str = f"{new_val_float:.3f}"

            # 3. Apply Setting Adaptation to Database
            update_btc5m_settings(
                db=db,
                updates={target_param: new_val_str},
                user_info=f"AI_OPTIMIZER_TRADE_{trade.id}",
                instance_id=self.instance_id
            )

            # 4. Create and Persist Self-Learning History Log
            log_entry = BTC5MSelfLearningLog(
                instance_id=self.instance_id,
                trade_id=trade.id,
                market_id=trade.market_id,
                timestamp=datetime.now(timezone.utc),
                outcome="LOSS",
                pnl=trade.pnl,
                root_cause=root_cause,
                error_analysis=error_analysis,
                parameter_adjusted=target_param,
                old_value=old_val_str,
                new_value=new_val_str,
                adaptation_delta=f"{adjustment_delta:+.3f}",
                status="APPLIED"
            )
            db.add(log_entry)
            db.commit()
            db.refresh(log_entry)

            # Persist to physical disk log file
            append_optimizer_log_entry(
                event_type="POST_MORTEM_DIAGNOSIS",
                instance_id=self.instance_id,
                trade_id=trade.id,
                outcome="LOSS",
                root_cause=root_cause,
                error_analysis=error_analysis,
                param_adjusted=target_param,
                old_value=old_val_str,
                new_value=new_val_str,
                adaptation_delta=f"{adjustment_delta:+.3f}",
                pnl=trade.pnl
            )

            logger.info(
                f"[Self-Learning Optimizer] Diagnosed Trade #{trade.id} loss (${trade.pnl:.2f}) as [{root_cause}]. "
                f"Adapted {target_param}: {old_val_str} -> {new_val_str} ({adjustment_delta:+.3f}). Log #{log_entry.id} saved."
            )
            return log_entry

        except Exception as e:
            logger.error(f"[Self-Learning Optimizer] Error analyzing trade #{trade.id}: {e}", exc_info=True)
            db.rollback()
            return None

    def _diagnose_prediction_error(
        self,
        trade: BTC5MTrade,
        settings: Dict[str, Any]
    ) -> Tuple[str, str, str, float]:
        """
        Determines the exact reason a prediction failed and selects the optimal corrective delta.
        Returns:
            (root_cause, error_analysis, target_parameter, adjustment_delta)
        """
        locked_pred = trade.locked_predicted_side or ("YES" if trade.side == "BUY" else "NO")
        score = trade.entry_yes_score if locked_pred == "YES" else trade.entry_no_score
        exit_reason = (trade.exit_reason or "").upper()
        resolution = (trade.resolution or "").upper()
        imbalance = trade.imbalance_at_entry or 0.0
        momentum = trade.momentum_at_entry or 0.0

        # Case 1: Stop-Loss limit was hit ($2.00 hard stop or thesis collapse)
        if "STOP LOSS" in exit_reason or "HARD SAFETY STOP" in exit_reason or trade.exit_decision_state == "HARD_EXIT":
            # If imbalance was marginal, orderbook spoofing likely gave a false entry trigger
            if abs(imbalance) < 0.035:
                return (
                    "OBI_FAKE_WALL",
                    f"Order book imbalance ({imbalance:+.2f}) was shallow and collapsed rapidly post-entry, leading to adverse stop-out.",
                    "min_order_book_imbalance",
                    +0.005
                )
            
            # If score was in the lower quartile (e.g. < 44.0), entry had insufficient conviction
            if score is not None and score < 45.0:
                return (
                    "LOW_CONVICTION_NOISE",
                    f"Entry prediction score ({score:.1f}) was near threshold ({settings.get('min_entry_score', 40):.1f}), making it vulnerable to random market noise.",
                    "min_entry_score",
                    +2.0
                )

            # Otherwise, stop-loss was too tight for current candle volatility
            return (
                "STOP_LOSS_TOO_TIGHT",
                f"Position stopped out at -${abs(trade.pnl):.2f} due to short-term candle volatility spikes before thesis could mature.",
                "dynamic_sl_delta",
                +0.02
            )

        # Case 2: Market Resolution settled against predicted side
        if resolution in ("YES", "NO") and resolution != locked_pred:
            # Check if entry probability was marginal (< 44%)
            fair_p = trade.entry_fair_probability or 0.50
            effective_p = fair_p if locked_pred == "YES" else (1.0 - fair_p)
            if effective_p < 0.44:
                return (
                    "PROBABILITY_DEFICIT",
                    f"Directional probability ({effective_p*100:.1f}%) was insufficient to withstand binary settlement spread against {resolution}.",
                    "min_entry_probability",
                    +0.02
                )

            # Check if momentum reversed against the trade
            if (locked_pred == "YES" and momentum < 0) or (locked_pred == "NO" and momentum > 0):
                return (
                    "MOMENTUM_REVERSAL",
                    f"Entry momentum ({momentum:+.3f}) diverged from market settlement direction ({resolution}), resulting in counter-trend lock.",
                    "min_entry_score",
                    +1.5
                )

            # Price-To-Beat chop near settlement
            p2b_diff_curr = float(settings.get("min_p2b_diff", 1.5))
            if p2b_diff_curr < 2.5:
                return (
                    "P2B_CHOP",
                    f"Final settlement resolved to {resolution} due to micro-price oscillation across Price-to-Beat boundary. Slightly adjusting P2B boundary without closing entry window.",
                    "min_p2b_diff",
                    +0.3
                )
            else:
                return (
                    "P2B_CHOP",
                    f"Micro-price oscillation across Price-to-Beat boundary near resolution. Widening dynamic stop buffer to absorb boundary noise.",
                    "dynamic_sl_delta",
                    +0.02
                )

        # Default fallback diagnosis: General prediction error
        return (
            "PREDICTION_DIVERGENCE",
            f"Trade incurred loss (-${abs(trade.pnl):.2f}) due to multi-factor decay between entry and exit.",
            "min_entry_score",
            +0.5
        )

    def run_continuous_optimization(self, db: Session, lookback: int = 20) -> Dict[str, Any]:
        """
        Periodic autonomous optimization loop:
        Analyzes recent closed trades and actively relaxes net edge and P2B window criteria
        to maximize trade execution frequency while protecting profitability.
        """
        recent_trades = db.query(BTC5MTrade).filter(
            BTC5MTrade.instance_id == self.instance_id,
            BTC5MTrade.status == "CLOSED"
        ).order_by(desc(BTC5MTrade.id)).limit(lookback).all()

        wins = sum(1 for t in recent_trades if t.pnl and t.pnl > 0)
        losses = sum(1 for t in recent_trades if t.pnl and t.pnl < 0)
        win_rate = (wins / len(recent_trades)) * 100.0 if recent_trades else 50.0

        current_settings = get_btc5m_settings(db, instance_id=self.instance_id)
        current_score = float(current_settings.get("min_entry_score", 40.0))
        current_prob = float(current_settings.get("min_entry_probability", 0.40))
        current_net_edge = float(current_settings.get("min_net_edge", -0.020))
        current_p2b_diff = float(current_settings.get("min_p2b_diff", 1.5))

        adjustments = {}
        reason_parts = []

        # 1. Reduce stringent net edge requirement to allow more executions
        if current_net_edge > -0.020:
            adjustments["min_net_edge"] = "-0.020"
            reason_parts.append("Reduced stringent net edge requirement to -2.00% (-0.020) to enable more trade executions.")

        # 2. Widen entry price window relative to Price-to-Beat
        if current_p2b_diff > 2.0:
            adjustments["min_p2b_diff"] = "1.5"
            reason_parts.append("Widened entry price window relative to Price-to-Beat to $1.50 (lowered lead threshold).")

        # 3. Dynamic Win-Rate Curve Optimization
        if len(recent_trades) >= 5:
            if win_rate < 42.0 and current_score < 48.0:
                adjustments["min_entry_score"] = f"{min(48.0, current_score + 1.0):.1f}"
                adjustments["min_entry_probability"] = f"{min(0.48, current_prob + 0.01):.2f}"
                reason_parts.append(f"Win rate curve rebalancing ({win_rate:.1f}%): calibrated entry filter floor.")
            elif win_rate >= 50.0:
                if current_score > 38.0:
                    adjustments["min_entry_score"] = f"{max(38.0, current_score - 1.0):.1f}"
                if current_prob > 0.38:
                    adjustments["min_entry_probability"] = f"{max(0.38, current_prob - 0.01):.2f}"
                if current_net_edge > -0.025:
                    adjustments["min_net_edge"] = "-0.025"
                if current_p2b_diff > 1.2:
                    adjustments["min_p2b_diff"] = "1.2"
                reason_parts.append(f"Win rate healthy ({win_rate:.1f}%): broadened opportunity window to maximize fill rate.")
        else:
            # When trade history is light, default to maximum trade execution mode
            if current_score > 40.0:
                adjustments["min_entry_score"] = "40.0"
            if current_prob > 0.40:
                adjustments["min_entry_probability"] = "0.40"
            if current_net_edge > -0.020:
                adjustments["min_net_edge"] = "-0.020"
            if current_p2b_diff > 1.5:
                adjustments["min_p2b_diff"] = "1.5"
            if adjustments:
                reason_parts.append("Baseline sweep: applied widened P2B entry window and relaxed net edge filters.")

        reason = " ".join(reason_parts)

        if adjustments:
            update_btc5m_settings(db, adjustments, user_info="CONTINUOUS_OPTIMIZER", instance_id=self.instance_id)
            
            # Log continuous optimization event
            opt_log = BTC5MSelfLearningLog(
                instance_id=self.instance_id,
                trade_id=None,
                market_id=None,
                timestamp=datetime.now(timezone.utc),
                outcome="PERIODIC_OPTIMIZATION",
                pnl=None,
                root_cause="TRADE_FREQUENCY_OPTIMIZATION",
                error_analysis=reason,
                parameter_adjusted=", ".join(adjustments.keys()),
                old_value=f"edge={current_net_edge:.3f}, p2b=${current_p2b_diff:.1f}, score={current_score:.1f}",
                new_value=f"{adjustments}",
                adaptation_delta=f"WinRate: {win_rate:.1f}%",
                status="APPLIED"
            )
            db.add(opt_log)
            db.commit()

            # Persist continuous optimization event to physical disk log file
            append_optimizer_log_entry(
                event_type="PERIODIC_OPTIMIZATION",
                instance_id=self.instance_id,
                trade_id=None,
                outcome="PERIODIC_SWEEP",
                root_cause="TRADE_FREQUENCY_OPTIMIZATION",
                error_analysis=reason,
                param_adjusted=", ".join(adjustments.keys()),
                old_value=f"edge={current_net_edge:.3f}, p2b=${current_p2b_diff:.1f}, score={current_score:.1f}",
                new_value=f"{adjustments}",
                adaptation_delta=f"WinRate: {win_rate:.1f}%",
                pnl=None
            )

        return {
            "status": "OPTIMIZED" if adjustments else "OPTIMAL",
            "analyzed_trades": len(recent_trades),
            "win_rate": round(win_rate, 1),
            "adjustments": adjustments,
            "reason": reason or "Strategy parameters are operating with widened entry windows and relaxed net edge for maximum trade executions."
        }

    def get_learning_summary(self, db: Session, limit: int = 30) -> Dict[str, Any]:
        """
        Provides structured metrics and logs for the Self-Learning Dashboard view.
        """
        logs = db.query(BTC5MSelfLearningLog).filter(
            BTC5MSelfLearningLog.instance_id == self.instance_id
        ).order_by(desc(BTC5MSelfLearningLog.id)).limit(limit).all()

        total_adaptations = db.query(BTC5MSelfLearningLog).filter(
            BTC5MSelfLearningLog.instance_id == self.instance_id
        ).count()

        # Error distribution
        error_counts = {}
        for l in logs:
            rc = l.root_cause or "UNKNOWN"
            error_counts[rc] = error_counts.get(rc, 0) + 1

        formatted_logs = []
        for l in logs:
            formatted_logs.append({
                "id": l.id,
                "trade_id": l.trade_id,
                "market_id": l.market_id,
                "timestamp": l.timestamp.isoformat() if l.timestamp else None,
                "outcome": l.outcome,
                "pnl": l.pnl,
                "root_cause": l.root_cause,
                "error_analysis": l.error_analysis,
                "parameter_adjusted": l.parameter_adjusted,
                "old_value": l.old_value,
                "new_value": l.new_value,
                "adaptation_delta": l.adaptation_delta,
                "status": l.status,
            })

        current_settings = get_btc5m_settings(db, instance_id=self.instance_id)
        log_file_size = os.path.getsize(OPTIMIZER_LOG_FILE) if os.path.exists(OPTIMIZER_LOG_FILE) else 0

        return {
            "total_adaptations": total_adaptations,
            "error_distribution": error_counts,
            "log_file_name": "self_learning_optimizer.log",
            "log_file_path": OPTIMIZER_LOG_FILE,
            "log_file_size_bytes": log_file_size,
            "current_settings": {
                "min_entry_score": current_settings.get("min_entry_score"),
                "min_entry_probability": current_settings.get("min_entry_probability"),
                "min_net_edge": current_settings.get("min_net_edge"),
                "min_p2b_diff": current_settings.get("min_p2b_diff"),
                "min_entry_price": current_settings.get("min_entry_price"),
                "max_entry_price": current_settings.get("max_entry_price"),
                "tp_dollar": current_settings.get("tp_dollar"),
                "sl_dollar": current_settings.get("sl_dollar"),
                "min_order_book_imbalance": current_settings.get("min_order_book_imbalance"),
                "dynamic_sl_delta": current_settings.get("dynamic_sl_delta"),
            },
            "recent_logs": formatted_logs
        }
