"""MeowVerse (CNC Verse) provider - ported from meowverse.ts."""

import asyncio
import re
import time
from typing import Any

import httpx
from bs4 import BeautifulSoup

from meowtv.models import (
    ContentItem, Episode, HomeRow, MovieDetails,
    Quality, Season, Subtitle, Track, VideoResponse, RelatedItem
)
from meowtv.providers.base import Provider
from meowtv.providers import proxy as proxy_utils
from meowtv.providers.proxy import get_hls_proxy_url, get_simple_proxy_url

MAIN_URL = "https://net20.cc"
NEW_URL = "https://net51.cc"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
}

# Cached cookies
_cached_direct_cookie: str | None = None
_cached_proxy_cookie: str | None = None
_cache_direct_timestamp: float = 0
_cache_proxy_timestamp: float = 0
CACHE_DURATION = 54_000  # 15 hours in seconds


async def _proxied_fetch(
    client: httpx.AsyncClient,
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    data: dict | str | None = None,
    follow_redirects: bool = True,
) -> httpx.Response:
    """Fetch via proxy if configured."""
    if not proxy_utils.PROXY_WORKER_URL:
        if method == "POST":
            return await client.post(url, headers=headers, data=data, follow_redirects=follow_redirects)
        return await client.get(url, headers=headers, follow_redirects=follow_redirects)

    # Extract special headers
    h = dict(headers) if headers else {}
    cookie = h.pop("Cookie", h.pop("cookie", None))
    referer = h.pop("Referer", h.pop("referer", None))

    params: dict[str, str] = {"ua": HEADERS["User-Agent"]}
    if cookie:
        params["cookie"] = cookie
    if referer:
        params["referer"] = referer
    if not follow_redirects:
        params["redirect"] = "manual"

    proxy_url = get_simple_proxy_url(url, params)

    if method == "POST":
        return await client.post(proxy_url, headers=h, data=data, follow_redirects=follow_redirects)
    return await client.get(proxy_url, headers=h, follow_redirects=follow_redirects)


async def _bypass(client: httpx.AsyncClient, main_url: str, use_proxy: bool = False) -> str:
    """Bypass cookie protection."""
    global _cached_direct_cookie, _cached_proxy_cookie
    global _cache_direct_timestamp, _cache_proxy_timestamp

    cached_cookie = _cached_proxy_cookie if use_proxy else _cached_direct_cookie
    timestamp = _cache_proxy_timestamp if use_proxy else _cache_direct_timestamp

    if cached_cookie and (time.time() - timestamp) < CACHE_DURATION:
        return cached_cookie

    max_retries = 10
    for attempt in range(max_retries):
        try:
            if use_proxy:
                res = await _proxied_fetch(client, f"{main_url}/tv/p.php", method="POST", headers=HEADERS)
            else:
                res = await client.post(f"{main_url}/tv/p.php", headers=HEADERS)

            text = res.text
            if '"r":"n"' in text:
                # Extract cookie from response
                set_cookie = res.headers.get("x-proxied-set-cookie") or res.headers.get("set-cookie", "")
                match = re.search(r't_hash_t=([^;]+)', set_cookie)
                if match:
                    cookie_val = match.group(1)
                    if use_proxy:
                        _cached_proxy_cookie = cookie_val
                        _cache_proxy_timestamp = time.time()
                    else:
                        _cached_direct_cookie = cookie_val
                        _cache_direct_timestamp = time.time()
                    return cookie_val

            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"[MeowVerse] Bypass attempt {attempt + 1} failed: {e}")
            await asyncio.sleep(0.5)

    raise Exception("Bypass failed after max retries")


def _merge_cookies(old_cookies: str, new_set_cookie: str | None) -> str:
    """Merge cookies from Set-Cookie header."""
    if not new_set_cookie:
        return old_cookies

    cookie_map: dict[str, str] = {}
    for c in old_cookies.split(";"):
        if "=" in c:
            key, val = c.strip().split("=", 1)
            cookie_map[key] = val

    # Parse Set-Cookie
    parts = re.split(r',(?=\s*[a-zA-Z0-9_-]+=)', new_set_cookie)
    for part in parts:
        main_part = part.split(";")[0].strip()
        if "=" in main_part:
            key, val = main_part.split("=", 1)
            cookie_map[key] = val

    return "; ".join(f"{k}={v}" for k, v in cookie_map.items())


