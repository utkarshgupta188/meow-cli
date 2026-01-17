"""MeowVerse (CineStream) provider - Cinemeta Frontend Only."""

import asyncio
import re
import secrets
from bs4 import BeautifulSoup
import httpx
from typing import Any

from meowtv.models import (
    ContentItem, Episode, HomeRow, MovieDetails,
    Quality, Season, Subtitle, Track, VideoResponse, RelatedItem
)
from meowtv.providers.base import Provider

# NetMirror (Netflix Mirror) APIs
NETMIRROR_MAIN_URL = "https://net20.cc"
NETMIRROR_NEW_URL = "https://net51.cc"

# NetMirror cached cookie (module-level)
_netmirror_cookie: str | None = None
_netmirror_cache_time: float = 0
_NETMIRROR_CACHE_DURATION = 54_000_000  # 15 hours in ms

class MeowVerseProvider(Provider):
    """MeowVerse (CineStream) content provider."""

    @property
    def name(self) -> str:
        return "MeowVerse"

    async def fetch_home(self, page: int = 1) -> list[HomeRow]:
        """Fetch home page content using Cinemeta catalogs."""
        if page > 1:
            return []

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                rows: list[HomeRow] = []
                catalogs = [
                    ("Top Movies", f"{CINEMETA_URL}/catalog/movie/top/skip=0.json", "movie"),
                    ("Top Series", f"{CINEMETA_URL}/catalog/series/top/skip=0.json", "series"),
                    ("Top Action Movies", f"{CINEMETA_URL}/catalog/movie/top/skip=0&genre=Action.json", "movie"),
                    ("Top Comedy Series", f"{CINEMETA_URL}/catalog/series/top/skip=0&genre=Comedy.json", "series"),
                    ("Top Anime", f"{KITSU_URL}/catalog/anime/kitsu-anime-trending/skip=0.json", "anime"),
                ]

                # Fetch sequentially
                for name, url, type_ in catalogs:
                    try:
                        res = await client.get(url)
                        data = res.json()
                        metas = data.get("metas", [])
                        
                        contents: list[ContentItem] = []
                        for m in metas:
                            m_id = m.get("id")
                            if not m_id: continue
                            
                            contents.append(ContentItem(
                                id=m_id,
                                title=m.get("name", ""),
                                cover_image=m.get("poster") or "",
                                type="movie" if type_ == "movie" else "show"
                            ))
                            
                        if contents:
                            rows.append(HomeRow(name=name, contents=contents))
                    except Exception as cat_e:
                        pass # print(f"[CineStream] Catalog error {name}: {cat_e}")

                return rows
            except Exception as e:
                # print(f"[CineStream] Home error: {e}")
                return []

    async def search(self, query: str) -> list[ContentItem]:
        """Search for content using NetMirror (matching Web App)."""
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                # Bypass first
                cookie = await self._netmirror_bypass()
                import time
                tm = int(time.time())
                
                url = f"{NETMIRROR_MAIN_URL}/search.php?s={query}&t={tm}"
                
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"{NETMIRROR_MAIN_URL}/tv/home",
                    "Cookie": f"t_hash_t={cookie}; ott=nf; hd=on; user_token=233123f803cf02184bf6c67e149cdd50"
                }
                
                res = await client.get(url, headers=headers)
                data = res.json()
                results = data.get("searchResult", [])
                
                contents = []
                for item in results:
                    c_id = item.get("id")
                    if not c_id: continue
                    
                    contents.append(ContentItem(
                        id=c_id, # Use NetMirror ID directly!
                        title=item.get("t", ""),
                        cover_image=f"https://imgcdn.kim/poster/v/{c_id}.jpg",
                        type="movie" # NetMirror search doesn't distinguish? Assume movie or check extra fields
                    ))
                
                return contents
                
            except Exception as e:
                # print(f"[MeowVerse] Search error: {e}")
                return []

    async def fetch_details(self, content_id: str, include_episodes: bool = True) -> MovieDetails | None:
        """Fetch content details using NetMirror (matching Web App)."""
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                # Bypass
                cookie = await self._netmirror_bypass()
                import time
                tm = int(time.time())
                
                url = f"{NETMIRROR_MAIN_URL}/post.php?id={content_id}&t={tm}"
                
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"{NETMIRROR_MAIN_URL}/tv/home",
                    "Cookie": f"t_hash_t={cookie}; ott=nf; hd=on; user_token=233123f803cf02184bf6c67e149cdd50"
                }
                
                res = await client.get(url, headers=headers)
                data = res.json()
                
                title = data.get("title", "")
                desc = data.get("desc", "")
                year = data.get("year", "0")
                if "-" in str(year):
                     year = str(year).split("-")[0]
                year_val = int(year) if year and str(year).isdigit() else 0
                
                score_str = data.get("match", "").replace("IMDb ", "")
                score = float(score_str) if score_str and score_str.replace(".", "").isdigit() else 0.0
                
                seasons: list[Season] = []
                data_seasons = data.get("season", [])
                if data_seasons:
                    for s in data_seasons:
                        s_id = str(s.get("id"))
                        seasons.append(Season(
                            id=s_id,
                            number=int(s_id) if s_id.isdigit() else 1,
                            name=f"Season {s_id}"
                        ))

                episodes: list[Episode] = []
                data_episodes = data.get("episodes", [])
                seen_eps = set()

                def add_eps(eps_list):
                    for ep in eps_list:
                        if not ep: continue
                        ep_id = ep.get("id")
                        if not ep_id or ep_id in seen_eps: continue
                        seen_eps.add(ep_id)
                        
                        s_str = str(ep.get("s", "S1")).replace("S", "")
                        e_str = str(ep.get("ep", "E1")).replace("E", "")
                        
                        episodes.append(Episode(
                            id=ep_id,
                            title=ep.get("t", f"Episode {ep_id}"),
                            season=int(s_str) if s_str.isdigit() else 1,
                            number=int(e_str) if e_str.isdigit() else 1,
                            cover_image=f"https://imgcdn.kim/epimg/150/{ep_id}.jpg",
                            source_movie_id=content_id
                        ))

                has_episodes = data_episodes and len(data_episodes) > 0 and data_episodes[0]
                
                if has_episodes:
                    # 1. First page from post.php
                    add_eps(data_episodes)

                    # 2. Next pages and Other seasons - Optimize by fetching in parallel
                    tasks = []

                    # Current season pagination
                    if data.get("nextPageShow") == 1 and data.get("nextPageSeason"):
                        next_s = data.get("nextPageSeason")
                        
                        async def fetch_pages(s_id, start_pg):
                            curr_pg = start_pg
                            while curr_pg < 10: # Lowered cap for speed
                                try:
                                    p_url = f"{NETMIRROR_MAIN_URL}/episodes.php?s={s_id}&series={content_id}&t={tm}&page={curr_pg}"
                                    p_res = await client.get(p_url, headers=headers)
                                    p_data = p_res.json()
                                    p_eps = p_data.get("episodes", [])
                                    if not p_eps: break
                                    add_eps(p_eps)
                                    if p_data.get("nextPageShow") == 0: break
                                    curr_pg += 1
                                except: break
                        
                        tasks.append(fetch_pages(next_s, 2))

                    # Other seasons (parallellized)
                    if len(data_seasons) > 1:
                        async def fetch_season(s_id):
                            try:
                                s_url = f"{NETMIRROR_MAIN_URL}/episodes.php?s={s_id}&series={content_id}&t={tm}&page=1"
                                s_res = await client.get(s_url, headers=headers)
                                s_data = s_res.json()
                                add_eps(s_data.get("episodes", []))
                                
                                # If there are more pages in this season
                                if s_data.get("nextPageShow") == 1:
                                    pg = 2
                                    while pg < 5: # Even lower cap for secondary seasons
                                        try:
                                            p_url = f"{NETMIRROR_MAIN_URL}/episodes.php?s={s_id}&series={content_id}&t={tm}&page={pg}"
                                            p_res = await client.get(p_url, headers=headers)
                                            pd = p_res.json()
                                            pe = pd.get("episodes", [])
                                            if not pe: break
                                            add_eps(pe)
                                            if pd.get("nextPageShow") == 0: break
                                            pg += 1
                                        except: break
                            except: pass

                        for s in data_seasons:
                            s_id = s.get("id")
                            # Skip if it's the one we already have (NetMirror usually returns latest season in post.php)
                            # But often it's not clear which one it is, so we rely on seen_eps set.
                            tasks.append(fetch_season(s_id))
                    
                    if tasks:
                        await asyncio.gather(*tasks)
                else:
                     episodes.append(Episode(
                        id=content_id,
                        title=title,
                        season=1,
                        number=1,
                        cover_image=f"https://imgcdn.kim/poster/v/{content_id}.jpg",
                        source_movie_id=content_id
                    ))

                episodes.sort(key=lambda x: (x.season, x.number))

                return MovieDetails(
                    id=content_id,
                    title=title,
                    description=desc,
                    year=year_val,
                    score=score,
                    cover_image=f"https://imgcdn.kim/poster/v/{content_id}.jpg",
                    background_image=f"https://imgcdn.kim/poster/h/{content_id}.jpg",
                    episodes=episodes,
                    seasons=seasons
                )
             
            except Exception as e:
                # print(f"[MeowVerse] Details error: {e}")
                return None
        

                

                

                    

                

                





    # --- Backend Extraction Logic (VidLink) ---

    async def fetch_stream(
        self,
        movie_id: str,
        episode_id: str,
        language_id: str | int | None = None
    ) -> VideoResponse | None:
        """Resolve stream using multiple extractors (VidLink prioritized)."""
        # print(f"[CineStream] Resolving stream for ID: {episode_id}")
        
        # 1. Try NetMirror first (Very fast, doesn't need TMDB ID)
        # print(f"[CineStream] Trying NetMirror for content ID: {movie_id}")
        netmirror_stream = await self._extract_netmirror(movie_id, episode_id)
        if netmirror_stream:
            return netmirror_stream

        # 2. Fetch details ONLY if NetMirror fails (needed for other extractors)
        details = await self.fetch_details(movie_id, include_episodes=False)
        title = details.title if details else None
        year = details.year if details else None
        
        # Parse TMDB ID (if needed for secondary extractors)
        is_movie = (movie_id == episode_id)
        meta_type = "movie" if is_movie else "series"
        tmdb_id = None

        if details:
            async with httpx.AsyncClient(timeout=30) as client:
                try:
                    types_to_check = ["series", "movie"] if not is_movie else ["movie", "series"]
                    for t in types_to_check:
                        url = f"{CINEMETA_URL}/meta/{t}/{movie_id}.json"
                        res = await client.get(url)
                        if res.status_code == 200:
                            data = res.json().get("meta")
                            if data:
                                tmdb_id = data.get("moviedb_id")
                                if tmdb_id: 
                                    meta_type = t
                                    break
                    
                    # print(f"[CineStream] Resolved TMDB ID: {tmdb_id}")
                except Exception as e:
                    pass # print(f"[CineStream] Cinemeta error: {e}")

                # Determine Season/Episode
                season = 1
                episode = 1
                if meta_type == "series":
                    if ":" in episode_id:
                        parts = episode_id.split(":")
                        if len(parts) >= 3:
                            try:
                                season = int(parts[1])
                                episode = int(parts[2])
                            except: pass

                # --- 2. VegaMovies (Secondary - Dual Audio) ---
                # print(f"[CineStream] Trying VegaMovies for: {title}")
                vega_stream = await self._extract_vegamovies(title, season if meta_type == "series" else None, episode if meta_type == "series" else None)
                if vega_stream:
                    return vega_stream
                
        return None

    async def _netmirror_bypass(self) -> str:
        """Bypass to get t_hash_t cookie from NetMirror."""
        global _netmirror_cookie, _netmirror_cache_time
        import time
        
        # Return cached cookie if valid
        current_time = time.time() * 1000  # Convert to ms
        if _netmirror_cookie and (current_time - _netmirror_cache_time) < _NETMIRROR_CACHE_DURATION:
            return _netmirror_cookie
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            retries = 0
            max_retries = 10
            
            # print("[NetMirror] Starting bypass...")
            
            while retries < max_retries:
                try:
                    res = await client.post(f"{NETMIRROR_MAIN_URL}/tv/p.php", headers=headers)
                    verify_check = res.text
                    
                    if '"r":"n"' in verify_check:
                        # Extract t_hash_t from cookies
                        cookies = res.cookies
                        if "t_hash_t" in cookies:
                            _netmirror_cookie = cookies["t_hash_t"]
                            _netmirror_cache_time = current_time
                            # print("[NetMirror] Bypass successful!")
                            return _netmirror_cookie
                except Exception as e:
                    pass # print(f"[NetMirror] Bypass attempt error: {e}")
                
                retries += 1
                await asyncio.sleep(0.5)
            
            raise Exception("NetMirror bypass failed after max retries")

    async def _extract_netmirror(
        self,
        movie_id: str,
        episode_id: str,
        audio_lang: str | None = None
    ) -> VideoResponse | None:
        """Extract stream from NetMirror (Netflix Mirror) using bypass."""
        import time
        
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                # Get bypass cookie
                cookie_value = await self._netmirror_bypass()
                tm = int(time.time())
                
                cookies = {
                    "t_hash_t": cookie_value,
                    "ott": "nf",
                    "hd": "on",
                    "user_token": "233123f803cf02184bf6c67e149cdd50"
                }
                
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"{NETMIRROR_NEW_URL}/home"
                }
                
                # Try net51.cc first
                playlist_url = f"{NETMIRROR_NEW_URL}/tv/playlist.php?id={episode_id}&t={audio_lang or ''}&tm={tm}"
                # print(f"[NetMirror] Fetching playlist: {playlist_url}")
                
                res_text = ""
                playlist_base_url = NETMIRROR_NEW_URL
                
                try:
                    res = await client.get(playlist_url, headers=headers, cookies=cookies)
                    res_text = res.text
                except Exception as e:
                    pass # print(f"[NetMirror] Playlist fetch error: {e}")
                
                # Fallback to net20.cc if needed
                if not res_text or "Video ID not found" in res_text:
                    # print("[NetMirror] Trying fallback to net20.cc...")
                    fallback_url = f"{NETMIRROR_MAIN_URL}/tv/playlist.php?id={episode_id}&t={audio_lang or ''}&tm={tm}"
                    headers["Referer"] = f"{NETMIRROR_MAIN_URL}/home"
                    
                    try:
                        res = await client.get(fallback_url, headers=headers, cookies=cookies)
                        res_text = res.text
                        playlist_base_url = NETMIRROR_MAIN_URL
                    except Exception as e:
                        # print(f"[NetMirror] Fallback fetch error: {e}")
                        return None
                
                try:
                    playlist = res.json()
                except:
                    # print(f"[NetMirror] Failed to parse playlist JSON: {res_text[:200]}")
                    return None
                
                if playlist and len(playlist) > 0:
                    item = playlist[0]
                    sources = item.get("sources", [])
                    tracks = item.get("tracks", [])
                    
                    if sources:
                        default_source = sources[0]
                        source_file = str(default_source.get("file", ""))
                        
                        if source_file.startswith("http"):
                            m3u8_url = source_file
                        else:
                            m3u8_url = f"{playlist_base_url}{source_file.replace('/tv/', '/')}"
                        
                        # print(f"[NetMirror] Found stream: {m3u8_url}")
                        
                        # Process subtitles
                        subtitles = []
                        for t in tracks:
                            kind = str(t.get("kind", "")).lower()
                            if "thumb" in kind:
                                continue
                            if "caption" in kind or "sub" in kind:
                                label = str(t.get("label") or "Subtitles")
                                # User requested: only load english one
                                if "english" not in label.lower():
                                    continue
                                    
                                raw_file = str(t.get("file", ""))
                                sub_url = raw_file
                                if sub_url.startswith("//"):
                                    sub_url = f"https:{sub_url}"
                                elif sub_url and not sub_url.startswith("http"):
                                    sub_url = f"{playlist_base_url}{sub_url}"
                                
                                if sub_url:
                                    subtitles.append(Subtitle(
                                        language=t.get("srclang") or t.get("lang") or "en",
                                        label=label,
                                        url=sub_url
                                    ))
                        
                        # Process qualities
                        qualities = []
                        for s in sources:
                            file_url = str(s.get("file", ""))
                            if file_url.startswith("http"):
                                abs_url = file_url
                            else:
                                abs_url = f"{playlist_base_url}{file_url.replace('/tv/', '/')}"
                            
                            qualities.append(Quality(
                                quality=s.get("label") or "Auto",
                                url=abs_url
                            ))
                        
                        return VideoResponse(
                            video_url=m3u8_url,
                            subtitles=subtitles,
                            qualities=qualities,
                            headers={
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                                "Referer": f"{playlist_base_url}/",
                                "Cookie": f"t_hash_t={cookie_value}; ott=nf; hd=on; user_token=233123f803cf02184bf6c67e149cdd50"
                            }
                        )
                
                return None
                
            except Exception as e:
                # print(f"[NetMirror] Error: {e}")
                return None

    async def _extract_vidlink(
        self,
        tmdb_id: int,
        season: int | None = None,
        episode: int | None = None
    ) -> VideoResponse | None:
        """Internal VidLink extraction."""
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                # Constants
                ENC_API = "https://enc-dec.app/api"
                VIDLINK_API = "https://vidlink.pro"
                
                # 1. Encrypt
                enc_url = f"{ENC_API}/enc-vidlink?text={tmdb_id}"
                enc_res = await client.get(enc_url)
                enc_text = enc_res.json().get("result")
                if not enc_text:
                    # print("[VidLink] Encryption failed")
                    return None
                
                # 2. VidLink API keys
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Connection": "keep-alive",
                    "Referer": f"{VIDLINK_API}/",
                    "Origin": f"{VIDLINK_API}/",
                }
                
                if season is None:
                    api_url = f"{VIDLINK_API}/api/b/movie/{enc_text}"
                else:
                    api_url = f"{VIDLINK_API}/api/b/tv/{enc_text}/{season}/{episode}"
                
                # print(f"[VidLink] Requesting stream from: {VIDLINK_API}")
                res = await client.get(api_url, headers=headers)
                data = res.json()
                
                stream = data.get("stream")
                if not stream:
                    # print("[VidLink] No stream found in response")
                    return None
                    
                playlist_url = stream.get("playlist")
                if not playlist_url:
                    # print("[VidLink] No playlist URL found")
                    return None
                
                # print(f"[VidLink] Found playlist: {playlist_url}")
                
                # Subtitles??
                # VidLink doesn't return separate subtitles list easily in this endpoint usually, 
                # but sometimes they are in the M3U8 or sidecar. 
                # Data might have tracks?
                # Test response had "language": "Spanish" ? Maybe tracks are elsewhere?
                # We'll skip for now or assume they are embedded in HLS.

                return VideoResponse(
                    video_url=playlist_url,
                    subtitles=[],
                    qualities=[Quality(quality="Auto", url=playlist_url)],
                    headers={
                        "User-Agent": headers["User-Agent"],
                        "Referer": headers["Referer"],
                        "Origin": headers["Origin"],
                    }
                )

            except Exception as e:
                # print(f"[VidLink] Extraction error: {e}")
                return None

    _config_cache = {}

    @classmethod
    async def _fetch_dynamic_url(cls, key: str) -> str | None:
        """Fetch dynamic API URL from remote config."""
        if key in cls._config_cache: return cls._config_cache[key]
        
        try:
             async with httpx.AsyncClient(timeout=10) as client:
                 res = await client.get("https://raw.githubusercontent.com/SaurabhKaperwan/Utils/refs/heads/main/urls.json")
                 data = res.json()
                 cls._config_cache = data
                 return data.get(key)
        except Exception as e:
            # print(f"[CineStream] Dynamic config fetch failed: {e}")
            return None


    async def _extract_hexa(
        self,
        tmdb_id: int,
        season: int | None = None,
        episode: int | None = None
    ) -> VideoResponse | None:
        """Internal Hexa extraction."""
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                HEXA_API = "https://themoviedb.hexa.su"
                MULTI_DECRYPT_API = "https://enc-dec.app/api"
                
                # 1. Generate Key
                key = secrets.token_hex(32)
                
                # 2. Construct URL
                if season is None:
                    url = f"{HEXA_API}/api/tmdb/movie/{tmdb_id}/images"
                else:
                    url = f"{HEXA_API}/api/tmdb/tv/{tmdb_id}/season/{season}/episode/{episode}/images"
                
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "plain/text",
                    "X-Api-Key": key
                }
                
                # 3. Fetch Encrypted Data
                # print(f"[Hexa] Fetching from: {url}")
                res = await client.get(url, headers=headers)
                if res.status_code != 200:
                    # print(f"[Hexa] Error fetching data: {res.status_code}")
                    return None
                    
                enc_data = res.text
                
                # 4. Decrypt
                dec_url = f"{MULTI_DECRYPT_API}/dec-hexa"
                payload = {
                    "text": enc_data,
                    "key": key
                }
                
                res = await client.post(dec_url, json=payload, headers={"Content-Type": "application/json"})
                if res.status_code != 200:
                    # print(f"[Hexa] Decryption failed: {res.status_code}")
                    return None
                    
                data = res.json()
                result = data.get("result", {})
                sources = result.get("sources", [])
                
                if not sources:
                    # print("[Hexa] No sources found.")
                    return None
                    
                # Return first source (usually 'alpha' or similar)
                first_src = sources[0]
                stream_url = first_src.get("url")
                server = first_src.get("server")
                # print(f"[Hexa] Found stream on server: {server}")
                
                return VideoResponse(
                    video_url=stream_url,
                    qualities=[Quality(quality="Auto", url=stream_url)],
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Origin": "https://hexa.su", 
                        "Referer": "https://hexa.su/"
                    },
                    force_seekable=True 
                )

            except Exception as e:
                # print(f"[Hexa] Error: {e}")
                return None

    async def _extract_hdmovie2(
        self,
        title: str,
        year: int | None = None,
        season: int | None = None,
        episode: int | None = None
    ) -> VideoResponse | None:
        """Internal Hdmovie2 extraction."""
        # print(f"[Hdmovie2] Searching for: {title}")
        base_url = await self._fetch_dynamic_url("hdmovie2") or "https://hdmovie2.kiwi"
            
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            try:
                # 1. Search
                # Sanitize title: keep alphanumeric, spaces, hyphens. Remove colons/etc.
                safe_title = re.sub(r'[^\w\s-]', ' ', title)
                safe_title = re.sub(r'\s+', ' ', safe_title).strip()
                search_query = safe_title.replace(" ", "+")
                search_url = f"{base_url}/?s={search_query}"
                # print(f"[Hdmovie2] Search URL: {search_url}")

                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                
                res = await client.get(search_url, headers=headers)
                soup = BeautifulSoup(res.text, 'html.parser')
                
                # 2. Find Page
                # Restrict to content area to avoid sidebar/similar-posts
                main_content = soup.select_one("div.content") or soup
                
                candidates = []
                for a in main_content.find_all('a', href=True):
                    href = a['href']
                    if "/movies/" in href or "/web-series/" in href:
                        candidates.append(href)

                if not candidates:
                    # print("[Hdmovie2] No search results found.")
                    return None
                
                # Naive selection: First result or try to match title/year
                page_url = candidates[0]
                # print(f"[Hdmovie2] Selected Page: {page_url}")

                res = await client.get(page_url, headers=headers)
                soup = BeautifulSoup(res.text, 'html.parser')

                # 3. Handle Series Navigation (if needed)
                if season is not None and episode is not None:
                     # This logic assumes we landed on a series page or main page
                     # If main page, look for season/episode links?
                     # Debug script was movie-focused.
                     # For now, implementing basic movie/direct player logic.
                     # TODO: Add specific series logic if this fails for shows.
                     pass

                # 4. Parse Player Options (ul#playeroptionsul)
                options = soup.select("ul#playeroptionsul li")
                # print(f"[Hdmovie2] Found {len(options)} options")
                
                target_li = None
                # Priority: "Ultra Stream" or "Super Player" or "Fast Player"
                for li in options:
                    text = li.get_text().strip().lower()
                    if "v2" in text or "ultra" in text or "super" in text:
                        target_li = li
                        break
                
                if not target_li and options:
                    target_li = options[0]
                    
                if not target_li:
                    # print("[Hdmovie2] No player options.")
                    return None

                post_id = target_li.get("data-post")
                nume = target_li.get("data-nume")
                p_type = target_li.get("data-type")
                
                # 5. AJAX Request
                ajax_url = f"{base_url}/wp-admin/admin-ajax.php"
                payload = {
                    "action": "doo_player_ajax",
                    "post": post_id,
                    "nume": nume,
                    "type": p_type
                }
                
                headers["X-Requested-With"] = "XMLHttpRequest"
                headers["Referer"] = page_url
                
                res = await client.post(ajax_url, data=payload, headers=headers)
                data = res.json()
                embed_url = data.get("embed_url") # or embed_url
                
                final_url = embed_url
                if "<iframe" in embed_url:
                     iframe_soup = BeautifulSoup(embed_url, 'html.parser')
                     src = iframe_soup.select_one("iframe")
                     if src:
                        final_url = src['src']
                
                print(f"[Hdmovie2] Resolved Stream: {final_url}")
                
                return VideoResponse(
                    video_url=final_url,
                    qualities=[Quality(quality="Auto", url=final_url)],
                    headers={
                        "User-Agent": headers["User-Agent"],
                        "Referer": page_url # Or iframe domain
                    },
                    force_seekable=True
                )

            except Exception as e:
                # print(f"[Hdmovie2] Error: {e}")
                return None
    
    async def _extract_vegamovies(
        self,
        title: str,
        season: int | None = None,
        episode: int | None = None
    ) -> VideoResponse | None:
        """Internal VegaMovies extraction."""
        # print(f"[VegaMovies] Searching for: {title}")
        
        # Dynamic base URL
        base_url = await self._fetch_dynamic_url("vegamovies") or "https://vegamovies.gt"
            
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            try:
                # 1. Search
                query = title
                if season:
                    query += f" Season {season}"
                
                # Basic sanitation
                query = re.sub(r'[^\w\s-]', ' ', query).strip()
                search_query = query.replace(" ", "+")
                
                search_url = f"{base_url}/?s={search_query}"
                # print(f"[VegaMovies] Search URL: {search_url}")

                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                
                res = await client.get(search_url, headers=headers)
                if res.status_code != 200: return None
                soup = BeautifulSoup(res.text, 'html.parser')
                
                # 2. Select Page
                # Find first article entry
                first_match = soup.select_one("article.entry > h2 > a") or soup.select_one("article.entry > a")
                if not first_match:
                     # print("[VegaMovies] No search results found.")
                     return None
                     
                page_url = first_match['href']
                # print(f"[VegaMovies] Selected Page: {page_url}")

                res = await client.get(page_url, headers=headers)
                soup = BeautifulSoup(res.text, 'html.parser')

                # 3. Extract Links
                content_div = soup.select_one("div.entry-content")
                if not content_div: return None

                # Find all potential links (NexDrive / FastDL / V-Cloud)
                candidates = []
                for a in content_div.find_all('a', href=True):
                    href = a['href']
                    text = a.get_text(strip=True).lower()
                    
                    # Basic filters(NexDrive / FastDL / V-Cloud / Download)
                    if "nexdrive" in href or "fastdl" in href or "vcloud" in href or "v-cloud" in text or "fastdl" in text or "download" in text:
                         # For series, filter by "Episode" if possible?
                         if season and episode:
                             # Try to match episode number in text (e.g. "Episode 5", "E05", "Ep 5")
                             if f"episode {episode}" in text or f"ep{episode}" in text or f"e{episode}" in text:
                                  candidates.insert(0, (text, href)) # High priority
                             else:
                                  candidates.append((text, href))
                         else:
                             # Movie - prefer higher res?
                             prio = 0
                             if "1080p" in text: prio = 2
                             elif "720p" in text: prio = 1
                             
                             candidates.append((prio, text, href))
                
                if not candidates:
                    # print("[VegaMovies] No links found.")
                    return None

                target_url = None
                
                if season and episode:
                    target_url = candidates[0][1] if isinstance(candidates[0], tuple) else candidates[0][2]
                else:
                    candidates.sort(key=lambda x: x[0], reverse=True)
                    target_url = candidates[0][2]
                
                # print(f"[VegaMovies] Processing: {target_url}")

                # 4. Resolve NexDrive / Check Direct
                final_url = None
                
                if "nexdrive" in target_url:
                     # print("[VegaMovies] Following NexDrive...")
                     res2 = await client.get(target_url, headers=headers)
                     soup2 = BeautifulSoup(res2.text, 'html.parser')
                     
                     # Find FastDL / V-Cloud. Prioritize FastDL.
                     fastdl = soup2.select_one("a[href*='fastdl']") or soup2.select_one("a[href*='G-Direct']")
                     vcloud = soup2.select_one("a[href*='vcloud']") or soup2.select_one("a[href*='linkda']")
                     
                     btn = fastdl or vcloud
                     if btn:
                         final_url = btn['href']
                         
                         # Resolve FastDL if selected (it often redirects to dl.php?link=...)
                         if "fastdl" in final_url or "filebee" in final_url:
                             # print(f"[VegaMovies] Resolving FastDL: {final_url}")
                             try:
                                 res_dl = await client.get(final_url, follow_redirects=True)
                                 # Check URL for dl.php?link=...
                                 import urllib.parse
                                 if "dl.php" in str(res_dl.url) and "link=" in str(res_dl.url):
                                     parsed = urllib.parse.urlparse(str(res_dl.url))
                                     real_link = urllib.parse.parse_qs(parsed.query).get('link', [None])[0]
                                     if real_link:
                                         final_url = real_link
                                         # print(f"[VegaMovies] Resolved to Direct Link: {final_url}")
                             except Exception as dl_e:
                                 pass # print(f"[VegaMovies] FastDL resolution error: {dl_e}")
                else:
                    final_url = target_url
                
                if not final_url: return None
                
                # print(f"[VegaMovies] Final URL: {final_url}")
                
                return VideoResponse(
                    video_url=final_url,
                    qualities=[Quality(quality="Auto", url=final_url)],
                    headers=headers,
                    force_seekable=True
                )

            except Exception as e:
                # print(f"[VegaMovies] Error: {e}")
                return None
