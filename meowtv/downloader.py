"""Download manager for MeowTV CLI."""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from meowtv.config import get_config
from meowtv.models import VideoResponse


def find_ytdlp() -> str | None:
    """Find yt-dlp executable."""
    paths = ["yt-dlp", "yt-dlp.exe"]
    for p in paths:
        if shutil.which(p):
            return p
    return None


def find_ffmpeg() -> str | None:
    """Find ffmpeg executable."""
    paths = ["ffmpeg", "ffmpeg.exe"]
    for p in paths:
        if shutil.which(p):
            return p
    return None


def download_with_ytdlp(
    url: str,
    output_path: Path,
    headers: dict[str, str] | None = None,
    quality: str | None = None,
    progress_callback: Callable[[float], None] | None = None
) -> bool:
    """
    Download video using yt-dlp.
    
    Returns True if successful.
    """
    ytdlp = find_ytdlp()
    if not ytdlp:
        print("[Downloader] yt-dlp not found. Please install it: pip install yt-dlp")
        return False
    
    args = [
        ytdlp,
        url,
        "-o", str(output_path),
        "--no-warnings",
        "--progress",
        "--merge-output-format", "mp4",  # Ensure output is mp4
        "--embed-subs",  # Embed subtitles if available
        "--audio-multistreams",  # Download and merge all audio tracks
    ]
    
    # Add headers
    if headers:
        for key, value in headers.items():
            args.extend(["--add-header", f"{key}: {value}"])
    
    # Format selection strategy for "All Audio" + "Robust Fix" + "Generic Fallback":
    # 1. bestvideo + all audio-only + best English variant (Fixes provider where English is hidden in video var)
    # 2. bestvideo + all audio-only (Gets separate audios like Spanish)
    # 3. bestvideo + best[format_id*=English] (Fallback fix)
    # 4. bestvideo + bestaudio (Standard)
    # 5. best (Single file)
    quality_map = {
        "1080p": "bestvideo[height<=1080]+mergeall[vcodec=none]+best[height<=1080][format_id*=English]/bestvideo[height<=1080]+mergeall[vcodec=none]/best[height<=1080]/best",
        "720p": "bestvideo[height<=720]+mergeall[vcodec=none]+best[height<=720][format_id*=English]/bestvideo[height<=720]+mergeall[vcodec=none]/best[height<=720]/best",
        "480p": "bestvideo[height<=480]+mergeall[vcodec=none]+best[height<=480][format_id*=English]/bestvideo[height<=480]+mergeall[vcodec=none]/best[height<=480]/best",
    }
    if quality and quality in quality_map:
        format_str = quality_map[quality]
    else:
        # Default robust chain
        format_str = "bestvideo+mergeall[vcodec=none]+best[format_id*=English]/bestvideo+mergeall[vcodec=none]/bestvideo+best[format_id*=English]/bestvideo+bestaudio/best"
    args.extend(["-f", format_str])
    
    try:
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # Parse progress from output
        for line in process.stdout:  # type: ignore
            line = line.strip()
            if "[download]" in line and "%" in line:
                try:
                    # Parse percentage from output like "[download]  45.2% of 1.23GiB"
                    parts = line.split()
                    for part in parts:
                        if "%" in part:
                            pct = float(part.replace("%", ""))
                            if progress_callback:
                                progress_callback(pct)
                            break
                except:
                    pass
        
        process.wait()
        return process.returncode == 0
        
    except Exception as e:
        print(f"[Downloader] yt-dlp error: {e}")
        return False


def download_with_ffmpeg(
    url: str,
    output_path: Path,
    headers: dict[str, str] | None = None
) -> bool:
    """
    Download video using ffmpeg (for HLS streams).
    
    Returns True if successful.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        print("[Downloader] ffmpeg not found. Please install it.")
        return False
    
    args = [
        ffmpeg,
        "-y",  # Overwrite output
        "-hide_banner",
        "-loglevel", "warning",
    ]
    
    # Add headers
    if headers:
        header_str = "\r\n".join(f"{k}: {v}" for k, v in headers.items())
        args.extend(["-headers", header_str])
    
    args.extend([
        "-i", url,
        "-c", "copy",  # Copy streams without re-encoding
        str(output_path)
    ])
    
    try:
        result = subprocess.run(args, capture_output=True, text=True)
        return result.returncode == 0
    except Exception as e:
        print(f"[Downloader] ffmpeg error: {e}")
        return False


def download(
    response: VideoResponse,
    title: str,
    output_dir: Path | str | None = None,
    quality: str | None = None,
    use_ffmpeg: bool = False
) -> Path | None:
    """
    Download a video from a VideoResponse.
    
    Args:
        response: The video response with URL
        title: Title for the output file
        output_dir: Output directory (uses config default if not specified)
        quality: Preferred quality (1080p, 720p, 480p)
        use_ffmpeg: Force use of ffmpeg instead of yt-dlp
    
    Returns:
        Path to downloaded file if successful, None otherwise
    """
    config = get_config()
    
    # Determine output directory
    if output_dir is None:
        output_dir = Path(config.download_dir)
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Clean title for filename
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
    safe_title = safe_title[:100]  # Limit length
    
    # Select quality URL if specified
    url = response.video_url
    if quality and response.qualities:
        for q in response.qualities:
            if q.quality.lower() == quality.lower():
                url = q.url
                break
    
    # Determine file extension based on URL
    if ".m3u8" in url or "hls" in url.lower():
        ext = ".mp4"  # HLS will be converted to MP4
    elif ".mp4" in url:
        ext = ".mp4"
    elif ".mkv" in url:
        ext = ".mkv"
    else:
        ext = ".mp4"
    
    output_path = output_dir / f"{safe_title}{ext}"
    
    # Avoid overwriting
    counter = 1
    while output_path.exists():
        output_path = output_dir / f"{safe_title} ({counter}){ext}"
        counter += 1
    
    print(f"[Downloader] Downloading to: {output_path}")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task = progress.add_task(f"Downloading {safe_title}...", total=100)
        
        def update_progress(pct: float):
            progress.update(task, completed=pct)
        
        # Try yt-dlp first (unless forced to use ffmpeg)
        if not use_ffmpeg and find_ytdlp():
            success = download_with_ytdlp(
                url,
                output_path,
                headers=response.headers,
                quality=quality,
                progress_callback=update_progress
            )
        else:
            success = download_with_ffmpeg(
                url,
                output_path,
                headers=response.headers
            )
        
        if success:
            progress.update(task, completed=100)
            return output_path
        else:
            # Clean up failed download
            if output_path.exists():
                output_path.unlink()
            return None


def is_download_available() -> bool:
    """Check if downloading is possible."""
    return find_ytdlp() is not None or find_ffmpeg() is not None