class MeowVerseProvider(Provider):
    """MeowVerse (CNC Verse) content provider."""

    @property
    def name(self) -> str:
        return "MeowVerse (Under Development)"

    async def fetch_home(self, page: int = 1) -> list[HomeRow]:
        """Fetch home page content."""
        if page > 1:
            return []

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                cookie_value = await _bypass(client, MAIN_URL, use_proxy=False)
                headers = {
                    **HEADERS,
                    "Cookie": f"t_hash_t={cookie_value}; ott=nf; hd=on; user_token=233123f803cf02184bf6c67e149cdd50"
                }

                res = await client.get(f"{MAIN_URL}/home", headers=headers)
                soup = BeautifulSoup(res.text, "html.parser")
                rows: list[HomeRow] = []

                for elem in soup.select(".lolomoRow"):
                    name_elem = elem.select_one("h2 > span > div")
                    name = name_elem.get_text(strip=True) if name_elem else ""
                    contents: list[ContentItem] = []

                    for img in elem.select("img.lazy"):
                        src = img.get("data-src", "")
                        if src:
                            parts = src.split("/")
                            if parts:
                                content_id = parts[-1].split(".")[0]
                                if content_id:
                                    contents.append(ContentItem(
                                        id=content_id,
                                        title="",
                                        cover_image=f"https://imgcdn.kim/poster/v/{content_id}.jpg",
                                        type="movie"
                                    ))

                    if contents:
                        rows.append(HomeRow(name=name, contents=contents))

                return rows
            except Exception as e:
                print(f"[MeowVerse] Home error: {e}")
                return []

    async def search(self, query: str) -> list[ContentItem]:
        """Search for content."""
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                cookie_value = await _bypass(client, MAIN_URL, use_proxy=False)
                timestamp = int(time.time())
                url = f"{MAIN_URL}/search.php?s={query}&t={timestamp}"

                headers = {
                    **HEADERS,
                    "Cookie": f"t_hash_t={cookie_value}; ott=nf; hd=on",
                    "Referer": f"{MAIN_URL}/tv/home"
                }

                res = await client.get(url, headers=headers)
                data = res.json()

                results: list[ContentItem] = []
                for item in data.get("searchResult", []):
                    results.append(ContentItem(
                        id=item.get("id", ""),
                        title=item.get("t", ""),
                        cover_image=f"https://imgcdn.kim/poster/v/{item.get('id', '')}.jpg",
                        type="movie"
                    ))

                return results
            except Exception as e:
                print(f"[MeowVerse] Search error: {e}")
                return []

    async def _fetch_all_pages(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        headers: dict,
        content_id: str,
        audio_tracks: list[Track]
    ) -> list[Episode]:
        """Fetch all pages of episodes."""
        all_episodes: list[Episode] = []
        current_page = 1
        has_more = True

        while has_more and current_page <= 100:
            try:
                url = base_url if current_page == 1 else f"{base_url}&page={current_page}"
                res = await client.get(url, headers=headers)
                data = res.json()

                episodes = data.get("episodes", [])
                if not episodes:
                    break

                # Check for duplicates to prevent infinite loops
                new_episodes_count = 0
                for ep in episodes:
                    if ep:
                        ep_id = ep.get("id", "")
                        # Check if already added
                        if any(e.id == ep_id for e in all_episodes):
                            continue
                            
                        season_str = ep.get("s", "S1").replace("S", "")
                        ep_str = ep.get("ep", "E1").replace("E", "")
                        all_episodes.append(Episode(
                            id=ep_id,
                            title=ep.get("t", ""),
                            season=int(season_str) if season_str.isdigit() else 1,
                            number=int(ep_str) if ep_str.isdigit() else 1,
                            cover_image=f"https://imgcdn.kim/epimg/150/{ep_id}.jpg",
                            source_movie_id=content_id,
                            tracks=audio_tracks
                        ))
                        new_episodes_count += 1
                
                if new_episodes_count == 0:
                    has_more = False
                    break

                # Check pagination
                next_page_show = data.get("nextPageShow")
                if next_page_show == 0 or next_page_show == "0":
                    has_more = False
                elif len(episodes) < 10:
                    has_more = False
                else:
                    current_page += 1

            except Exception as e:
                print(f"[MeowVerse] Page {current_page} error: {e}")
                break

        return all_episodes

    async def fetch_details(self, content_id: str, include_episodes: bool = True) -> MovieDetails | None:
        """Fetch content details."""
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                cookie_value = await _bypass(client, MAIN_URL, use_proxy=False)
                timestamp = int(time.time())
                url = f"{MAIN_URL}/post.php?id={content_id}&t={timestamp}"

                headers = {
                    **HEADERS,
                    "Cookie": f"t_hash_t={cookie_value}; ott=nf; hd=on",
                    "Referer": f"{MAIN_URL}/tv/home"
                }

                res = await client.get(url, headers=headers)
                data = res.json()

                # Parse audio tracks
                audio_tracks: list[Track] = [Track(name="Default", language_id=None, is_default=True)]
                for entry in data.get("lang", []):
                    code = str(entry.get("s", "")).strip()
                    label = str(entry.get("l", "")).strip()
                    if code and code.lower() != "und":
                        audio_tracks.append(Track(
                            name=label or code,
                            language_id=hash(code),  # Use hash as language_id
                            is_default=False
                        ))

                episodes: list[Episode] = []
                if include_episodes:
                    is_movie = data.get("type") in ("m", "movie")
                    if not is_movie and data.get("episodes") and data["episodes"]:
                        # Fetch current season
                        base_url = f"{MAIN_URL}/post.php?id={content_id}&t={timestamp}"
                        episodes = await self._fetch_all_pages(client, base_url, headers, content_id, audio_tracks)

                        # Fetch additional seasons
                        seasons = data.get("season", [])
                        if len(seasons) > 1:
                            for season in seasons[:-1]:  # Skip last (already fetched)
                                season_url = f"{MAIN_URL}/episodes.php?s={season.get('id')}&series={content_id}&t={timestamp}"
                                season_episodes = await self._fetch_all_pages(
                                    client, season_url, headers, content_id, audio_tracks
                                )
                                episodes.extend(season_episodes)
                    else:
                        # Single movie/episode
                        episodes.append(Episode(
                            id=content_id,
                            title=data.get("title", ""),
                            number=1,
                            season=1,
                            source_movie_id=content_id,
                            tracks=audio_tracks
                        ))

                    episodes.sort(key=lambda e: (e.season, e.number))

                # Parse seasons
                seasons: list[Season] = []
                for s in data.get("season", []):
                    seasons.append(Season(
                        id=str(s.get("id", "")),
                        number=int(s.get("id", 1)),
                        name=f"Season {s.get('id', 1)}"
                    ))

                # Parse related content
                related: list[RelatedItem] = []
                for item in data.get("suggest", []):
                    related.append(RelatedItem(
                        id=item.get("id", ""),
                        title=item.get("t", item.get("title", "")),
                        image=f"https://imgcdn.kim/poster/v/{item.get('id', '')}.jpg",
                        type="show",
                        year=int(item.get("year")) if item.get("year") else None
                    ))

                score_str = data.get("match", "0").replace("IMDb ", "")
                try:
                    score = float(score_str)
                except ValueError:
                    score = 0.0

                return MovieDetails(
                    id=content_id,
                    title=data.get("title", ""),
                    description=data.get("desc"),
                    cover_image=f"https://imgcdn.kim/poster/v/{content_id}.jpg",
                    background_image=f"https://imgcdn.kim/poster/h/{content_id}.jpg",
                    year=int(data.get("year")) if data.get("year") else None,
                    score=score,
                    episodes=episodes,
                    seasons=seasons,
                    related_content=related
                )

            except Exception as e:
                print(f"[MeowVerse] Details error: {e}")
                return None

    async def fetch_stream(
        self,
        movie_id: str,
        episode_id: str,
        language_id: str | int | None = None
    ) -> VideoResponse | None:
        """Fetch stream URL for playback."""
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                cookie_value = await _bypass(client, MAIN_URL, use_proxy=True)
                timestamp = int(time.time())
                audio_param = str(language_id) if language_id else ""

                # Initial cookies
                stream_cookies = f"t_hash_t={cookie_value}; ott=nf; hd=on; user_token=233123f803cf02184bf6c67e149cdd50"
                referer_net20 = f"{MAIN_URL}/home"

                # Step 1: Language selection (if specified)
                if audio_param:
                    try:
                        lang_res = await _proxied_fetch(
                            client,
                            f"{MAIN_URL}/language.php",
                            method="POST",
                            headers={
                                **HEADERS,
                                "Cookie": stream_cookies,
                                "Content-Type": "application/x-www-form-urlencoded",
                                "Referer": referer_net20
                            },
                            data=f"lang={audio_param}"
                        )
                        new_cookie = lang_res.headers.get("x-proxied-set-cookie") or lang_res.headers.get("set-cookie")
                        stream_cookies = _merge_cookies(stream_cookies, new_cookie)
                    except Exception as e:
                        print(f"[MeowVerse] Language POST failed: {e}")

                # Step 2: Get transfer hash
                hash_params = ""
                try:
                    play_res = await _proxied_fetch(
                        client,
                        f"{MAIN_URL}/play.php",
                        method="POST",
                        headers={
                            **HEADERS,
                            "Cookie": stream_cookies,
                            "Content-Type": "application/x-www-form-urlencoded",
                            "Referer": referer_net20,
                        },
                        data=f"id={episode_id}"
                    )
                    new_cookie = play_res.headers.get("x-proxied-set-cookie") or play_res.headers.get("set-cookie")
                    stream_cookies = _merge_cookies(stream_cookies, new_cookie)

                    try:
                        play_data = play_res.json()
                        if play_data.get("h"):
                            hash_params = f"&{play_data['h']}"
                    except:
                        pass
                except Exception as e:
                    print(f"[MeowVerse] Play POST failed: {e}")

                # Step 3: Transfer session to net51
                if hash_params:
                    try:
                        await _proxied_fetch(
                            client,
                            f"{NEW_URL}/play.php?id={episode_id}{hash_params}",
                            headers={
                                **HEADERS,
                                "Cookie": stream_cookies,
                                "Referer": referer_net20
                            },
                            follow_redirects=False
                        )
                    except Exception as e:
                        print(f"[MeowVerse] Session transfer failed: {e}")

                # Step 4: Fetch playlist
                playlist_url = f"{NEW_URL}/tv/playlist.php?id={episode_id}&t={audio_param}&tm={timestamp}"
                playlist_base_url = NEW_URL
                playlist_referer = f"{NEW_URL}/"

                res_text = ""
                try:
                    playlist_res = await _proxied_fetch(
                        client,
                        playlist_url,
                        headers={
                            **HEADERS,
                            "Cookie": stream_cookies,
                            "Referer": f"{NEW_URL}/home"
                        }
                    )
                    res_text = playlist_res.text
                    new_cookie = playlist_res.headers.get("x-proxied-set-cookie") or playlist_res.headers.get("set-cookie")
                    stream_cookies = _merge_cookies(stream_cookies, new_cookie)
                except Exception as e:
                    print(f"[MeowVerse] Playlist fetch error: {e}")

                # Fallback to net20 if needed
                if not res_text or "Video ID not found" in res_text:
                    try:
                        fallback_url = f"{MAIN_URL}/tv/playlist.php?id={episode_id}&t={audio_param}&tm={timestamp}"
                        fallback_res = await _proxied_fetch(
                            client,
                            fallback_url,
                            headers={
                                **HEADERS,
                                "Cookie": stream_cookies,
                                "Referer": referer_net20
                            }
                        )
                        res_text = fallback_res.text
                        playlist_base_url = MAIN_URL
                        playlist_referer = f"{MAIN_URL}/"
                    except Exception as e:
                        print(f"[MeowVerse] Fallback playlist error: {e}")

                try:
                    import json
                    playlist = json.loads(res_text)
                except:
                    print(f"[MeowVerse] Failed to parse playlist JSON")
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

                        # For CLI, we can use direct URLs or proxied (get_hls_proxy_url checks config)
                        # We force proxy usage if PROXY_WORKER_URL is set in config
                        video_url = get_hls_proxy_url(m3u8_url, {
                            "referer": playlist_referer,
                            "cookie": stream_cookies,
                            "ua": HEADERS["User-Agent"]
                        }) if proxy_utils.PROXY_WORKER_URL else m3u8_url

                        # Parse subtitles
                        subtitles: list[Subtitle] = []
                        for t in tracks:
                            kind = str(t.get("kind", "")).lower()
                            file = str(t.get("file", "")).lower()

                            if "thumb" in kind:
                                continue
                            if not ("caption" in kind or "sub" in kind or file.endswith((".vtt", ".srt"))):
                                continue

                            raw_file = str(t.get("file", ""))
                            label = str(t.get("label", t.get("name", "Subtitles")))
                            lang = str(t.get("srclang", t.get("lang", "en")))

                            sub_url = raw_file
                            if sub_url.startswith("//"):
                                sub_url = f"https:{sub_url}"
                            elif sub_url and not sub_url.startswith("http"):
                                sub_url = f"{playlist_base_url}{sub_url}"

                            if sub_url:
                                subtitles.append(Subtitle(
                                    language=lang,
                                    label=label,
                                    url=sub_url
                                ))

                        # Parse qualities
                        qualities: list[Quality] = []
                        for s in sources:
                            file = str(s.get("file", ""))
                            if file.startswith("http"):
                                abs_url = file
                            else:
                                abs_url = f"{playlist_base_url}{file.replace('/tv/', '/')}"
                            qualities.append(Quality(
                                quality=s.get("label", "Auto"),
                                url=abs_url
                            ))

                        return VideoResponse(
                            video_url=video_url,
                            subtitles=subtitles,
                            qualities=qualities,
                            headers={"Cookie": stream_cookies, "Referer": playlist_referer}
                        )

                return None

            except Exception as e:
                print(f"[MeowVerse] Stream error: {e}")
                return None
