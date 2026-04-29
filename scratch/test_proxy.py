import asyncio
import httpx
from urllib.parse import quote

async def test_proxy_formats():
    proxy_base = "https://meowserver.utkarshg.workers.dev"
    target_url = "https://api.hlowb.com/v0.1/system/getSecurityKey/1?channel=IndiaA&clientType=1&lang=en-US"
    headers = {"User-Agent": "okhttp/4.9.0"}
    
    formats = [
        ("Query Param", f"{proxy_base}/api/proxy?url={quote(target_url)}"),
        ("Path Append", f"{proxy_base}/{target_url}"),
        ("Path Append (No Slash)", f"{proxy_base}{target_url}"),
    ]
    
    async with httpx.AsyncClient(timeout=10) as client:
        for name, url in formats:
            print(f"Testing {name}: {url}")
            try:
                res = await client.get(url, headers=headers)
                print(f"  Status: {res.status_code}")
                print(f"  Body: {res.text[:100]}")
            except Exception as e:
                print(f"  Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_proxy_formats())
