"""Proxy utilities for stream URLs."""

import urllib.parse


# Default to empty (direct connection); can be overridden via config
PROXY_WORKER_URL = ""


def set_proxy_url(url: str) -> None:
    """Set the Cloudflare Worker proxy URL."""
    global PROXY_WORKER_URL
    PROXY_WORKER_URL = url.rstrip("/") if url else ""


def get_hls_proxy_url(target_url: str, params: dict[str, str] | None = None) -> str:
    """Generate proxied HLS URL."""
    if params is None:
        params = {}

    query_params = {"url": target_url, **{k: v for k, v in params.items() if v}}
    query_string = urllib.parse.urlencode(query_params)

    if PROXY_WORKER_URL:
        return f"{PROXY_WORKER_URL}/api/hls?{query_string}"
    return target_url  # Direct URL for CLI


def get_simple_proxy_url(target_url: str, params: dict[str, str] | None = None) -> str:
    """Generate simple proxied URL."""
    if params is None:
        params = {}

    query_params = {"url": target_url, **{k: v for k, v in params.items() if v}}
    query_string = urllib.parse.urlencode(query_params)

    if PROXY_WORKER_URL:
        return f"{PROXY_WORKER_URL}/api/proxy?{query_string}"
    return target_url  # Direct URL for CLI
