from .base import BaseStrategy

class ArbitrageStrategy(BaseStrategy):
    def evaluate(self, tick, features: dict, **kwargs):
        spread = tick.ask - tick.bid if (tick.ask is not None and tick.bid is not None) else 1.0
        if spread < 0:
            return {
                "direction": "BUY",
                "probability": 1.0,
                "confidence": 1.0,
                "expected_edge": abs(spread),
                "entry_condition": "Negative spread detected",
                "exit_condition": "Spread normalizes to >= 0",
                "reason": "Arbitrage opportunity: bid exceeds ask",
                "strategy": "ARBITRAGE"
            }
        return {
            "direction": "SKIP",
            "probability": 0.5,
            "confidence": 0.0,
            "expected_edge": 0.0,
            "entry_condition": "None",
            "exit_condition": "None",
            "reason": "No arbitrage opportunity found",
            "strategy": "ARBITRAGE"
        }
