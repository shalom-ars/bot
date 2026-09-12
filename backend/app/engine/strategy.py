from app.db.schemas import MarketTick
from app.config import settings
import numpy as np
from app.research.market_quality import MarketQualityEngine
from app.research.correlations import CorrelationEngine

class StrategyEngine:
    def __init__(self, model):
        self.model = model
        self.correlation_engine = CorrelationEngine()
        
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
            "model_version": "untrained"
        }
        base.update(kwargs)
        return base

    def evaluate(self, tick: MarketTick, current_features: dict, order_size: float = 50.0):
        """
        Phase 3 Edge Engine & Strategy Router.
        Evaluates strict safety gates, mathematical edge, execution costs, and routes to a strategy.
        """
        # 1. Market Quality Gate
        quality = MarketQualityEngine.evaluate(tick, current_features, current_features.get('time_remaining_sec', 99999))
        if quality['quality_level'] == "Reject":
            return self._skip_signal(tick, f"Rejected Quality: {'; '.join(quality['rejection_reasons'])}", market_quality_status="Reject")

        # 2. Correlation Engine (Advisory)
        related_data = self.correlation_engine.evaluate(tick)
        
        # 3. Model Prediction (Fair Probability)
        feat_vec = [
            current_features.get('spread', tick.spread),
            current_features.get('imbalance', 0.0),
            current_features.get('short_momentum_1m', 0.0),
            current_features.get('rolling_volatility', 0.0),
            current_features.get('distance_from_50', tick.price - 0.5)
        ]
        
        prob, uncertainty, model_name = self.model.predict(np.array(feat_vec).reshape(1, -1))
        
        if model_name == "untrained_baseline":
            return self._skip_signal(tick, "Model not trained (RESEARCH ONLY)", 
                                     market_quality_status=quality['quality_level'], model_version=model_name)

        if uncertainty > 0.05:
            return self._skip_signal(tick, "Uncertainty too high", uncertainty=uncertainty, 
                                     market_quality_status=quality['quality_level'], model_version=model_name)

        # 4. Market Price Handling
        # We assume the model predicts the probability of this specific token resolving YES (payout $1).
        # To buy YES, we pay best_ask. To buy NO, we sell YES at best_bid (effectively).
        # For simplicity in this YES/NO token-separated architecture, if we believe probability > price, we BUY this token at best_ask.
        # If we believe probability < price, we would SELL this token (or BUY the sibling NO token).
        # Here we only evaluate BUYING the current token if Fair Prob > Ask.
        
        best_ask = tick.ask if tick.ask is not None and tick.ask > 0 else 1.0
        best_bid = tick.bid if tick.bid is not None and tick.bid > 0 else 0.0
        
        # 5. Raw Edge
        # We only consider BUYing the token.
        entry_price = best_ask
        raw_edge = prob - entry_price
        
        # 6. Cost Engine
        fees = 0.0  # Polymarket zero fees
        spread_cost = (best_ask - best_bid) / 2.0
        
        # Slippage/Liquidity Model
        ask_depth = tick.ask_depth if tick.ask_depth else 0.0
        if ask_depth < order_size:
            return self._skip_signal(tick, "Insufficient liquidity for order size", 
                                     uncertainty=uncertainty, fair_probability=prob, entry_price=entry_price, raw_edge=raw_edge)
            
        # Slippage scales linearly as order consumes more of the top book
        liquidity_impact = (order_size / ask_depth) if ask_depth > 0 else 1.0
        slippage_cost = spread_cost * liquidity_impact
        liquidity_cost = 0.0 # Could be fixed routing costs, etc.
        
        execution_cost = fees + spread_cost + slippage_cost + liquidity_cost
        
        # 7. Net Edge
        net_edge = raw_edge - execution_cost
        
        # 8. Dynamic Threshold
        threshold = settings.min_edge
        if tick.spread > 0.05:
            threshold += 0.01  # Stricter for wide spread
        if uncertainty > 0.02:
            threshold += 0.01  # Stricter for high uncertainty
            
        # 9. Strategy Router
        strategy = "NO-TRADE"
        signal_type = "SKIP"
        reason = "No statistical edge"
        
        if net_edge >= threshold:
            strategy = "VALUE_EDGE"
            signal_type = "BUY"
            reason = "Net Edge exceeds dynamic threshold"
            
            # Momentum confirmation (Optional multi-strategy)
            if current_features.get('short_momentum_1m', 0) > 0.01:
                strategy = "VALUE_MOMENTUM"
        
        return {
            "market_id": tick.market_id,
            "signal_type": signal_type,
            "market_prob": tick.price,
            "model_prob": prob,
            "raw_edge": raw_edge,
            "effective_edge": net_edge,
            "confidence": 1.0 - uncertainty,
            "reason": reason,
            
            # Phase 3 Fields
            "strategy": strategy,
            "fair_probability": prob,
            "calibrated_probability": prob,
            "entry_price": entry_price,
            "spread_cost": spread_cost,
            "slippage_cost": slippage_cost,
            "liquidity_cost": liquidity_cost,
            "fees": fees,
            "net_edge": net_edge,
            "threshold": threshold,
            "uncertainty": uncertainty,
            "correlation_status": related_data['relationship_type'],
            "market_quality_status": quality['quality_level'],
            "model_version": model_name
        }
