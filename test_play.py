"""Test script to debug mpv playback."""
import asyncio
import os
from meowtv.providers.meowtoon import MeowToonProvider

async def main():
    p = MeowToonProvider()
    r = await p.fetch_stream('movie-68bf03e214aed75380bab612', 'mov-68bf03e214aed75380bab612')
    
    print("Video URL:", r.video_url[:80], "...")
    print()
    
    # Try different methods
    cmd = f'start "" "mpv" "--force-window=yes" "{r.video_url}"'
    print("Method 1 - os.system with start:")
    print(cmd[:100], "...")
    print()
    
    result = input("Try this command? (y/n): ")
    if result.lower() == 'y':
        os.system(cmd)

if __name__ == "__main__":
    asyncio.run(main())
