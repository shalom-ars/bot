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

from app.db.models import BTC5MTrade, BTC5MSelfLearningLog
from app.btc5m.settings_manager import get_btc5m_settings, update_btc5m_settings

logger = logging.getLogger(__name__)

# Strict Safety Boundaries to prevent over-tightening or reckless widening
SAFETY_BOUNDS: Dict[str, Tuple[float, float]] = {
    "min_entry_score": (35.0, 65.0),
    "min_entry_probability": (0.35, 0.60),
    "min_order_book_imbalance": (0.01, 0.05),
    "min_p2b_diff": (5.0, 25.0),
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
            elif target_param in ("tp_dollar", "sl_dollar", "dynamic_sl_delta"):
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
            return (
                "P2B_CHOP",
                f"Final settlement resolved to {resolution} due to micro-price oscillation across Price-to-Beat boundary in final candle window.",
                "min_p2b_diff",
                +2.0
            )

        # Default fallback diagnosis: General prediction error
        return (
            "PREDICTION_DIVERGENCE",
            f"Trade incurred loss (-${abs(trade.pnl):.2f}) due to multi-factor decay between entry and exit.",
            "min_entry_score",
            +1.0
        )

    def run_continuous_optimization(self, db: Session) -> Dict[str, Any]:
        """
        Periodic autonomous optimization loop:
        Analyzes the distribution of recent closed trades to maintain peak profitability.
        """
        recent_trades = db.query(BTC5MTrade).filter(
            BTC5MTrade.instance_id == self.instance_id,
            BTC5MTrade.status == "CLOSED"
        ).order_by(desc(BTC5MTrade.id)).limit(20).all()

        if len(recent_trades) < 5:
            return {"status": "INSUFFICIENT_HISTORY", "analyzed_trades": len(recent_trades)}

        wins = sum(1 for t in recent_trades if t.pnl and t.pnl > 0)
        losses = sum(1 for t in recent_trades if t.pnl and t.pnl < 0)
        win_rate = (wins / len(recent_trades)) * 100.0 if recent_trades else 0.0

        current_settings = get_btc5m_settings(db, instance_id=self.instance_id)
        current_score = float(current_settings.get("min_entry_score", 40.0))
        current_prob = float(current_settings.get("min_entry_probability", 0.40))

        adjustments = {}
        reason = ""

        # If win rate is below 45%, tighten entry criteria to eliminate low-conviction signals
        if win_rate < 45.0 and current_score < 55.0:
            adjustments["min_entry_score"] = f"{min(55.0, current_score + 1.5):.1f}"
            adjustments["min_entry_probability"] = f"{min(0.55, current_prob + 0.02):.2f}"
            reason = f"Periodic Optimizer: Win rate low ({win_rate:.1f}% across 20 trades). Tightening entry filters to protect capital."
        
        # If win rate is high (>65%), gently ease criteria to capture more profitable volume
        elif win_rate > 65.0 and current_score > 38.0:
            adjustments["min_entry_score"] = f"{max(38.0, current_score - 1.0):.1f}"
            adjustments["min_entry_probability"] = f"{max(0.38, current_prob - 0.01):.2f}"
            reason = f"Periodic Optimizer: Win rate strong ({win_rate:.1f}%). Broadening entry criteria to increase trade frequency."

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
                root_cause="WIN_RATE_CURVE_BALANCING",
                error_analysis=reason,
                parameter_adjusted=", ".join(adjustments.keys()),
                old_value=f"score={current_score:.1f}, prob={current_prob:.2f}",
                new_value=f"{adjustments}",
                adaptation_delta=f"WinRate: {win_rate:.1f}%",
                status="APPLIED"
            )
            db.add(opt_log)
            db.commit()

        return {
            "status": "OPTIMIZED" if adjustments else "OPTIMAL",
            "analyzed_trades": len(recent_trades),
            "win_rate": round(win_rate, 1),
            "adjustments": adjustments,
            "reason": reason or "Strategy parameters are currently operating in the optimal profit zone."
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

        return {
            "total_adaptations": total_adaptations,
            "error_distribution": error_counts,
            "current_settings": {
                "min_entry_score": current_settings.get("min_entry_score"),
                "min_entry_probability": current_settings.get("min_entry_probability"),
                "tp_dollar": current_settings.get("tp_dollar"),
                "sl_dollar": current_settings.get("sl_dollar"),
                "min_order_book_imbalance": current_settings.get("min_order_book_imbalance"),
                "dynamic_sl_delta": current_settings.get("dynamic_sl_delta"),
            },
            "recent_logs": formatted_logs
        }
