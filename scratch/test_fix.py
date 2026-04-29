import asyncio
import json
from meowtv.providers.meowtv import MeowTVProvider
from meowtv.config import get_config

async def test():
    # Use the config proxy
    config = get_config()
    print(f"Testing with proxy: {config.proxy_url}")
    
    prov = MeowTVProvider(proxy_url=config.proxy_url)
    print("Searching for 'meow'...")
    results = await prov.search("meow")
    
    if results:
        print(f"Success! Found {len(results)} results.")
        for item in results[:5]:
            print(f" - {item.title} ({item.id})")
    else:
        print("Failed: No results found.")

if __name__ == "__main__":
    asyncio.run(test())
