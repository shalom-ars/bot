import urllib.request
import json

urls = [
    "http://127.0.0.1:8000/api/health",
    "http://127.0.0.1:8000/api/paper-test/health",
    "http://127.0.0.1:8000/api/live/status"
]

for url in urls:
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
            print(f"--- {url} ---")
            print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"Error fetching {url}: {e}")
