from app.config import settings

class EdgeEngine:
    def __init__(self):
        self.min_edge = settings.min_edge
        self.min_confidence = settings.min_confidence
        self.max_spread = settings.max_spread

    def evaluate(self, model_prob: float, market_price: float, spread: float, confidence: float):
        raw_edge = model_prob - market_price
        
        # Adjust for spread/fees
        net_edge = raw_edge - (spread / 2) # simplified slippage/spread model
        
        signal = "SKIP"
        if net_edge > self.min_edge and confidence > self.min_confidence and spread < self.max_spread:
            signal = "BUY_YES"
        elif net_edge < -self.min_edge and confidence > self.min_confidence and spread < self.max_spread:
            signal = "BUY_NO"
            
        return {
            "raw_edge": raw_edge,
            "net_edge": net_edge,
            "signal": signal,
            "confidence": confidence
        }
