import httpx
import asyncio
import json
from urllib.parse import quote

MAIN_URL = "https://api.hlowb.com"
PROXY_WORKER_URL = "https://meowserver.hackeru491.workers.dev"
HEADERS = {
    "User-Agent": "okhttp/4.9.0",
}

async def test_key():
    target_url = f"{MAIN_URL}/v0.1/system/getSecurityKey/1?channel=IndiaA&clientType=1&lang=en-US"
    
    # 1. Test Native
    print(f"--- Testing Native ---")
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(target_url, headers=HEADERS)
            print(f"Status: {res.status_code}")
            print(f"Text: {res.text[:200]}")
        except Exception as e:
            print(f"Error: {e}")

    # 2. Test Simple Proxy (Prepending)
    print(f"\n--- Testing Simple Proxy (Prepending) ---")
    proxy_url = f"{PROXY_WORKER_URL}/api/proxy?url={quote(target_url)}"
    print(f"Proxy URL: {proxy_url}")
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(proxy_url, headers=HEADERS)
            print(f"Status: {res.status_code}")
            print(f"Text: {res.text[:200]}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_key())
