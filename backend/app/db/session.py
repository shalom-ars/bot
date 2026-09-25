from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///../data/bot.db")

if DATABASE_URL.startswith("sqlite:///"):
    db_path = DATABASE_URL.replace("sqlite:///", "")
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    connect_args["timeout"] = 15.0

from sqlalchemy import event

engine = create_engine(DATABASE_URL, connect_args=connect_args)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_btc5m_schema(db_engine):
    """
    Ensures that btc5m_trades has all required immutable thesis columns,
    ensures btc5m_settings table exists and is seeded with targeting defaults,
    and backfills any legacy rows in SQLite.
    """
    from sqlalchemy import text, inspect
    from app.db.models import BTC5MSetting
    from app.btc5m.settings_manager import ensure_btc5m_settings

    # Ensure btc5m_settings table exists
    BTC5MSetting.__table__.create(db_engine, checkfirst=True)
    
    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        ensure_btc5m_settings(db)

    inspector = inspect(db_engine)
    if "btc5m_trades" not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns("btc5m_trades")}
    
    new_cols = [
        ("locked_predicted_side", "VARCHAR"),
        ("locked_direction", "VARCHAR"),
        ("locked_outcome", "VARCHAR"),
        ("locked_token_id", "VARCHAR"),
        ("execution_side", "VARCHAR DEFAULT 'BUY'"),
        ("entry_yes_score", "FLOAT"),
        ("entry_no_score", "FLOAT"),
        ("entry_fair_probability", "FLOAT"),
        ("entry_market_probability", "FLOAT"),
        ("entry_net_edge", "FLOAT"),
        ("entry_planned_rr", "FLOAT"),
        ("entry_stop_price", "FLOAT"),
        ("entry_target_price", "FLOAT"),
        ("prediction_locked_at", "DATETIME"),
        ("prediction_lock_version", "VARCHAR DEFAULT '1.0'"),
        ("instance_id", "VARCHAR DEFAULT 'instance_1'"),
        ("exit_decision_state", "VARCHAR DEFAULT 'HOLD'"),
        ("soft_stop_touched_at", "DATETIME"),
        ("exit_review_started_at", "DATETIME"),
        ("last_exit_review_reason", "VARCHAR"),
        ("thesis_failure_score", "FLOAT"),
        ("hard_stop_price", "FLOAT")
    ]

    from app.db.models import BTC5MExitAudit
    BTC5MExitAudit.__table__.create(db_engine, checkfirst=True)

    with db_engine.connect() as conn:
        for col_name, col_type in new_cols:
            if col_name not in existing_columns:
                try:
                    conn.execute(text(f"ALTER TABLE btc5m_trades ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                except Exception:
                    pass

        # Check btc5m_signals columns
        if "btc5m_signals" in inspector.get_table_names():
            signal_cols = {col["name"] for col in inspector.get_columns("btc5m_signals")}
            if "instance_id" not in signal_cols:
                try:
                    conn.execute(text("ALTER TABLE btc5m_signals ADD COLUMN instance_id VARCHAR DEFAULT 'instance_1'"))
                    conn.commit()
                except Exception:
                    pass

        # Backfill legacy trades where locked fields are NULL
        try:
            conn.execute(text("""
                UPDATE btc5m_trades
                SET 
                    locked_predicted_side = CASE WHEN side = 'BUY' THEN 'YES' ELSE 'NO' END,
                    locked_direction = CASE WHEN side = 'BUY' THEN 'YES' ELSE 'NO' END,
                    locked_outcome = CASE WHEN side = 'BUY' THEN 'UP' ELSE 'DOWN' END,
                    locked_token_id = CASE WHEN side = 'BUY' THEN yes_token_id ELSE no_token_id END,
                    execution_side = 'BUY',
                    entry_yes_score = yes_score,
                    entry_no_score = no_score,
                    entry_net_edge = net_edge,
                    entry_planned_rr = planned_rr,
                    entry_stop_price = stop_loss_price,
                    entry_target_price = take_profit_price,
                    prediction_locked_at = entry_time,
                    prediction_lock_version = '1.0'
                WHERE locked_predicted_side IS NULL
            """))
            conn.commit()
        except Exception:
            pass


def ensure_fast5m_schema(db_engine):
    """
    Ensures that fast5m_trades, fast5m_settings, fast5m_user_vaults, and fast5m_user_settings tables exist
    and have all scoring breakdown, user isolation, and multi-wallet columns.
    """
    from sqlalchemy import text, inspect
    from app.db.models import Fast5MTrade, Fast5MSetting, Fast5MUserVault, Fast5MUserSetting, User

    Fast5MTrade.__table__.create(db_engine, checkfirst=True)
    Fast5MSetting.__table__.create(db_engine, checkfirst=True)
    Fast5MUserVault.__table__.create(db_engine, checkfirst=True)
    Fast5MUserSetting.__table__.create(db_engine, checkfirst=True)

    inspector = inspect(db_engine)

    # 1. Migrate users table columns if present
    if "users" in inspector.get_table_names():
        user_cols = {col["name"] for col in inspector.get_columns("users")}
        with db_engine.connect() as conn:
            if "wallet_address" not in user_cols:
                try:
                    conn.execute(text("ALTER TABLE users ADD COLUMN wallet_address VARCHAR(66)"))
                    conn.commit()
                except Exception:
                    pass
            if "auth_provider" not in user_cols:
                try:
                    conn.execute(text("ALTER TABLE users ADD COLUMN auth_provider VARCHAR(32) DEFAULT 'email'"))
                    conn.commit()
                except Exception:
                    pass
            if "google_sub" not in user_cols:
                try:
                    conn.execute(text("ALTER TABLE users ADD COLUMN google_sub VARCHAR(128)"))
                    conn.commit()
                except Exception:
                    pass
            if "status" not in user_cols:
                try:
                    conn.execute(text("ALTER TABLE users ADD COLUMN status VARCHAR(32) DEFAULT 'PENDING'"))
                    conn.commit()
                except Exception:
                    pass
            if "allowed_mode" not in user_cols:
                try:
                    conn.execute(text("ALTER TABLE users ADD COLUMN allowed_mode VARCHAR(32) DEFAULT 'DEMO_ONLY'"))
                    conn.commit()
                except Exception:
                    pass

            # Seed / ensure super admin privileges strictly for primary admin account: shalombinrasheed@gmail.com
            try:
                conn.execute(text("""
                    INSERT OR IGNORE INTO users (email, role, status, allowed_mode, auth_provider, is_active)
                    VALUES ('shalombinrasheed@gmail.com', 'SUPER_ADMIN', 'APPROVED', 'REAL_AND_DEMO', 'google', 1)
                """))
                conn.execute(text("""
                    UPDATE users 
                    SET role = 'SUPER_ADMIN', status = 'APPROVED', allowed_mode = 'REAL_AND_DEMO'
                    WHERE LOWER(email) = 'shalombinrasheed@gmail.com'
                """))
                # Demote any other accounts that had SUPER_ADMIN to USER
                conn.execute(text("""
                    UPDATE users
                    SET role = 'USER'
                    WHERE LOWER(email) != 'shalombinrasheed@gmail.com' AND role = 'SUPER_ADMIN'
                """))
                # Default null status to PENDING for regular accounts
                conn.execute(text("""
                    UPDATE users
                    SET status = 'PENDING'
                    WHERE status IS NULL AND LOWER(email) != 'shalombinrasheed@gmail.com'
                """))
                conn.execute(text("""
                    UPDATE users
                    SET allowed_mode = CASE 
                        WHEN LOWER(email) = 'shalombinrasheed@gmail.com' THEN 'REAL_AND_DEMO'
                        ELSE 'DEMO_ONLY'
                    END
                    WHERE allowed_mode IS NULL
                """))
                conn.commit()
            except Exception:
                pass

    # 2. Migrate fast5m_trades columns
    if "fast5m_trades" in inspector.get_table_names():
        existing_cols = {col["name"] for col in inspector.get_columns("fast5m_trades")}
        fast_cols = [
            ("user_id", "INTEGER"),
            ("delta_score", "FLOAT DEFAULT 0.0"),
            ("obi_score", "FLOAT DEFAULT 0.0"),
            ("momentum_score", "FLOAT DEFAULT 0.0"),
            ("prediction_rationale", "VARCHAR DEFAULT ''"),
            ("account_mode", "VARCHAR(16) DEFAULT 'demo'"),
            ("execution_type", "VARCHAR(32) DEFAULT 'SIMULATED_ORDERBOOK'"),
            ("tx_hash", "VARCHAR(66)"),
            ("exit_slippage", "FLOAT DEFAULT 0.0"),
            ("buffer_status", "VARCHAR(32) DEFAULT 'CLEARED'"),
            ("real_orderbook_bid", "FLOAT")
        ]
        with db_engine.connect() as conn:
            for col_name, col_type in fast_cols:
                if col_name not in existing_cols:
                    try:
                        conn.execute(text(f"ALTER TABLE fast5m_trades ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                    except Exception:
                        pass
            try:
                conn.execute(text("UPDATE fast5m_trades SET account_mode = 'demo' WHERE account_mode IS NULL"))
                conn.commit()
            except Exception:
                pass


