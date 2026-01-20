import asyncio
import os
import shutil
import tempfile
import subprocess
from typing import Literal

import httpx
from meowtv.config import get_config
from meowtv.models import Subtitle, VideoResponse


def find_player(player: Literal["mpv", "vlc"]) -> str | None:
    """Find player executable path."""
    if player == "mpv":
        # Try common mpv locations
        paths = ["mpv", "mpv.exe"]
        for p in paths:
            if shutil.which(p):
                return p
    elif player == "vlc":
        # Try common VLC locations
        paths = [
            "vlc",
            "vlc.exe",
            r"D:\VLC\vlc.exe",  # User's VLC location
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
        ]
        
        # Add user's AppData if present
        app_data = os.environ.get("APPDATA")
        if app_data:
            paths.append(os.path.join(app_data, "VLC", "vlc.exe"))
            
        for p in paths:
            if shutil.which(p):
                return p
            # Also check if file exists directly
            if os.path.isfile(p):
                return p
    return None


async def download_subtitles(subtitles: list[Subtitle]) -> list[tuple[str, str]]:
    """
    Download remote subtitles to temporary files in parallel.
    Returns a list of (url, local_path) tuples.
    """
    if not subtitles:
        return []

    async with httpx.AsyncClient(timeout=30) as client:
        async def fetch_one(sub):
            if not sub.url.startswith("http"):
                return None
            try:
                # Silent download
                res = await client.get(sub.url)
                if res.status_code == 200:
                    ext = ".srt"
                    if ".vtt" in sub.url.lower():
                        ext = ".vtt"
                    
                    fd, path = tempfile.mkstemp(suffix=ext, prefix="meowtv_sub_")
                    os.write(fd, res.content)
                    os.close(fd)
                    # print(f"[Player] Saved subtitle to: {path} ({len(res.content)} bytes)")
                    return (sub.url, path)
                else:
                    pass  # Silent fail
            except Exception as e:
                pass  # Silent error
            return None

        results = await asyncio.gather(*(fetch_one(s) for s in subtitles))
        return [r for r in results if r is not None]


def build_mpv_args(
    url: str,
    subtitles: list[Subtitle] | None = None,
    title: str | None = None,
    headers: dict[str, str] | None = None,
    extra_args: list[str] | None = None,
    suppress_output: bool = True,
    force_seekable: bool = False
) -> list[str]:
    """Build mpv command arguments."""
    args = ["mpv", "--force-window=yes", "--no-ytdl"]
    
    # Aggressive startup speed for HLS
    args.extend([
        "--cache=yes",
        "--demuxer-max-bytes=16MiB",
        "--demuxer-readahead-secs=2",
        "--cache-secs=2",
        "--audio-wait-open=0"
    ])
    
    if suppress_output:
        args.extend(["--msg-level=all=no", "--term-playing-msg="])
    
    # Add title (use = format for shell compatibility)
    if title:
        args.append(f"--title={title}")
    
    # Add headers for direct URLs (proxy URLs don't need headers passed to player)
    # Use native flags for Referer and User-Agent for better compatibility
    if headers:
        filtered_headers = {}
        for k, v in headers.items():
            if k.lower() == "referer":
                args.append(f"--referrer={v}")
            elif k.lower() == "user-agent":
                args.append(f"--user-agent={v}")
            elif k.lower() == "cookie":
                # Cookies need special handling - pass as header field
                filtered_headers["Cookie"] = v
            else:
                filtered_headers[k] = v
        
        if filtered_headers:
            # MPV uses format: "Header1: Value1,Header2: Value2"
            # But commas in values can cause issues, so we use separate args
            for hk, hv in filtered_headers.items():
                args.append(f"--http-header-fields={hk}: {hv}")
    
    # Add subtitles (use = format for shell compatibility)
    if subtitles:
        for i, sub in enumerate(subtitles):
            args.append(f"--sub-file={sub.url}")
            if i == 0:
                args.append("--sid=1")
    
    # Add extra args from config
    config = get_config()
    args.extend(config.mpv_args)
    
    # Add extra args passed directly
    if extra_args:
        args.extend(extra_args)
    
    # Force seekable if requested
    if force_seekable:
        args.append("--force-seekable=yes")
        
    # MPV optimization: Small initial buffer
    args.append("--cache-secs=2")
        
    # Add the URL last
    args.append(url)
    
    return args


