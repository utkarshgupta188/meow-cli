"""MeowTV (Castle) provider - ported from meowtv.ts."""

import json
import os
import re
from typing import Any, Optional

import httpx

from meowtv.crypto import decrypt_data
from meowtv.models import (
    ContentItem, Episode, HomeRow, MovieDetails, 
    Quality, Season, Subtitle, Track, VideoResponse
)
from meowtv.providers.base import Provider

MAIN_URL = "https://api.hlowb.com"

HEADERS = {
    "User-Agent": "okhttp/4.9.0",
}


def _quote_large_ints(text: str) -> str:
    """Wrap integers with 16+ digits in quotes to preserve precision."""
    return re.sub(r'(:\s*)(\d{16,})', r'\1"\2"', text)


def _parse_json_preserve_bigint(text: str) -> Any:
    """Parse JSON while preserving large integers as strings."""
    safe = _quote_large_ints(text)
    return json.loads(safe)


class MeowTVProvider(Provider):
    """MeowTV (Castle) content provider."""

    def __init__(self, proxy_url: Optional[str] = None):
        super().__init__(proxy_url)
        self._security_key: Optional[str] = None
        self._cookie: Optional[str] = None
        self._proxy_failed = False  # Track if proxy is consistently failing

    @property
    def name(self) -> str:
        return "MeowTV"

    async def _get_client(self) -> httpx.AsyncClient:
        """Create a client. Environment variables like HTTP_PROXY are ignored 
        to ensure we control the proxy behavior via self.proxy_url."""
        return httpx.AsyncClient(timeout=30, trust_env=False)

    async def _get_security_key(self, client: httpx.AsyncClient, retries: int = 3) -> tuple[str | None, str | None]:
        """Fetch security key with proxy fallback logic."""
        base_url = f"{MAIN_URL}/v0.1/system/getSecurityKey/1?channel=IndiaA&clientType=1&lang=en-US"
        
        # Strategies: 
        # 1. Proxied (if configured)
        # 2. Local/Direct
        strategies = []
        if self.proxy_url and not self._proxy_failed:
            strategies.append(("proxied", self.get_proxied_url(base_url)))
        strategies.append(("direct", base_url))

        for strategy_name, url in strategies:
            for attempt in range(1, retries + 1):
                try:
                    res = await client.get(url, headers=HEADERS)
                    
                    if res.status_code == 400 and strategy_name == "proxied":
                        # If proxy returns 400, it's likely the worker issue. Skip to next strategy.
                        self._proxy_failed = True
                        break
                        
                    cookie = res.headers.get("set-cookie", "")
                    text = res.text
                    
                    try:
                        data = json.loads(text)
                        if data.get("code") == 200 and data.get("data"):
                            return data["data"], cookie
                    except json.JSONDecodeError:
                        pass
                except Exception:
                    if attempt == retries:
                        continue
        
        return None, None

    async def _fetch_details_with_key(self, client: httpx.AsyncClient, content_id: str, key: str) -> Any | None:
        """Fetch details using security key."""
        raw_url = f"{MAIN_URL}/film-api/v1.9.9/movie?channel=IndiaA&clientType=1&lang=en-US&movieId={content_id}&packageName=com.external.castle"
        url = self.get_proxied_url(raw_url)
        
        try:
            res = await client.get(url)
            decrypted = decrypt_data(res.text, key)
            if not decrypted:
                return None
            return _parse_json_preserve_bigint(decrypted).get("data")
        except Exception:
            return None

    async def _request(self, client: httpx.AsyncClient, method: str, raw_url: str, key: Optional[str] = None, **kwargs) -> Any:
        """Perform request with proxy fallback."""
        strategies = []
        if self.proxy_url and not self._proxy_failed:
            strategies.append(("proxied", self.get_proxied_url(raw_url)))
        strategies.append(("direct", raw_url))

        last_exception = None
        for strategy_name, url in strategies:
            try:
                if method.upper() == "POST":
                    res = await client.post(url, **kwargs)
                else:
                    res = await client.get(url, **kwargs)
                
                if res.status_code == 400 and strategy_name == "proxied":
                    continue # Try direct
                
                text = res.text
                if not key:
                    return text
                
                decrypted = decrypt_data(text, key)
                if decrypted:
                    return decrypted
                
                # If decryption failed but we are on proxied, try direct
                if strategy_name == "proxied":
                    self._proxy_failed = True
                    continue
                
            except Exception as e:
                last_exception = e
                if strategy_name == "proxied":
                    continue
        
        if last_exception:
            raise last_exception
        return None

    async def fetch_home(self, page: int = 1) -> list[HomeRow]:
        """Fetch home page content."""
        async with await self._get_client() as client:
            key, _ = await self._get_security_key(client)
            if not key:
                return []
            
            raw_url = f"{MAIN_URL}/film-api/v0.1/category/home?channel=IndiaA&clientType=1&lang=en-US&locationId=1001&mode=1&packageName=com.external.castle&page={page}&size=17"
            
            try:
                decrypted = await self._request(client, "GET", raw_url, key=key)
                if not decrypted:
                    return []
                
                data = _parse_json_preserve_bigint(decrypted).get("data", {})
                rows_data = data.get("rows", [])
                
                rows: list[HomeRow] = []
                for row in rows_data:
                    contents: list[ContentItem] = []
                    for c in row.get("contents", []):
                        redirect_id = c.get("redirectId")
                        if redirect_id:
                            movie_type = c.get("movieType", 0)
                            content_type = "series" if movie_type in [1, 3, 5] else "movie"
                            contents.append(ContentItem(
                                id=str(redirect_id),
                                title=c.get("title", ""),
                                cover_image=c.get("coverImage", ""),
                                type=content_type
                            ))
                    
                    if contents:
                        rows.append(HomeRow(name=row.get("name", ""), contents=contents))
                
                return rows
                
            except Exception as e:
                print(f"[MeowTV] Home error: {e}")
                return []

    async def search(self, query: str) -> list[ContentItem]:
        """Search for content."""
        async with await self._get_client() as client:
            key, _ = await self._get_security_key(client)
            if not key:
                return []
            
            raw_url = f"{MAIN_URL}/film-api/v1.1.0/movie/searchByKeyword?channel=IndiaA&clientType=1&keyword={query}&lang=en-US&mode=1&packageName=com.external.castle&page=1&size=30"
            
            try:
                decrypted = await self._request(client, "GET", raw_url, key=key)
                if not decrypted:
                    return []
                
                data = _parse_json_preserve_bigint(decrypted).get("data", {})
                rows = data.get("rows", [])
                
                results: list[ContentItem] = []
                for row in rows:
                    movie_type = row.get("movieType", 0)
                    content_type = "series" if movie_type in [1, 3, 5] else "movie"
                    results.append(ContentItem(
                        id=str(row.get("id", "")),
                        title=row.get("title", ""),
                        cover_image=row.get("coverVerticalImage") or row.get("coverHorizontalImage", ""),
                        type=content_type
                    ))
                
                return results
                
            except Exception as e:
                print(f"[MeowTV] Search error: {e}")
                return []

    async def fetch_details(self, content_id: str, include_episodes: bool = True) -> MovieDetails | None:
        """Fetch content details."""
        async with await self._get_client() as client:
            key, _ = await self._get_security_key(client)
            if not key:
                return None
            
            raw_url = f"{MAIN_URL}/film-api/v1.9.9/movie?channel=IndiaA&clientType=1&lang=en-US&movieId={content_id}&packageName=com.external.castle"
            
            try:
                decrypted = await self._request(client, "GET", raw_url, key=key)
                if not decrypted:
                    return None
                
                d = _parse_json_preserve_bigint(decrypted).get("data", {})
                
                episodes: list[Episode] = []
                if include_episodes:
                    seasons_data = d.get("seasons", [])
                    
                    if len(seasons_data) > 1:
                        # Fetch episodes from each season
                        for season in seasons_data:
                            movie_id = season.get("movieId")
                            if not movie_id:
                                continue
                            
                            season_raw_url = f"{MAIN_URL}/film-api/v1.9.9/movie?channel=IndiaA&clientType=1&lang=en-US&movieId={movie_id}&packageName=com.external.castle"
                            season_decrypted = await self._request(client, "GET", season_raw_url, key=key)
                            if not season_decrypted:
                                continue
                            
                            season_data = _parse_json_preserve_bigint(season_decrypted).get("data", {})
                            if not season_data:
                                continue
                            
                            for ep in season_data.get("episodes", []):
                                tracks = [
                                    Track(
                                        language_id=t.get("languageId"),
                                        name=t.get("languageName") or t.get("abbreviate", ""),
                                        is_default=t.get("isDefault", False)
                                    )
                                    for t in ep.get("tracks", [])
                                ]
                                
                                episodes.append(Episode(
                                    id=str(ep.get("id", "")),
                                    title=ep.get("title", ""),
                                    number=ep.get("number", 1),
                                    season=season.get("number", 1),
                                    cover_image=ep.get("coverImage"),
                                    source_movie_id=str(movie_id),
                                    tracks=tracks
                                ))
                    elif d.get("episodes"):
                        # Single season
                        season_number = d.get("seasonNumber", 1)
                        for ep in d.get("episodes", []):
                            tracks = [
                                Track(
                                    language_id=t.get("languageId"),
                                    name=t.get("languageName") or t.get("abbreviate", ""),
                                    is_default=t.get("isDefault", False)
                                )
                                for t in ep.get("tracks", [])
                            ]
                            
                            episodes.append(Episode(
                                id=str(ep.get("id", "")),
                                title=ep.get("title", ""),
                                number=ep.get("number", 1),
                                season=season_number,
                                cover_image=ep.get("coverImage"),
                                source_movie_id=content_id,
                                tracks=tracks
                            ))
                    
                    episodes.sort(key=lambda e: (e.season, e.number))
                
                # Parse seasons
                seasons: list[Season] = []
                for s in d.get("seasons", []):
                    seasons.append(Season(
                        id=str(s.get("movieId", "")),
                        number=s.get("number", 1),
                        name=f"Season {s.get('number', 1)}"
                    ))
                
                # Parse year from publishTime
                year = None
                publish_time = d.get("publishTime")
                if publish_time:
                    try:
                        from datetime import datetime
                        year = datetime.fromisoformat(publish_time.replace("Z", "+00:00")).year
                    except:
                        pass
                
                return MovieDetails(
                    id=str(d.get("id", content_id)),
                    title=d.get("title", ""),
                    description=d.get("briefIntroduction"),
                    cover_image=d.get("coverVerticalImage") or d.get("coverHorizontalImage", ""),
                    background_image=d.get("coverHorizontalImage"),
                    year=year,
                    score=d.get("score"),
                    episodes=episodes,
                    seasons=seasons,
                    tags=d.get("tags", []),
                    actors=[{"name": a.get("name"), "image": a.get("avatar")} for a in d.get("actors", [])]
                )
                
            except Exception as e:
                print(f"[MeowTV] Details error: {e}")
                return None

    async def fetch_stream(
        self,
        movie_id: str,
        episode_id: str,
        language_id: str | int | None = None
    ) -> VideoResponse | None:
        """Fetch stream URL for playback."""
        async with await self._get_client() as client:
            key, cookie = await self._get_security_key(client)
            if not key:
                return None
            
            # Fetch details to get episode tracks
            raw_details_url = f"{MAIN_URL}/film-api/v1.9.9/movie?channel=IndiaA&clientType=1&lang=en-US&movieId={movie_id}&packageName=com.external.castle"
            decrypted_details = await self._request(client, "GET", raw_details_url, key=key)
            
            details = _parse_json_preserve_bigint(decrypted_details).get("data", {}) if decrypted_details else {}
            episodes = details.get("episodes", []) if details else []
            
            # Find target episode
            target_episode = None
            for ep in episodes:
                if str(ep.get("id")) == episode_id:
                    target_episode = ep
                    break
            
            if not target_episode and episodes:
                target_episode = episodes[0]
                episode_id = str(target_episode.get("id", episode_id))
            
            tracks = target_episode.get("tracks", []) if target_episode else []
            has_individual = any(t.get("existIndividualVideo") for t in tracks)
            
            # Build track plan
            track_plan: list[dict] = []
            if language_id:
                track_plan.append({"languageId": language_id})
            elif not has_individual and tracks:
                track_plan.append({"languageId": tracks[0].get("languageId")})
            elif tracks:
                for t in tracks:
                    track_plan.append({"languageId": t.get("languageId")})
            else:
                track_plan.append({"languageId": None})
            
            resolutions = [3, 2, 1]  # 1080p, 720p, 480p
            collected_qualities: list[Quality] = []
            best_video_url: str | None = None
            best_subtitles: list[Subtitle] = []
            
            cookie_header = cookie or os.environ.get("MEOW_COOKIE", "hd=on")
            
            for track in track_plan:
                for resolution in resolutions:
                    raw_url = f"{MAIN_URL}/film-api/v2.0.1/movie/getVideo2?clientType=1&packageName=com.external.castle&channel=IndiaA&lang=en-US"
                    
                    body = {
                        "mode": "1",
                        "appMarket": "GuanWang",
                        "clientType": "1",
                        "woolUser": "false",
                        "apkSignKey": "ED0955EB04E67A1D9F3305B95454FED485261475",
                        "androidVersion": "13",
                        "movieId": movie_id,
                        "episodeId": episode_id,
                        "isNewUser": "true",
                        "resolution": str(resolution),
                        "packageName": "com.external.castle"
                    }
                    
                    if track.get("languageId"):
                        body["languageId"] = str(track["languageId"])
                    
                    try:
                        decrypted = await self._request(
                            client, 
                            "POST", 
                            raw_url, 
                            key=key,
                            headers={
                                **HEADERS,
                                "Content-Type": "application/json; charset=utf-8",
                                "Cookie": cookie_header
                            },
                            json=body
                        )
                        
                        if not decrypted:
                            continue
                        
                        data = _parse_json_preserve_bigint(decrypted).get("data", {})
                        video_url = data.get("videoUrl")
                        
                        quality_label = {3: "1080p", 2: "720p", 1: "480p"}.get(resolution, f"{resolution}p")
                        collected_qualities.append(Quality(quality=quality_label, url=video_url))
                        
                        if not best_video_url:
                            best_video_url = video_url
                            for s in data.get("subtitles", []):
                                lang = s.get("abbreviate") or s.get("title") or "Unknown"
                                sub_url = s.get("url", "")
                                label = s.get("title") or lang or "Subtitles"
                                if sub_url:
                                    best_subtitles.append(Subtitle(
                                        language=lang,
                                        label=label,
                                        url=sub_url
                                    ))
                    except Exception as e:
                        print(f"[MeowTV] Stream fetch error: {e}")
                        continue
            
            if not best_video_url:
                return None
            
            return VideoResponse(
                video_url=best_video_url,
                subtitles=best_subtitles,
                qualities=collected_qualities,
                headers={"Referer": MAIN_URL}
            )
