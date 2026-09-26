import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal, engine, ensure_fast5m_schema
from app.db.models import User, Fast5MTrade, Fast5MUserVault
from app.api.security import create_access_token, get_password_hash
from app.fast5m.executor import fast_executor

ensure_fast5m_schema(engine)

@pytest.fixture
def client():
    return TestClient(app)

def test_multitenant_demo_reset_isolation(client):
    db = SessionLocal()
    try:
        # Create User A (PENDING status - standard registered user)
        user_a = db.query(User).filter(User.email == "usera_demo@example.com").first()
        if not user_a:
            user_a = User(
                email="usera_demo@example.com",
                hashed_password=get_password_hash("password123"),
                role="USER",
                status="PENDING",
                allowed_mode="DEMO_ONLY",
                is_active=True
            )
            db.add(user_a)
            db.commit()
            db.refresh(user_a)

        # Create User B (APPROVED user)
        user_b = db.query(User).filter(User.email == "userb_demo@example.com").first()
        if not user_b:
            user_b = User(
                email="userb_demo@example.com",
                hashed_password=get_password_hash("password123"),
                role="USER",
                status="APPROVED",
                allowed_mode="DEMO_ONLY",
                is_active=True
            )
            db.add(user_b)
            db.commit()
            db.refresh(user_b)

        # Ensure vaults for both
        vault_a = db.query(Fast5MUserVault).filter(Fast5MUserVault.user_id == user_a.id).first()
        if not vault_a:
            vault_a = Fast5MUserVault(user_id=user_a.id, allocated_balance=150.0, account_mode="demo")
            db.add(vault_a)
        else:
            vault_a.allocated_balance = 150.0

        vault_b = db.query(Fast5MUserVault).filter(Fast5MUserVault.user_id == user_b.id).first()
        if not vault_b:
            vault_b = Fast5MUserVault(user_id=user_b.id, allocated_balance=450.0, account_mode="demo")
            db.add(vault_b)
        else:
            vault_b.allocated_balance = 450.0

        # Seed trades for User A
        trade_a = Fast5MTrade(
            user_id=user_a.id,
            asset="BTC",
            market_id="mkt_a",
            condition_id="mkt_a",
            question="BTC Up?",
            epoch_bucket=101,
            outcome="UP",
            token_id="tok_a",
            entry_price=0.50,
            shares=20.0,
            cost=10.0,
            strike_price=90000.0,
            entry_oracle_price=90000.0,
            delta_at_entry=0.0,
            confidence_score=85.0,
            status="CLOSED",
            account_mode="demo",
            pnl=-5.0
        )
        db.add(trade_a)

        # Seed trades for User B
        trade_b = Fast5MTrade(
            user_id=user_b.id,
            asset="ETH",
            market_id="mkt_b",
            condition_id="mkt_b",
            question="ETH Up?",
            epoch_bucket=102,
            outcome="DOWN",
            token_id="tok_b",
            entry_price=0.45,
            shares=22.2,
            cost=10.0,
            strike_price=3000.0,
            entry_oracle_price=3000.0,
            delta_at_entry=0.0,
            confidence_score=88.0,
            status="CLOSED",
            account_mode="demo",
            pnl=12.0
        )
        db.add(trade_b)
        db.commit()

        # Seed traded epochs in memory
        fast_executor._traded_epochs.add((user_a.id, "BTC", 101, 0))
        fast_executor._traded_epochs.add((user_b.id, "ETH", 102, 0))

        # Generate tokens
        token_a = create_access_token({"sub": str(user_a.id)})
        token_b = create_access_token({"sub": str(user_b.id)})

        # 1. Test unauthenticated request returns 401
        res_no_auth = client.post("/api/fast5m/demo/reset")
        assert res_no_auth.status_code == 401

        # 2. Test User A resets demo via /api/fast5m/demo/reset
        res_a = client.post("/api/fast5m/demo/reset", headers={"Authorization": f"Bearer {token_a}"})
        assert res_a.status_code == 200
        data_a = res_a.json()
        assert data_a["status"] == "success"
        assert data_a["balance"] == 300.0

        # Verify DB state: User A trades wiped, User B trades PRESERVED
        db_trades_a = db.query(Fast5MTrade).filter(Fast5MTrade.user_id == user_a.id, Fast5MTrade.account_mode == "demo").all()
        db_trades_b = db.query(Fast5MTrade).filter(Fast5MTrade.user_id == user_b.id, Fast5MTrade.account_mode == "demo").all()
        assert len(db_trades_a) == 0
        assert len(db_trades_b) >= 1
        assert any(t.market_id == "mkt_b" for t in db_trades_b)

        # Verify Vault balances: User A reset to 300.0, User B remains 450.0
        db.refresh(vault_a)
        db.refresh(vault_b)
        assert vault_a.allocated_balance == 300.0
        assert vault_b.allocated_balance == 450.0

        # Verify Memory Epochs: User A epoch removed, User B epoch preserved
        assert (user_a.id, "BTC", 101, 0) not in fast_executor._traded_epochs
        assert (user_b.id, "ETH", 102, 0) in fast_executor._traded_epochs

        # 3. Test alias endpoint /api/demo/reset works identically for User B
        res_b = client.post("/api/demo/reset", headers={"Authorization": f"Bearer {token_b}"})
        assert res_b.status_code == 200
        db.refresh(vault_b)
        assert vault_b.allocated_balance == 300.0
        db_trades_b_after = db.query(Fast5MTrade).filter(Fast5MTrade.user_id == user_b.id, Fast5MTrade.account_mode == "demo").all()
        assert len(db_trades_b_after) == 0

    finally:
        db.query(Fast5MTrade).filter(Fast5MTrade.market_id.in_(["mkt_a", "mkt_b"])).delete(synchronize_session=False)
        db.commit()
        db.close()