def build_vlc_args(
    url: str,
    subtitles: list[Subtitle] | None = None,
    title: str | None = None,
    headers: dict[str, str] | None = None,
    extra_args: list[str] | None = None
) -> list[str]:
    """Build VLC command arguments."""
    # Find VLC executable
    vlc_path = find_player("vlc")
    if not vlc_path:
        vlc_path = "vlc"
    
    # Start with player path
    # Start with player path and optimizations
    args = [vlc_path, "--no-repeat", "--no-loop", "--quiet", "--network-caching=1000"]
    
    # Add title as a global option
    if title:
        args.extend(["--meta-title", title])
    
    # Add global headers
    if headers:
        if "Referer" in headers:
            args.extend(["--http-referrer", headers["Referer"]])
        if "User-Agent" in headers:
            args.extend(["--http-user-agent", headers["User-Agent"]])
    
    # Add the URL (MRL)
    args.append(url)
    
    # Add subtitles as MRL options (using colon)
    # This is often more reliable for secondary files when playing a primary MRL
    if subtitles:
        for sub in subtitles:
            # Use local path if it was downloaded (path exists)
            sub_path = sub.url
            if os.path.exists(sub_path):
                # VLC on Windows sometimes prefers absolute paths with forward slashes or escaped backslashes
                sub_path = os.path.abspath(sub_path)
            
            args.append(f":sub-file={sub_path}")
    
    # Add extra args from config
    config = get_config()
    if config.vlc_args:
        args.extend(config.vlc_args)
    
    # Add extra args passed directly
    if extra_args:
        args.extend(extra_args)
    
    return args


async def play(
    response: VideoResponse,
    player: Literal["mpv", "vlc"] | None = None,
    title: str | None = None,
    quality: str | None = None,
    suppress_output: bool = True
) -> subprocess.Popen | None:
    """
    Play a video using the specified player.
    
    Returns the subprocess if successful, None otherwise.
    """
    config = get_config()
    player = player or config.default_player
    
    # Find the player
    player_path = find_player(player)
    if not player_path:
        print(f"[Player] {player} not found. Please install it and ensure it's in your PATH.")
        return None
    
    # Select quality if specified
    url = response.video_url
    if quality and response.qualities:
        for q in response.qualities:
            if q.quality.lower() == quality.lower():
                url = q.url
                break
    
    # Check if we need to use the proxy (for HLS streams with headers)
    use_proxy = False
    actual_headers = response.headers or {}
    
    # Use proxy if there are headers that players can't handle well (like Cookie)
    if actual_headers.get("Cookie") and (".m3u8" in url or "playlist" in url.lower()):
        use_proxy = True
    
    if use_proxy:
        print("Loading player...", end="\r")  # Show loading, will be overwritten
        try:
            from meowtv.proxy import start_hls_proxy, build_proxy_url
            
            referer = actual_headers.get("Referer", "")
            cookie = actual_headers.get("Cookie", "")
            
            # Start proxy server
            port = start_hls_proxy(referer, cookie)
            # Rewrite URL to use proxy
            url = build_proxy_url(port, url, referer, cookie)
            
            actual_headers = {}  # No headers needed for local proxy
            # print(f"[Player] Using local proxy for playback at port {port}")
        except Exception as e:
            pass  # Silent fallback
    
    # Handle subtitles (VLC needs local files for remote subtitles usually)
    local_subs_info = []
    if response.subtitles:
        local_subs_info = await download_subtitles(response.subtitles)
        
        # Replace URLs with local paths for the player
        if local_subs_info:
            # Create a map for easy lookup
            sub_map = {url: path for url, path in local_subs_info}
            for sub in response.subtitles:
                if sub.url in sub_map:
                    sub.url = sub_map[sub.url]

    # Build arguments
    if player == "mpv":
        args = build_mpv_args(
            url,
            subtitles=response.subtitles,
            title=title,
            headers=actual_headers,
            suppress_output=suppress_output,
            force_seekable=response.force_seekable
        )
    else:
        args = build_vlc_args(
            url,
            subtitles=response.subtitles,
            title=title,
            headers=actual_headers
        )
    
    # Replace player name with actual path
    args[0] = player_path
    
    process = None
    try:
        # Call directly without shell=True to avoid quoting issues with headers
        # Silent launch
        
        # We start as Popen so we can handle cleanup if needed, 
        # but for simplicity in CLI we wait and then cleanup.
        process = subprocess.Popen(args)
        process.wait()
    except Exception as e:
        print(f"[Player] Failed to start {player}: {e}")
    finally:
        # Cleanup temporary subtitles
        for _, path in local_subs_info:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass
    
    return process


def is_player_available(player: Literal["mpv", "vlc"]) -> bool:
    """Check if a player is available."""
    return find_player(player) is not None


def get_available_players() -> list[str]:
    """Get list of available players."""
    players = []
    if is_player_available("mpv"):
        players.append("mpv")
    if is_player_available("vlc"):
        players.append("vlc")
    return players
