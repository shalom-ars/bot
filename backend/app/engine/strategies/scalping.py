from .base import BaseStrategy

class ScalpingStrategy(BaseStrategy):
    def evaluate(self, tick, features: dict, **kwargs):
        order_size = kwargs.get('order_size', 50.0)
        momentum = features.get('short_momentum_1m', 0.0)
        spread = tick.spread if hasattr(tick, 'spread') else (tick.ask - tick.bid if tick.ask and tick.bid else 1.0)
        ask_depth = tick.ask_depth if tick.ask_depth else 0.0
        
        if momentum > 0.03 and spread < 0.02 and ask_depth >= order_size:
            return {
                "direction": "BUY",
                "probability": (tick.ask + 0.05) if tick.ask else 0.5, 
                "confidence": 0.8,
                "expected_edge": 0.03,
                "entry_condition": "Strong momentum with tight spread and good liquidity",
                "exit_condition": "Momentum reverses or spread widens",
                "reason": "Scalping setup detected",
                "strategy": "SCALPING"
            }
        return {
            "direction": "SKIP",
            "probability": 0.5,
            "confidence": 0.0,
            "expected_edge": 0.0,
            "entry_condition": "None",
            "exit_condition": "None",
            "reason": "Scalping conditions not met",
            "strategy": "SCALPING"
        }
