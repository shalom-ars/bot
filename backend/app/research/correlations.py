import logging
from app.db.session import SessionLocal
from app.db.models import Market

logger = logging.getLogger(__name__)

class CorrelationEngine:
    def __init__(self):
        pass

    def evaluate(self, tick) -> dict:
        """
        Builds a related-market analysis object.
        Advisory only.
        """
        db = SessionLocal()
        related_ids = []
        try:
            # Find tokens sharing the same parent condition_id
            market = db.query(Market).filter(Market.market_id == tick.market_id).first()
            if market and market.condition_id:
                siblings = db.query(Market).filter(
                    Market.condition_id == market.condition_id,
                    Market.market_id != tick.market_id
                ).all()
                related_ids = [s.market_id for s in siblings]
        except Exception as e:
            logger.error(f"[CORRELATION] DB Error: {e}")
        finally:
            db.close()
            
        return {
            "related_market_ids": related_ids,
            "relationship_type": "mutually_exclusive_siblings" if related_ids else "none",
            "correlation_score": -1.0 if related_ids else 0.0,
            "divergence": 0.0,
            "confidence": 0.5 if related_ids else 0.0
        }
