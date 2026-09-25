import pytest
from fastapi.testclient import TestClient
from urllib.parse import urlparse, parse_qs
from app.main import app

client = TestClient(app)

def test_google_oauth_url_formatting():
    """Verify authorization URL formatting strictly matches specifications."""
    # Test with default redirect_uri
    response = client.get("/api/auth/google/url")
    assert response.status_code == 200
    data = response.json()
    assert "auth_url" in data
    auth_url = data["auth_url"]
    
    # Must use https://accounts.google.com/o/oauth2/v2/auth
    assert auth_url.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    
    parsed = urlparse(auth_url)
    params = parse_qs(parsed.query)
    
    # Check required query parameters: prompt=select_account, client_id, redirect_uri, response_type=code, scope
    assert "prompt" in params
    assert params["prompt"][0] == "select_account"
    
    assert "client_id" in params
    assert len(params["client_id"][0]) > 0
    
    assert "redirect_uri" in params
    assert len(params["redirect_uri"][0]) > 0
    
    assert "response_type" in params
    assert params["response_type"][0] == "code"
    
    assert "scope" in params
    assert "openid" in params["scope"][0]
    assert "email" in params["scope"][0]

def test_google_oauth_url_custom_redirect_uri():
    """Verify custom redirect_uri is reflected exactly in authorization URL."""
    custom_uri = "http://localhost:5173/login"
    response = client.get(f"/api/auth/google/url?redirect_uri={custom_uri}")
    assert response.status_code == 200
    data = response.json()
    parsed = urlparse(data["auth_url"])
    params = parse_qs(parsed.query)
    assert params["redirect_uri"][0] == custom_uri

def test_google_oauth_routes_no_404():
    """Verify all Google OAuth callback endpoints exist and do not return 404."""
    # 1. API prefix GET callbacks
    res1 = client.get("/api/auth/google/callback", follow_redirects=False)
    assert res1.status_code != 404
    
    res2 = client.get("/api/auth/callback", follow_redirects=False)
    assert res2.status_code != 404
    
    # 2. Non-API prefix GET callbacks (safeguards against missing /api in redirects)
    res3 = client.get("/auth/google/callback", follow_redirects=False)
    assert res3.status_code != 404
    
    res4 = client.get("/auth/callback", follow_redirects=False)
    assert res4.status_code != 404

def test_google_callback_post_exchange():
    """Verify POST callback handles code exchange and returns token."""
    payload = {
        "code": "test_auth_code",
        "redirect_uri": "http://localhost:5173/login"
    }
    
    # With /api/auth prefix
    response = client.post("/api/auth/google/callback", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "user" in data
    assert data["user"]["email"] == "shalombinrasheed@gmail.com"
    assert data["user"]["role"] == "SUPER_ADMIN"
    assert data["user"]["status"] == "APPROVED"

    # With /auth prefix
    response2 = client.post("/auth/google/callback", json=payload)
    assert response2.status_code == 200
    assert "access_token" in response2.json()

def test_google_callback_get_redirect():
    """Verify GET callback exchanges code and redirects to frontend without 404."""
    response = client.get("/api/auth/google/callback?code=test_auth_code", follow_redirects=False)
    assert response.status_code in (302, 307)
    location = response.headers.get("location")
    assert location is not None
    assert "/login?token=" in location
    assert "auth=google" in location
