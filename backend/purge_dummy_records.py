import os
import sys

# Ensure backend path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.db.session import engine, ensure_fast5m_schema
from sqlalchemy import text

# Ensure schema
ensure_fast5m_schema(engine)

with engine.begin() as conn:
    # 1. Identify Super Admin shalombinrasheed@gmail.com
    admin_row = conn.execute(text("SELECT id, email, role, status, allowed_mode FROM users WHERE LOWER(email) = 'shalombinrasheed@gmail.com'")).fetchone()
    if not admin_row:
        conn.execute(text("INSERT INTO users (email, role, status, allowed_mode, auth_provider, is_active) VALUES ('shalombinrasheed@gmail.com', 'SUPER_ADMIN', 'APPROVED', 'REAL_AND_DEMO', 'google', 1)"))
        admin_row = conn.execute(text("SELECT id, email, role, status, allowed_mode FROM users WHERE LOWER(email) = 'shalombinrasheed@gmail.com'")).fetchone()
    
    admin_id = admin_row[0]
    print(f"==================================================")
    print(f"RETAINING SUPER ADMIN: ID={admin_id} ({admin_row[1]}) Role={admin_row[2]} Status={admin_row[3]}")
    print(f"==================================================")

    # 2. Get list of non-admin users to purge
    dummy_users = conn.execute(text(f"SELECT id, email FROM users WHERE id != {admin_id}")).fetchall()
    print(f"\nFound {len(dummy_users)} dummy/seed users to purge:")
    dummy_user_ids = [u[0] for u in dummy_users]
    for u in dummy_users:
        print(f" - ID {u[0]}: {u[1]}")

    if dummy_user_ids:
        ids_str = ",".join(str(i) for i in dummy_user_ids)

        # 3. Purge related user records
        conn.execute(text(f"DELETE FROM subscriptions WHERE user_id IN ({ids_str})"))
        conn.execute(text(f"DELETE FROM user_portfolios WHERE user_id IN ({ids_str})"))
        conn.execute(text(f"DELETE FROM user_positions WHERE user_id IN ({ids_str})"))
        conn.execute(text(f"DELETE FROM user_settings WHERE user_id IN ({ids_str})"))
        conn.execute(text(f"DELETE FROM user_trades WHERE user_id IN ({ids_str})"))
        conn.execute(text(f"DELETE FROM fast5m_user_vaults WHERE user_id IN ({ids_str})"))
        conn.execute(text(f"DELETE FROM fast5m_user_settings WHERE user_id IN ({ids_str})"))
        
        # Purge fast5m trades linked to dummy users or without user_id
        res_fast5m = conn.execute(text(f"DELETE FROM fast5m_trades WHERE user_id IN ({ids_str}) OR user_id IS NULL"))
        print(f"Deleted {res_fast5m.rowcount} fast5m_trades rows for dummy users.")

        # Purge dummy users themselves
        res_users = conn.execute(text(f"DELETE FROM users WHERE id IN ({ids_str})"))
        print(f"Deleted {res_users.rowcount} dummy users from 'users' table.")

    # 4. Purge legacy mock trades from `trades` table
    res_trades = conn.execute(text("DELETE FROM trades"))
    print(f"Purged {res_trades.rowcount} legacy/mock trades from 'trades' table.")

    # 5. Purge mock fast5m_trades from trades table (all demo/fake historical trades)
    res_all_demo_fast5m = conn.execute(text("DELETE FROM fast5m_trades WHERE account_mode = 'demo' OR user_id IS NULL"))
    print(f"Purged {res_all_demo_fast5m.rowcount} historical mock/demo trades from 'fast5m_trades' table.")

    # 6. Ensure Super Admin has dedicated clean vault & SaaS records
    vault = conn.execute(text(f"SELECT id FROM fast5m_user_vaults WHERE user_id = {admin_id}")).fetchone()
    if not vault:
        conn.execute(text(f"""
            INSERT INTO fast5m_user_vaults (user_id, account_mode, allocated_balance, initial_deposit, total_deposited, total_withdrawn)
            VALUES ({admin_id}, 'demo', 300.0, 300.0, 300.0, 0.0)
        """))
        print("Created clean default vault ($300.00) for Super Admin.")
    else:
        conn.execute(text(f"UPDATE fast5m_user_vaults SET allocated_balance = 300.0, initial_deposit = 300.0 WHERE user_id = {admin_id}"))

    # 7. Clean audit logs relating to dummy accounts
    conn.execute(text("DELETE FROM audit_logs WHERE details LIKE '%test%' OR details LIKE '%perf_%' OR details LIKE '%example.com%' OR details LIKE '%e2e_%' OR details LIKE '%attacker%'"))

    # Verify remaining users
    final_users = conn.execute(text("SELECT id, email, role, status, allowed_mode FROM users")).fetchall()
    print(f"\n==================================================")
    print(f"VERIFICATION: Final Users in Database: {len(final_users)}")
    print(f"==================================================")
    for u in final_users:
        print(f"ID={u[0]} | Email={u[1]} | Role={u[2]} | Status={u[3]} | AllowedMode={u[4]}")

    assert len(final_users) == 1, f"Expected exactly 1 user, found {len(final_users)}"
    assert final_users[0][1].lower() == "shalombinrasheed@gmail.com"
    assert final_users[0][2] == "SUPER_ADMIN"
    assert final_users[0][3] == "APPROVED"
    assert final_users[0][4] == "REAL_AND_DEMO"

print("\nSUCCESS: All mock and dummy records purged. Clean slate verified!")
