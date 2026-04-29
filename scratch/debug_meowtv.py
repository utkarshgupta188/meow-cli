import asyncio
import httpx
from meowtv.providers.meowtv import MeowTVProvider

async def test():
    # Use the proxy from config
    proxy_url = "https://meowserver.utkarshg.workers.dev"
    prov = MeowTVProvider(proxy_url=proxy_url)
    
    print(f"Testing with proxy: {proxy_url}")
    async with await prov._get_client() as client:
        print("--- Testing get_security_key ---")
        key, cookie = await prov._get_security_key(client)
        print(f"Result: key={key}, cookie={cookie}")
        
        if key:
            print("--- Testing search ---")
            results = await prov.search("meow")
            print(f"Search results: {len(results)}")
            for item in results[:3]:
                print(f"  - {item.title} ({item.id})")
        else:
            print("Failed to get security key.")

if __name__ == "__main__":
    asyncio.run(test())
