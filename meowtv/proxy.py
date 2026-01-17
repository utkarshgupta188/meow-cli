"""Flask-based HLS proxy server for CLI playback."""
import threading
import logging
from urllib.parse import urlparse, urljoin, urlencode, unquote
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import requests
from flask import Flask, request, Response, stream_with_context
from flask_cors import CORS

# from meowtv.enc2 import decrypt_inline
decrypt_inline = lambda x: x

# Enable Flask logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR) # Lowered level for less noise

# Persistent session for performance
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=100)
session.mount("http://", adapter)
session.mount("https://", adapter)

app = Flask(__name__)
CORS(app)

# Global config
_proxy_config = {
    "port": 0
}

def resolve_url(base_url, maybe_relative):
    """Resolve a URL relative to base_url, handling malformed URLs."""
    ref = maybe_relative.strip()
    
    # Handle broken URLs present in some providers (https:///path)
    if ref.startswith("https:///"):
        try:
            parsed_base = urlparse(base_url)
            authority = f"{parsed_base.scheme}://{parsed_base.netloc}"
            return ref.replace("https:///", authority + "/")
        except:
            pass
            
    if ref.startswith("http://") or ref.startswith("https://"):
        return ref
        
    try:
        return urljoin(base_url, ref)
    except:
        return ref

def make_proxy_url(absolute_url, referer, cookie, kind):
    """Generate a localhost proxy URL."""
    port = _proxy_config["port"]
    params = {
        "url": absolute_url,
        "referer": referer,
        "cookie": cookie,
        "kind": kind
    }
    return f"http://127.0.0.1:{port}/api/hls?{urlencode(params)}"

def rewrite_playlist(content, base_url, referer, cookie, limit_variants=3):
    """Rewrite HLS playlist content and optionally filter variants."""
    lines = content.splitlines()
    result = []
    
    variant_count = 0
    skip_next_url = False
    is_master = "#EXT-X-STREAM-INF" in content
    
    for line in lines:
        line = line.strip()
        if not line:
            result.append("")
            continue
            
        if line.startswith("#"):
            if is_master and "#EXT-X-STREAM-INF" in line:
                if variant_count >= limit_variants:
                    skip_next_url = True
                    continue
                variant_count += 1
                
            def replace_uri(match):
                key = match.group(1)
                val = match.group(2)
                resolved = resolve_url(base_url, val)
                k = "segment"
                low = resolved.lower()
                if ".m3u8" in low or "playlist" in low:
                    k = "playlist"
                proxied = make_proxy_url(resolved, referer, cookie, k)
                return f'{key}="{proxied}"'

            line = re.sub(r'([A-Z-]*URI)="([^"]+)"', replace_uri, line, flags=re.IGNORECASE)
            result.append(line)
        else:
            if skip_next_url:
                skip_next_url = False
                continue
                
            resolved = resolve_url(base_url, line)
            kind = "segment"
            lower_url = resolved.lower()
            if ".m3u8" in lower_url or "playlist" in lower_url:
                kind = "playlist"
                
            proxied = make_proxy_url(resolved, referer, cookie, kind)
            result.append(proxied)
            
    return "\n".join(result)

import re

@app.route('/api/hls')
def proxy_hls():
    url = request.args.get('url')
    referer = request.args.get('referer', '')
    cookie = request.args.get('cookie', '')
    kind = request.args.get('kind', 'segment')
    print(f"[Proxy] Request: {kind.upper()} -> {url}")
    
    if not url:
        return "Missing URL", 400

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": referer,
        "Cookie": cookie
    }
    
    # Range handling - Only for segments, NOT playlists
    if 'Range' in request.headers and kind != 'playlist':
        headers['Range'] = request.headers['Range']
        
    try:
        # Use persistent session for speed
        req = session.get(url, headers=headers, stream=True, timeout=15, verify=False)
        
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection', 'access-control-allow-origin']
        resp_headers = [(name, value) for (name, value) in req.headers.items()
                       if name.lower() not in excluded_headers]
        
        # Check if playlist
        is_playlist = kind == "playlist" or ".m3u8" in url.lower() or "mpegurl" in req.headers.get('Content-Type', '').lower()
        
        if is_playlist:
            # decode content directly for speed
            text = req.content.decode('utf-8', errors='replace')
            rewritten = rewrite_playlist(text, url, referer, cookie)
            return Response(rewritten, status=req.status_code, headers=resp_headers, content_type="application/vnd.apple.mpegurl")
        else:
            # Stream segments with larger chunks for high-bitrate content
            return Response(stream_with_context(req.iter_content(chunk_size=128*1024)),
                          status=req.status_code,
                          headers=resp_headers,
                          content_type=req.headers.get('Content-Type'))
                          
    except Exception as e:
        print(f"[Flask Proxy] Error processing {url}: {e}")
        return f"Error: {e}", 500

class ProxyServer:
    def __init__(self):
        self.port = 0
        self.server_thread = None
        
    def start(self, referer, cookie):
        # Find port
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('127.0.0.1', 0))
        self.port = sock.getsockname()[1]
        sock.close()
        
        _proxy_config["port"] = self.port
        
        def run_app():
            # threaded=True is default. use_reloader=False prevents restarting.
            app.run(host='127.0.0.1', port=self.port, threaded=True, use_reloader=False)
            
        self.server_thread = threading.Thread(target=run_app, daemon=True)
        self.server_thread.start()
        
        print(f"[CLI Proxy] Flask Server started on http://127.0.0.1:{self.port}")
        return self.port
        
    def stop(self):
        # Flask checking doesn't have easy stop. 
        # But daemon thread dies with main process.
        pass

# Global instance management
_server_instance = None

def start_hls_proxy(referer, cookie):
    global _server_instance
    if not _server_instance:
        _server_instance = ProxyServer()
    # If already running, we might need to restart if referer/cookie changed? 
    # But port logic in Flask app uses query params, so referer/cookie in arguments 
    # are only for the *initial* logging or unused?
    # Wait, start() finds a port. If called again, we just reuse the instance if running?
    # Our simple logic: Just create new one? No, we can reuse.
    # The Flask routes reads referer/cookie from QUERY PARAMS, so the server is stateless regarding config!
    # So we just need ONE server running.
    
    if _server_instance.port == 0:
        return _server_instance.start(referer, cookie)
    return _server_instance.port

def build_proxy_url(port, url, referer, cookie, kind="playlist"):
    params = {
        "url": url,
        "referer": referer,
        "cookie": cookie,
        "kind": kind
    }
    return f"http://127.0.0.1:{port}/api/hls?{urlencode(params)}"

def stop_proxy():
    global _server_instance
    if _server_instance:
        _server_instance.stop()
