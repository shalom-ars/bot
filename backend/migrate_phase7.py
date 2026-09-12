import sqlite3

def migrate():
    conn = sqlite3.connect('../data/bot.db')
    cursor = conn.cursor()
    
    # Create LiveOrder table
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id VARCHAR UNIQUE,
            client_id VARCHAR UNIQUE,
            market_id VARCHAR,
            condition_id VARCHAR,
            token_id VARCHAR,
            side VARCHAR,
            price FLOAT,
            quantity FLOAT,
            state VARCHAR,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            error_reason VARCHAR
        )
        """)
        print("Created live_orders table")
    except Exception as e:
        print(f"Error creating live_orders: {e}")
        
    # Create CircuitBreakerEvent table
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS circuit_breaker_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            event_type VARCHAR,
            reason VARCHAR,
            resolved BOOLEAN DEFAULT 0
        )
        """)
        print("Created circuit_breaker_events table")
    except Exception as e:
        print(f"Error creating circuit_breaker_events: {e}")

    # Create AuditLog table
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            action VARCHAR,
            details VARCHAR
        )
        """)
        print("Created audit_logs table")
    except Exception as e:
        print(f"Error creating audit_logs: {e}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
