"""Media player integration for MeowTV CLI."""

import shutil
import subprocess
from typing import Literal

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
        for p in paths:
            if shutil.which(p):
                return p
            # Also check if file exists directly
            import os
            if os.path.isfile(p):
                return p
    return None


def build_mpv_args(
    url: str,
    subtitles: list[Subtitle] | None = None,
    title: str | None = None,
    headers: dict[str, str] | None = None,
    extra_args: list[str] | None = None,
    suppress_output: bool = True
) -> list[str]:
    """Build mpv command arguments."""
    args = ["mpv", "--force-window=yes", url]
    
    if suppress_output:
        args.extend(["--msg-level=all=no", "--term-playing-msg="])
    
    # Add title (use = format for shell compatibility)
    if title:
        args.append(f"--title={title}")
    
    # Add headers (use = format for shell compatibility)
    if headers:
        for k, v in headers.items():
            args.append(f"--http-header-fields={k}: {v}")
    
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
    
    args = [vlc_path, url]
    
    # Add title
    if title:
        args.extend(["--meta-title", title])
    
    # Add headers via http-user-agent if Referer/User-Agent
    if headers:
        if "Referer" in headers:
            args.extend(["--http-referrer", headers["Referer"]])
        if "User-Agent" in headers:
            args.extend(["--http-user-agent", headers["User-Agent"]])
    
    # Add subtitles
    if subtitles:
        for sub in subtitles:
            args.extend(["--sub-file", sub.url])
    
    # Add extra args from config
    config = get_config()
    args.extend(config.vlc_args)
    
    # Add extra args passed directly
    if extra_args:
        args.extend(extra_args)
    
    return args


def play(
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
    
    # Build arguments
    if player == "mpv":
        args = build_mpv_args(
            url,
            subtitles=response.subtitles,
            title=title,
            headers=response.headers,
            suppress_output=suppress_output
        )
    else:
        args = build_vlc_args(
            url,
            subtitles=response.subtitles,
            title=title,
            headers=response.headers
        )
    
    # Replace player name with actual path
    args[0] = player_path
    
    try:
        # Build command string for shell execution
        cmd = ' '.join(f'"{arg}"' for arg in args)
        result = subprocess.call(cmd, shell=True)
        return None
    except Exception as e:
        print(f"[Player] Failed to start {player}: {e}")
        return None


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
