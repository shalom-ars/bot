import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_db
from app.api.security import get_password_hash, verify_password, create_access_token

client = TestClient(app)

def override_get_db():
    mock_db = MagicMock()
    
    # Mock user creation
    mock_db.query().filter().first.return_value = None
    
    yield mock_db

app.dependency_overrides[get_db] = override_get_db

def test_password_hashing():
    pwd = "securepassword123"
    hashed = get_password_hash(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrongpassword", hashed) is False

def test_register_creates_isolated_resources():
    response = client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "password123"
    })
    
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_login_success():
    # Setup mock user
    def override_login_db():
        db = MagicMock()
        mock_user = MagicMock(id=1, email="test@example.com", hashed_password=get_password_hash("password123"))
        db.query().filter().first.return_value = mock_user
        yield db
    app.dependency_overrides[get_db] = override_login_db
    
    response = client.post("/api/auth/login", data={
        "username": "test@example.com",
        "password": "password123"
    })
    
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_get_me_unauthorized():
    response = client.get("/api/users/me")
    assert response.status_code == 401

def test_data_isolation_user_trades():
    def override_trades_db():
        db = MagicMock()
        db.query().filter().offset().limit().all.return_value = [{"id": 100, "market_id": "m1"}]
        db.query().filter().count.return_value = 1
        
        mock_user = MagicMock(id=1, is_active=True, role="USER")
        db.query().filter().first.return_value = mock_user
        yield db
    
    app.dependency_overrides[get_db] = override_trades_db
    token = create_access_token(data={"sub": "1"})
    
    response = client.get("/api/users/trades", headers={"Authorization": f"Bearer {token}"})
    
    assert response.status_code == 200
    assert response.json()["total"] == 1

def test_rbac_admin_dashboard_forbidden_for_user():
    def override_rbac_user_db():
        db = MagicMock()
        mock_user = MagicMock(id=1, is_active=True, role="USER")
        db.query().filter().first.return_value = mock_user
        yield db
        
    app.dependency_overrides[get_db] = override_rbac_user_db
    token = create_access_token(data={"sub": "1"})
    
    response = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
    
    assert response.status_code == 403
    assert "Forbidden: Admin Panel access is strictly restricted" in response.json()["detail"]

def test_rbac_admin_dashboard_allowed_for_admin():
    def override_rbac_admin_db():
        db = MagicMock()
        mock_admin = MagicMock(id=2, email="shalombinrasheed@gmail.com", is_active=True, role="SUPER_ADMIN", status="APPROVED")
        db.query().filter().first.return_value = mock_admin
        db.query().count.return_value = 10
        yield db
        
    app.dependency_overrides[get_db] = override_rbac_admin_db
    token = create_access_token(data={"sub": "2"})
    
    response = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
    
    assert response.status_code == 200
    assert "metrics" in response.json()
