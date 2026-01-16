
import asyncio
import sys
import os

# Add current dir to path to find meowtv package
sys.path.append(os.getcwd())

from meowtv.providers.meowtv import MeowTVProvider

async def main():
    try:
        p = MeowTVProvider()
        results = await p.search("Iron Man")
        if results:
            item = results[0]
            print(f"ID: {item.id}")
            print(f"Title: {item.title}")
        else:
            print("No results found")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
