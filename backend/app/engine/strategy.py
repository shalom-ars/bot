from app.db.schemas import MarketTick
from app.config import settings
import numpy as np
from app.research.market_quality import MarketQualityEngine
from app.research.correlations import CorrelationEngine

from .strategies.arbitrage import ArbitrageStrategy
from .strategies.scalping import ScalpingStrategy
from .strategies.trend import TrendFollowingStrategy

class StrategyEngine:
    def __init__(self, model):
        self.model = model
        self.correlation_engine = CorrelationEngine()
        self.strategies = [
            ArbitrageStrategy(),
            ScalpingStrategy(),
            TrendFollowingStrategy()
        ]
        
    def _skip_signal(self, tick, reason, strategy="NO-TRADE", **kwargs):
        base = {
            "market_id": tick.market_id,
            "signal_type": "SKIP",
            "market_prob": tick.price,
            "model_prob": 0.5,
            "raw_edge": 0.0,
            "effective_edge": 0.0,
            "confidence": 0.0,
            "reason": reason,
            "strategy": strategy,
            "fair_probability": 0.5,
            "calibrated_probability": 0.5,
            "entry_price": tick.price,
            "spread_cost": 0.0,
            "slippage_cost": 0.0,
            "liquidity_cost": 0.0,
            "fees": 0.0,
            "net_edge": 0.0,
            "threshold": settings.min_edge,
            "uncertainty": 1.0,
            "correlation_status": "none",
            "market_quality_status": "SKIP",
            "model_version": "untrained",
            "entry_condition": "None",
            "exit_condition": "None",
            "direction": "SKIP"
        }
        base.update(kwargs)
        return base

    def evaluate(self, tick: MarketTick, current_features: dict, order_size: float = 50.0):
        quality = MarketQualityEngine.evaluate(tick, current_features, current_features.get('time_remaining_sec', 99999))
        if quality['quality_level'] == "Reject":
            return self._skip_signal(tick, f"Rejected Quality: {'; '.join(quality['rejection_reasons'])}", market_quality_status="Reject")

        related_data = self.correlation_engine.evaluate(tick)
        
        feat_vec = [
            current_features.get('spread', tick.spread),
            current_features.get('imbalance', 0.0),
            current_features.get('short_momentum_1m', 0.0),
            current_features.get('rolling_volatility', 0.0),
            current_features.get('distance_from_50', tick.price - 0.5)
        ]
        prob, uncertainty, model_name = self.model.predict(np.array(feat_vec).reshape(1, -1))
        
        best_ask = tick.ask if tick.ask is not None and tick.ask > 0 else 1.0
        best_bid = tick.bid if tick.bid is not None and tick.bid > 0 else 0.0
        
        fees = 0.0
        spread_cost = (best_ask - best_bid) / 2.0
        ask_depth = tick.ask_depth if tick.ask_depth else 0.0
        
        entry_price = best_ask
        raw_edge = prob - entry_price
        
        if ask_depth < order_size:
            return self._skip_signal(tick, "Insufficient liquidity for order size", 
                                     uncertainty=uncertainty, fair_probability=prob, entry_price=entry_price, raw_edge=raw_edge)
            
        liquidity_impact = (order_size / ask_depth) if ask_depth > 0 else 1.0
        slippage_cost = spread_cost * liquidity_impact
        liquidity_cost = 0.0
        execution_cost = fees + spread_cost + slippage_cost + liquidity_cost
        
        net_edge = raw_edge - execution_cost

        best_eval = None
        for strat in self.strategies:
            res = strat.evaluate(tick, current_features, order_size=order_size)
            if res["direction"] != "SKIP":
                if not best_eval or res["expected_edge"] > best_eval["expected_edge"]:
                    best_eval = res
        
        if model_name == "untrained_baseline" and not best_eval:
            momentum = current_features.get('short_momentum_1m', 0.0)
            if momentum > 0.05 and tick.spread < 0.03 and ask_depth >= order_size:
                prob = tick.ask + 0.05
                model_name = "rule_based_momentum"
                uncertainty = 0.0
            else:
                return self._skip_signal(tick, "Model not trained and no strategy edge", 
                                         market_quality_status=quality['quality_level'], model_version=model_name)

        if not best_eval and uncertainty > 0.05:
            return self._skip_signal(tick, "Uncertainty too high", uncertainty=uncertainty, 
                                     market_quality_status=quality['quality_level'], model_version=model_name)

        threshold = settings.min_edge
        if tick.spread > 0.05:
            threshold += 0.01
        if uncertainty > 0.02:
            threshold += 0.01

        strategy = "NO-TRADE"
        signal_type = "SKIP"
        reason = "No statistical edge"
        entry_cond = "None"
        exit_cond = "None"
        final_prob = prob
        final_edge = net_edge
        final_conf = 1.0 - uncertainty

        if best_eval:
            strategy = best_eval["strategy"]
            signal_type = best_eval["direction"]
            reason = best_eval["reason"]
            entry_cond = best_eval["entry_condition"]
            exit_cond = best_eval["exit_condition"]
            final_prob = best_eval["probability"]
            final_edge = best_eval["expected_edge"]
            final_conf = best_eval["confidence"]
        elif net_edge >= threshold:
            strategy = "VALUE_EDGE"
            signal_type = "BUY"
            reason = "Net Edge exceeds dynamic threshold"
            entry_cond = "Net Edge > Threshold"
            exit_cond = "Edge decay"
            if current_features.get('short_momentum_1m', 0) > 0.01:
                strategy = "VALUE_MOMENTUM"
        
        return {
            "market_id": tick.market_id,
            "signal_type": signal_type,
            "market_prob": tick.price,
            "model_prob": final_prob,
            "raw_edge": raw_edge if not best_eval else final_edge,
            "effective_edge": final_edge,
            "confidence": final_conf,
            "reason": reason,
            "strategy": strategy,
            "fair_probability": final_prob,
            "calibrated_probability": final_prob,
            "entry_price": entry_price,
            "spread_cost": spread_cost,
            "slippage_cost": slippage_cost,
            "liquidity_cost": liquidity_cost,
            "fees": fees,
            "net_edge": final_edge,
            "threshold": threshold,
            "uncertainty": uncertainty,
            "correlation_status": related_data['relationship_type'],
            "market_quality_status": quality['quality_level'],
            "model_version": model_name,
            "entry_condition": entry_cond,
            "exit_condition": exit_cond,
            "direction": signal_type
        }
