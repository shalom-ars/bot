from .base import BaseStrategy

class TrendFollowingStrategy(BaseStrategy):
    def evaluate(self, tick, features: dict, **kwargs):
        momentum_1m = features.get('short_momentum_1m', 0.0)
        distance_50 = features.get('distance_from_50', 0.0)
        
        if momentum_1m > 0.05 and distance_50 > 0.1:
            return {
                "direction": "BUY",
                "probability": (tick.ask + 0.1) if tick.ask else 0.5,
                "confidence": 0.7,
                "expected_edge": 0.05,
                "entry_condition": "Strong sustained trend and momentum",
                "exit_condition": "Trend strength weakens",
                "reason": "Trend Following setup detected",
                "strategy": "TREND_FOLLOWING"
            }
        return {
            "direction": "SKIP",
            "probability": 0.5,
            "confidence": 0.0,
            "expected_edge": 0.0,
            "entry_condition": "None",
            "exit_condition": "None",
            "reason": "Trend conditions not met",
            "strategy": "TREND_FOLLOWING"
        }
