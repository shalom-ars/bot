import requests
import json

base_url = "http://localhost:8000/api"

print("1. Signup")
resp = requests.post(f"{base_url}/auth/signup", json={"email": "newuser@example.com", "password": "newpass"})
print(resp.status_code, resp.text[:200])

print("\n2. Login")
resp = requests.post(f"{base_url}/auth/login", data={"username": "admin@example.com", "password": "adminpassword"})
print(resp.status_code, resp.text[:200])

if resp.status_code != 200:
    resp = requests.post(f"{base_url}/auth/login", data={"username": "admin@example.com", "password": "adminpass"})

token = resp.json().get("access_token")
headers = {"Authorization": f"Bearer {token}"}

print("\n3. Portfolio")
resp = requests.get(f"{base_url}/portfolio", headers=headers)
print(resp.status_code, resp.text[:200])

print("\n4. Markets")
resp = requests.get(f"{base_url}/markets", headers=headers)
print(resp.status_code, resp.text[:200])

print("\n5. Signals")
resp = requests.get(f"{base_url}/signals", headers=headers)
print(resp.status_code, resp.text[:200])

print("\n6. Positions")
resp = requests.get(f"{base_url}/positions", headers=headers)
print(resp.status_code, resp.text[:200])

print("\n7. Trades")
resp = requests.get(f"{base_url}/trades", headers=headers)
print(resp.status_code, resp.text[:200])

print("\n8. Performance")
resp = requests.get(f"{base_url}/performance", headers=headers)
print(resp.status_code, resp.text[:200])

print("\n9. Risk")
resp = requests.get(f"{base_url}/risk", headers=headers)
print(resp.status_code, resp.text[:200])

print("\n10. Settings")
resp = requests.get(f"{base_url}/settings", headers=headers)
print(resp.status_code, resp.text[:200])

print("\n11. Research Terminal (System Health)")
resp = requests.get(f"{base_url}/system/health", headers=headers)
print(resp.status_code, resp.text[:200])
