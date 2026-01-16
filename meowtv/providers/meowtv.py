"""MeowTV (Castle) provider - ported from meowtv.ts."""

import json
import os
import re
from typing import Any

import httpx

from meowtv.crypto import decrypt_data
from meowtv.models import (
    ContentItem, Episode, HomeRow, MovieDetails, 
    Quality, Season, Subtitle, Track, VideoResponse
)
from meowtv.providers.base import Provider
from meowtv.providers import proxy as proxy_utils
from meowtv.providers.proxy import get_hls_proxy_url

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


async def _get_security_key(client: httpx.AsyncClient, retries: int = 3) -> tuple[str | None, str | None]:
    """Fetch security key from Castle API."""
    url = f"{MAIN_URL}/v0.1/system/getSecurityKey/1?channel=IndiaA&clientType=1&lang=en-US"
    
    for attempt in range(1, retries + 1):
        try:
            res = await client.get(url, headers=HEADERS)
            cookie = res.headers.get("set-cookie", "")
            text = res.text
            
            try:
                data = json.loads(text)
                if data.get("code") == 200 and data.get("data"):
                    return data["data"], cookie
            except json.JSONDecodeError:
                print(f"[MeowTV] getSecurityKey parse error (attempt {attempt})")
                
        except Exception as e:
            print(f"[MeowTV] getSecurityKey failed (attempt {attempt}): {e}")
    
    return None, None


async def _fetch_details_with_key(client: httpx.AsyncClient, content_id: str, key: str) -> Any | None:
    """Fetch details using security key."""
    url = f"{MAIN_URL}/film-api/v1.9.9/movie?channel=IndiaA&clientType=1&lang=en-US&movieId={content_id}&packageName=com.external.castle"
    
    try:
        res = await client.get(url)
        decrypted = decrypt_data(res.text, key)
        if not decrypted:
            return None
        return _parse_json_preserve_bigint(decrypted).get("data")
    except Exception:
        return None


class MeowTVProvider(Provider):
    """MeowTV (Castle) content provider."""

    @property
    def name(self) -> str:
        return "MeowTV"

    async def fetch_home(self, page: int = 1) -> list[HomeRow]:
        """Fetch home page content."""
        async with httpx.AsyncClient(timeout=30) as client:
            key, _ = await _get_security_key(client)
            if not key:
                return []
            
            url = f"{MAIN_URL}/film-api/v0.1/category/home?channel=IndiaA&clientType=1&lang=en-US&locationId=1001&mode=1&packageName=com.external.castle&page={page}&size=17"
            
            try:
                res = await client.get(url)
                text = res.text
                
                # Try to extract encrypted data
                encrypted_data = text
                try:
                    parsed = json.loads(text)
                    if parsed.get("data"):
                        encrypted_data = parsed["data"]
                except json.JSONDecodeError:
                    pass
                
                decrypted = decrypt_data(encrypted_data, key)
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
        async with httpx.AsyncClient(timeout=30) as client:
            key, _ = await _get_security_key(client)
            if not key:
                return []
            
            url = f"{MAIN_URL}/film-api/v1.1.0/movie/searchByKeyword?channel=IndiaA&clientType=1&keyword={query}&lang=en-US&mode=1&packageName=com.external.castle&page=1&size=30"
            
            try:
                res = await client.get(url)
                decrypted = decrypt_data(res.text, key)
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
        async with httpx.AsyncClient(timeout=30) as client:
            key, _ = await _get_security_key(client)
            if not key:
                return None
            
            url = f"{MAIN_URL}/film-api/v1.9.9/movie?channel=IndiaA&clientType=1&lang=en-US&movieId={content_id}&packageName=com.external.castle"
            
            try:
                res = await client.get(url)
                decrypted = decrypt_data(res.text, key)
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
                            
                            season_data = await _fetch_details_with_key(client, str(movie_id), key)
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
        async with httpx.AsyncClient(timeout=60) as client:
            key, cookie = await _get_security_key(client)
            if not key:
                return None
            
            # Fetch details to get episode tracks
            details = await _fetch_details_with_key(client, movie_id, key)
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
                    url = f"{MAIN_URL}/film-api/v2.0.1/movie/getVideo2?clientType=1&packageName=com.external.castle&channel=IndiaA&lang=en-US"
                    
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
                        res = await client.post(
                            url,
                            headers={
                                **HEADERS,
                                "Content-Type": "application/json; charset=utf-8",
                                "Cookie": cookie_header
                            },
                            json=body
                        )
                        
                        decrypted = decrypt_data(res.text, key)
                        if not decrypted:
                            continue
                        
                        data = _parse_json_preserve_bigint(decrypted).get("data", {})
                        video_url = data.get("videoUrl")
                        
                        if video_url:
                            # Apply proxy if configured
                            if proxy_utils.PROXY_WORKER_URL:
                                params = {
                                    "ua": HEADERS["User-Agent"],
                                    # Add other headers if needed, e.g. Referer
                                }
                                # MeowTV streams are usually simple HLS without complex cookies
                                video_url = get_hls_proxy_url(video_url, params)

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
