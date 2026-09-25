import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_db, SessionLocal
from app.db.models import User, Fast5MUserVault, Fast5MTrade, UserPortfolio, Subscription
from app.api.security import create_access_token

client = TestClient(app)

def test_admin_delete_user_cascade_and_protections():
    app.dependency_overrides.clear()
    db = SessionLocal()
    try:
        # Create an admin user
        admin = db.query(User).filter(User.email == "shalombinrasheed@gmail.com").first()
        if not admin:
            admin = User(
                email="shalombinrasheed@gmail.com",
                role="SUPER_ADMIN",
                status="APPROVED",
                allowed_mode="REAL_AND_DEMO"
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)

        # Create a second dummy admin
        second_admin = db.query(User).filter(User.email == "sub_admin@example.com").first()
        if not second_admin:
            second_admin = User(
                email="sub_admin@example.com",
                role="SUPER_ADMIN",
                status="APPROVED",
                allowed_mode="REAL_AND_DEMO"
            )
            db.add(second_admin)
            db.commit()
            db.refresh(second_admin)

        # Create a test target user
        target_user = db.query(User).filter(User.email == "target_delete_me@example.com").first()
        if not target_user:
            target_user = User(
                email="target_delete_me@example.com",
                role="USER",
                status="APPROVED",
                allowed_mode="DEMO_ONLY",
                is_active=True
            )
            db.add(target_user)
            db.commit()
            db.refresh(target_user)

        # Add associated records for target user (vault, trade, portfolio, subscription)
        vault = db.query(Fast5MUserVault).filter(Fast5MUserVault.user_id == target_user.id).first()
        if not vault:
            vault = Fast5MUserVault(user_id=target_user.id, allocated_balance=300.0)
            db.add(vault)

        trade = Fast5MTrade(
            user_id=target_user.id,
            asset="BTC",
            market_id="test_market",
            question="Will BTC go UP?",
            epoch_bucket=12345,
            outcome="UP",
            token_id="token_yes",
            entry_price=0.50,
            shares=10.0,
            cost=5.0,
            strike_price=90000.0,
            entry_oracle_price=90000.0,
            delta_at_entry=0.0,
            confidence_score=75.0
        )
        db.add(trade)

        portfolio = db.query(UserPortfolio).filter(UserPortfolio.user_id == target_user.id).first()
        if not portfolio:
            portfolio = UserPortfolio(user_id=target_user.id)
            db.add(portfolio)

        sub = db.query(Subscription).filter(Subscription.user_id == target_user.id).first()
        if not sub:
            sub = Subscription(user_id=target_user.id, plan="PRO")
            db.add(sub)

        db.commit()

        target_user_id = target_user.id
        admin_token = create_access_token(data={"sub": str(admin.id)})
        user_token = create_access_token(data={"sub": str(target_user_id)})

        # 1. Non-admin cannot delete
        res_forbidden = client.delete(
            f"/api/admin/users/{target_user_id}",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert res_forbidden.status_code in (401, 403)

        # 2. Admin cannot delete themselves
        res_self = client.delete(
            f"/api/admin/users/{admin.id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert res_self.status_code == 400
        assert "cannot delete their own account" in res_self.json()["detail"].lower()

        # 3. Cannot delete non-existent user
        res_404 = client.delete(
            "/api/admin/users/99999999",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert res_404.status_code == 404

        # 4. Successful cascade deletion of target user
        res_success = client.delete(
            f"/api/admin/users/{target_user_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert res_success.status_code == 200
        assert res_success.json()["success"] is True
        assert res_success.json()["deleted_user_id"] == target_user_id

        # Verify database cascade
        assert db.query(User).filter(User.id == target_user_id).first() is None
        assert db.query(Fast5MUserVault).filter(Fast5MUserVault.user_id == target_user_id).first() is None
        assert db.query(Fast5MTrade).filter(Fast5MTrade.user_id == target_user_id).first() is None
        assert db.query(UserPortfolio).filter(UserPortfolio.user_id == target_user_id).first() is None
        assert db.query(Subscription).filter(Subscription.user_id == target_user_id).first() is None

        # Clean up second admin
        db.delete(second_admin)
        db.commit()

    finally:
        db.close()
