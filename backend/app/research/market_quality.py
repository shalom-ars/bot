class MarketQualityEngine:
    """Evaluates the structural quality and safety of a Polymarket orderbook before prediction."""
    
    @staticmethod
    def evaluate(tick, features, time_remaining_sec: float) -> dict:
        score = 100
        reasons = []
        
        # 1. Spread Evaluation
        spread = tick.spread if tick.spread is not None else 1.0
        if spread >= 0.10:
            score -= 40
            reasons.append(f"Wide Spread ({spread:.4f})")
        elif spread >= 0.05:
            score -= 20
            reasons.append(f"Moderate Spread ({spread:.4f})")
            
        # 2. Depth/Liquidity Evaluation
        depth = (tick.bid_depth or 0.0) + (tick.ask_depth or 0.0)
        if depth == 0:
            score -= 80
            reasons.append("Empty Orderbook")
        elif depth < 50:
            score -= 30
            reasons.append(f"Low Depth (${depth:.2f})")
            
        # 3. Resolution Proximity
        if time_remaining_sec <= 3600:
            score -= 50
            reasons.append(f"Too close to resolution ({time_remaining_sec/60:.1f}m)")
            
        # 4. Feature Quality
        if not features:
            score -= 40
            reasons.append("Insufficient historical features")
        else:
            # Check for stale data (e.g. 0 volatility over long period)
            if features.get('rolling_volatility', 0) == 0.0 and features.get('history_length', 0) > 10:
                score -= 10
                reasons.append("Price entirely stagnant")
                
        score = max(0, min(100, score))
        
        if score >= 80:
            level = "Excellent"
        elif score >= 50:
            level = "Good"
        elif score >= 20:
            level = "Poor"
        else:
            level = "Reject"
            
        return {
            "quality_score": score,
            "quality_level": level,
            "rejection_reasons": reasons
        }
