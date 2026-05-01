"""MeowVerse (CineTv) provider."""

import asyncio
import base64
import hashlib
import json
import time
import gzip
import httpx
from typing import Any, Optional
from Crypto.Cipher import AES, DES3
from Crypto.Util.Padding import unpad

from meowtv.models import (
    ContentItem, Episode, HomeRow, MovieDetails,
    Quality, Season, Subtitle, VideoResponse
)
from meowtv.providers.base import Provider

# Constants from CineTv
SECRET_KEY_ENCRYPTED = "MxASAkl/yHTGg+/Tw1R7u96nGqkWsOZ2"
DES_KEY = "dsawdf634eebGFHITR5UT9kS0"
DES_IV = "32456738"
AES_KEY = "0123456789123456"
AES_IV = "2015030120123456"
WS_SECRET = "00b5f05c40b4f1d91dbc9b3fd8a059ef"
MAIN_URL = "https://i6a6.t9z0.com"
DEVICE_ID = "2987149b2e2a63b2"
GAID = ""

class MeowVerseProvider(Provider):
    """MeowVerse (CineTv) content provider."""

    def __init__(self, proxy_url: Optional[str] = None):
        super().__init__(proxy_url)
        self.secret = self._des3_decrypt(SECRET_KEY_ENCRYPTED)
        self.token = ""
        self._last_init = 0
        self._init_lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "MeowVerse"

    # --- Encryption Helpers ---

    def _des3_decrypt(self, encrypted_text: str) -> str | None:
        try:
            key = DES_KEY.encode('utf-8')[:24]
            iv = DES_IV.encode('utf-8')
            cipher = DES3.new(key, DES3.MODE_CBC, iv)
            encrypted_data = base64.b64decode(encrypted_text)
            decrypted_data = unpad(cipher.decrypt(encrypted_data), 8)
            return decrypted_data.decode('utf-8')
        except Exception:
            return None

    def _aes_decrypt(self, encrypted_base64: str) -> str | None:
        try:
            key = AES_KEY.encode('utf-8')
            iv = AES_IV.encode('utf-8')
            cipher = AES.new(key, AES.MODE_CBC, iv)
            encrypted_data = base64.b64decode(encrypted_base64)
            decrypted_data = unpad(cipher.decrypt(encrypted_data), 16)
            
            if len(decrypted_data) >= 2 and decrypted_data[0] == 0x1f and decrypted_data[1] == 0x8b:
                return gzip.decompress(decrypted_data).decode('utf-8')
            
            return decrypted_data.decode('utf-8')
        except Exception:
            return None

    def _md5(self, text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def _generate_sign(self, cur_time: str) -> str:
        sign_string = (self.secret or "") + DEVICE_ID + cur_time
        return self._md5(sign_string).upper()

    def _generate_p2p_token(self, vod_id: str, timestamp: str) -> str:
        salt = "Zox882LYjEn4Rqpa"
        concatenated = salt + DEVICE_ID + vod_id + timestamp
        return self._md5(concatenated).upper()

    def _get_headers(self, cur_time: str) -> dict[str, str]:
        return {
            "androidid": DEVICE_ID,
            "app_id": "cinetvin",
            "app_language": "en",
            "channel_code": "cinetvin_3001",
            "cur_time": cur_time,
            "device_id": DEVICE_ID,
            "en_al": "0",
            "gaid": GAID,
            "Host": "i6a6.t9z0.com",
            "is_display": "GMT+05:30",
            "is_language": "en",
            "is_vvv": "0",
            "log-header": "I am the log request header.",
            "mob_mfr": "google",
            "mobmodel": "Pixel 5",
            "package_name": "com.cti.cinetvin",
            "sign": self._generate_sign(cur_time),
            "sys_platform": "2",
            "sysrelease": "13",
            "token": self.token,
            "User-Agent": "okhttp/4.11.0",
            "version": "30000",
            "Content-Type": "application/x-www-form-urlencoded"
        }

    async def _ensure_token(self):
        """Lazy initialize device token."""
        async with self._init_lock:
            if self.token and (time.time() - self._last_init) < 3600:
                return
            
            url = f"{MAIN_URL}/api/public/init"
            cur_time = str(int(time.time() * 1000))
            headers = self._get_headers(cur_time)
            data = {"invited_by": "", "is_install": "1"}
            
            async with httpx.AsyncClient(timeout=30) as client:
                try:
                    response = await client.post(url, headers=headers, data=data)
                    if response.status_code == 200:
                        resp_text = response.text.strip()
                        json_text = self._aes_decrypt(resp_text) if not resp_text.startswith("{") else resp_text
                        if json_text:
                            result = json.loads(json_text)
                            self.token = result.get("result", {}).get("user_info", {}).get("token", "")
                            self._last_init = time.time()
                except Exception:
                    pass

    # --- Provider Methods ---

    async def fetch_home(self, page: int = 1) -> list[HomeRow]:
        """Fetch home page content."""
        if page > 1: return []
        
        await self._ensure_token()
        
        # CineTv usually has a home/index endpoint. Let's try /api/vod/index or search fallback.
        # Based on typical implementations, we'll search for popular content.
        recent = await self.search("2024")
        if recent:
            return [HomeRow(name="Recently Added", contents=recent)]
        
        return []

    async def search(self, query: str) -> list[ContentItem]:
        """Search for content."""
        await self._ensure_token()
        
        url = f"{MAIN_URL}/api/search/result"
        cur_time = str(int(time.time() * 1000))
        headers = self._get_headers(cur_time)
        data = {"kw": query, "pn": "1"}
        
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.post(url, headers=headers, data=data)
                if response.status_code == 200:
                    decrypted = self._aes_decrypt(response.text.strip())
                    if decrypted:
                        data_json = json.loads(decrypted)
                        results = data_json.get("result", [])
                        
                        contents = []
                        for item in results:
                            contents.append(ContentItem(
                                id=str(item.get("id")),
                                title=item.get("vod_name", ""),
                                cover_image=item.get("vod_pic") or "",
                                type="movie" # We will determine actual type in details
                            ))
                        return contents
            except Exception:
                pass
            return []

    async def fetch_details(self, content_id: str, include_episodes: bool = True) -> MovieDetails | None:
        """Fetch content details."""
        await self._ensure_token()
        
        url = f"{MAIN_URL}/api/vod/info_new"
        cur_time = str(int(time.time() * 1000))
        headers = self._get_headers(cur_time)
        p2p_token = self._generate_p2p_token(str(content_id), cur_time)
        data = {
            "sign": p2p_token,
            "vod_id": str(content_id),
            "cur_time": cur_time,
            "audio_type": "0"
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.post(url, headers=headers, data=data)
                if response.status_code == 200:
                    decrypted = self._aes_decrypt(response.text.strip())
                    if decrypted:
                        resp_data = json.loads(decrypted)
                        info = resp_data.get("result", {})
                        
                        if not info: return None
                        
                        episodes = []
                        collections = info.get("vod_collection", [])
                        for col in collections:
                            episodes.append(Episode(
                                id=str(col.get("id") or f"{content_id}:{col.get('title') or col.get('episode_no')}"),
                                title=col.get("title", f"Episode {col.get('episode_no', '')}"),
                                season=1, 
                                number=int(col.get("episode_no") or 1),
                                source_movie_id=content_id,
                                description=col.get("vod_name")
                            ))
                        
                        # If no collections, it might be a direct movie
                        if not episodes:
                             episodes.append(Episode(
                                id=content_id,
                                title=info.get("vod_name", ""),
                                season=1,
                                number=1,
                                source_movie_id=content_id
                            ))

                        return MovieDetails(
                            id=content_id,
                            title=info.get("vod_name", ""),
                            description=info.get("vod_blurb", ""),
                            year=int(info.get("vod_year") or 0),
                            score=float(info.get("vod_score") or 0.0),
                            cover_image=info.get("vod_pic") or "",
                            background_image=info.get("vod_pic_bg") or "",
                            episodes=episodes,
                            seasons=[Season(id="1", number=1, name="Season 1")]
                        )
            except Exception:
                pass
            return None

    async def fetch_stream(
        self,
        movie_id: str,
        episode_id: str,
        language_id: str | int | None = None
    ) -> VideoResponse | None:
        """Fetch stream URL."""
        await self._ensure_token()
        
        # We need to find the vod_url. info_new returns it in collections.
        url = f"{MAIN_URL}/api/vod/info_new"
        cur_time = str(int(time.time() * 1000))
        headers = self._get_headers(cur_time)
        p2p_token = self._generate_p2p_token(str(movie_id), cur_time)
        data = {
            "sign": p2p_token,
            "vod_id": str(movie_id),
            "cur_time": cur_time,
            "audio_type": "0"
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.post(url, headers=headers, data=data)
                if response.status_code == 200:
                    decrypted = self._aes_decrypt(response.text.strip())
                    if decrypted:
                        resp_data = json.loads(decrypted)
                        info = resp_data.get("result", {})
                        collections = info.get("vod_collection", [])
                        
                        raw_url = None
                        # Find the matching episode
                        if ":" in episode_id:
                             # It's a generated ID
                             for col in collections:
                                 generated_id = str(col.get("id") or f"{movie_id}:{col.get('title') or col.get('episode_no')}")
                                 if generated_id == episode_id:
                                     raw_url = col.get("vod_url") or col.get("down_url")
                                     break
                        else:
                             # Direct ID or fallback
                             for col in collections:
                                 if str(col.get("id")) == episode_id:
                                     raw_url = col.get("vod_url") or col.get("down_url")
                                     break
                        
                        # Fallback to info top-level if single movie
                        if not raw_url:
                            raw_url = info.get("vod_url") or info.get("down_url")
                            
                        if not raw_url: return None
                        
                        # Sign URL
                        from urllib.parse import urlparse
                        path = urlparse(raw_url).path
                        expiry = int(time.time()) + (5 * 60 * 60)
                        ws_time = hex(expiry)[2:]
                        raw = WS_SECRET + path + ws_time
                        ws_secret = self._md5(raw)
                        signed_url = f"{raw_url}?wsSecret={ws_secret}&wsTime={ws_time}"
                        
                        return VideoResponse(
                            video_url=signed_url,
                            headers={"User-Agent": "okhttp/4.11.0"}
                        )
            except Exception:
                pass
            return None
