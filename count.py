import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.db.session import SessionLocal
from app.db.models import MarketTick, Signal, Position, Trade, User, UserPortfolio, UserTrade

try:
    db = SessionLocal()
    print(f"Snapshots: {db.query(MarketTick).count()}")
    print(f"Signals: {db.query(Signal).count()}")
    print(f"Positions: {db.query(Position).count()}")
    print(f"Trades: {db.query(Trade).count()}")
    print(f"Users: {db.query(User).count()}")
    print(f"User Portfolios: {db.query(UserPortfolio).count()}")
    print(f"User Trades: {db.query(UserTrade).count()}")
except Exception as e:
    print(f"Error: {e}")
