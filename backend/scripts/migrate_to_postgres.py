import os
import sys
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# Adjust path to import app modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from app.db.models import Base, Market, MarketSnapshot, Signal, Trade, Position, PaperTestSession, PaperDailySnapshot, LiveOrder, CircuitBreakerEvent, AuditLog, User, Subscription, UserPortfolio, UserSetting, UserPosition, UserTrade

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def migrate_data():
    sqlite_url = os.environ.get("SQLITE_URL", "sqlite:///../data/bot.db")
    postgres_url = os.environ.get("POSTGRES_URL")
    
    if not postgres_url:
        logger.error("POSTGRES_URL environment variable is not set. Migration aborted.")
        sys.exit(1)
        
    logger.info(f"Connecting to Source (SQLite): {sqlite_url}")
    sqlite_engine = create_engine(sqlite_url)
    SqliteSession = sessionmaker(bind=sqlite_engine)
    
    logger.info(f"Connecting to Target (PostgreSQL): {postgres_url}")
    pg_engine = create_engine(postgres_url)
    PgSession = sessionmaker(bind=pg_engine)
    
    # 1. Create Target Schema
    logger.info("Creating tables in PostgreSQL...")
    Base.metadata.create_all(pg_engine)
    
    sqlite_session = SqliteSession()
    pg_session = PgSession()
    
    # Tables to migrate in order of dependencies
    models_to_migrate = [
        Market,
        PaperTestSession,
        PaperDailySnapshot,
        User,
        Subscription,
        UserPortfolio,
        UserSetting,
        MarketSnapshot,
        Signal,
        Trade,
        Position,
        UserPosition,
        UserTrade,
        LiveOrder,
        CircuitBreakerEvent,
        AuditLog
    ]
    
    total_migrated = 0
    
    try:
        for model in models_to_migrate:
            logger.info(f"Migrating table: {model.__tablename__}...")
            
            # Use chunks to avoid memory exhaustion
            chunk_size = 10000
            offset = 0
            
            # Count records
            total_records = sqlite_session.query(model).count()
            logger.info(f"Found {total_records} records in {model.__tablename__}.")
            
            while True:
                records = sqlite_session.query(model).offset(offset).limit(chunk_size).all()
                if not records:
                    break
                
                # Make transient (detach from sqlite)
                for record in records:
                    sqlite_session.expunge(record)
                    from sqlalchemy.orm import make_transient
                    make_transient(record)
                    # We need to drop the id if we want it to map perfectly, 
                    # but actually we WANT to keep the IDs exactly the same to preserve foreign keys!
                
                pg_session.bulk_save_objects(records)
                pg_session.commit()
                
                offset += len(records)
                total_migrated += len(records)
                logger.info(f"  ...migrated {offset}/{total_records} records.")
                
        logger.info(f"Migration completed successfully. Total records migrated: {total_migrated}")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        pg_session.rollback()
        sys.exit(1)
    finally:
        sqlite_session.close()
        pg_session.close()

if __name__ == "__main__":
    migrate_data()
