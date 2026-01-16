"""MeowToon provider (Kartoons + Xon) - ported from meowtoon.ts."""

import asyncio
from typing import Any

import httpx

from meowtv.models import (
    ContentItem, Episode, HomeRow, MovieDetails,
    Quality, Season, Subtitle, VideoResponse, RelatedItem
)
from meowtv.providers.base import Provider

# Kartoons API
MAIN_URL = "https://api.kartoons.fun"
DECRYPT_BASE = "https://kartoondecrypt.onrender.com"

# Xon API (Firebase-based)
XON_MAIN_URL = "http://myavens18052002.xyz/nzapis"
XON_API_KEY = "553y845hfhdlfhjkl438943943839443943fdhdkfjfj9834lnfd98"


def _normalize_id(raw: Any) -> str | None:
    """Normalize an ID to string."""
    if raw is None:
        return None
    s = str(raw).strip()
    return s if s else None


def _normalize_image(src: Any) -> str:
    """Normalize image URL."""
    return str(src) if src else ""


def _derive_season_number(raw: Any, index: int) -> int:
    """Derive season number from various possible fields."""
    candidates = [
        raw.get("seasonNumber") if isinstance(raw, dict) else None,
        raw.get("season_no") if isinstance(raw, dict) else None,
        raw.get("seasonNo") if isinstance(raw, dict) else None,
        raw.get("number") if isinstance(raw, dict) else None,
        raw.get("season") if isinstance(raw, dict) else None,
    ]
    for c in candidates:
        if c is not None:
            try:
                n = int(str(c))
                if n > 0:
                    return n
            except ValueError:
                pass
    return index + 1


def _parse_content_id(raw: str) -> tuple[str, str] | None:
    """Parse content ID into type and identifier."""
    if not raw:
        return None
    idx = raw.find("-")
    if idx <= 0:
        return None
    prefix = raw[:idx]
    identifier = raw[idx + 1:]
    if not identifier:
        return None
    if prefix in ("movie", "series"):
        return (prefix, identifier)
    return None


def _to_kartoons_stream_url(encoded_link: str) -> str:
    """Convert encoded link to decrypt URL."""
    import urllib.parse
    clean = "".join(str(encoded_link or "").split())
    return f"{DECRYPT_BASE}/kartoons?data={urllib.parse.quote(clean)}"


def _format_media_url(url: Any) -> str:
    """Format Xon media URL (handle relative paths)."""
    if not url:
        return ""
    u = str(url).strip()
    if u.startswith(("http://", "https://")):
        return u
    # Xon uses archive.org for relative paths
    return f"https://archive.org/download/{u}"


async def _fetch_json(client: httpx.AsyncClient, url: str, timeout: float = 8.0) -> Any:
    """Fetch JSON with timeout."""
    res = await client.get(url, timeout=timeout)
    res.raise_for_status()
    return res.json()


# ===== XON PROVIDER FUNCTIONS =====

_xon_auth_token: str | None = None
_xon_cache: dict[str, Any] = {
    "languages": [],
    "shows": [],
    "seasons": [],
    "episodes": [],
    "movies": [],
}
_xon_cache_time: float = 0
XON_CACHE_DURATION = 86400  # 24 hours



async def _xon_fetch_settings(client: httpx.AsyncClient, token: str) -> None:
    """Fetch dynamic settings (API Key, Base URL) from Firestore."""
    global XON_API_KEY, XON_MAIN_URL
    try:
        url = "https://firestore.googleapis.com/v1/projects/xon-app/databases/(default)/documents/settings/BvJwsNb0eaObbigSefkm"
        res = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        if res.status_code != 200:
            return

        data = res.json()
        fields = data.get("fields", {})

        api_val = fields.get("api", {}).get("stringValue")
        base_val = fields.get("base", {}).get("stringValue")

        if api_val:
            XON_API_KEY = api_val

        if base_val:
            XON_MAIN_URL = base_val.rstrip("/")

    except Exception as e:
        print(f"[Xon] Settings fetch failed: {e}")


async def _xon_authenticate(client: httpx.AsyncClient) -> str | None:
    """Authenticate with Xon Firebase."""
    global _xon_auth_token
    
    if _xon_auth_token:
        return _xon_auth_token
    
    try:
        # Firebase anonymous auth
        # Key from xon.ts
        auth_url = "https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=AIzaSyAC__yhrI4ExLcqWbZjsLN33_gVgyp6w3A"
        res = await client.post(auth_url, json={"returnSecureToken": True})
        data = res.json()
        _xon_auth_token = data.get("idToken")
        
        if _xon_auth_token:
            # Also fetch settings from Firestore to ensure Key/URL are up to date
            await _xon_fetch_settings(client, _xon_auth_token)
            return _xon_auth_token
        else:
            return None
    except Exception:
        return None


async def _xon_refresh_cache(client: httpx.AsyncClient, force: bool = False) -> None:
    """Refresh Xon cache."""
    global _xon_cache, _xon_cache_time
    
    import time
    if not force and _xon_cache_time > 0 and (time.time() - _xon_cache_time) < XON_CACHE_DURATION:
        return
    
    token = await _xon_authenticate(client)
    if not token:
        return
    
    headers = {
        "Authorization": f"Bearer {token}",
        "api": XON_API_KEY,
        "caller": "vion-official-app",
        "User-Agent": "okhttp/3.14.9",
        "Accept": "application/json"
    }
    
    try:
        urls = {
            "languages": f"{XON_MAIN_URL}/nzgetlanguages.php",
            "shows": f"{XON_MAIN_URL}/nzgetshows.php",
            "seasons": f"{XON_MAIN_URL}/nzgetseasons.php",
            "episodes": f"{XON_MAIN_URL}/nzgetepisodes_v2.php?since=",
            "movies": f"{XON_MAIN_URL}/nzgetmovies.php",
        }
        
        for key, url in urls.items():
            try:
                res = await client.get(url, headers=headers, timeout=15)
                # Check status
                if res.status_code != 200:
                    continue
                
                json_data = res.json()
                if key == "episodes" and isinstance(json_data, dict):
                    _xon_cache[key] = json_data.get("episodes", [])
                else:
                    _xon_cache[key] = json_data
                
            except Exception as e:
                pass
        
        _xon_cache_time = time.time()
    except Exception as e:
        print(f"[Xon] Cache refresh failed: {e}")


async def _xon_fetch_home(client: httpx.AsyncClient) -> list[HomeRow]:
    """Fetch Xon home content."""
    await _xon_refresh_cache(client)
    
    rows: list[HomeRow] = []
    
    # Recent Episodes
    episodes = _xon_cache.get("episodes", [])[:20]
    if episodes:
        items = [
            ContentItem(
                id=f"xon:{ep.get('id')}",
                title=ep.get("name", ""),
                cover_image=_normalize_image(ep.get("thumb") or ep.get("cover")),
                type="series"
            )
            for ep in episodes if ep.get("id")
        ]
        if items:
            rows.append(HomeRow(name="Xon • Recent Episodes", contents=items))
    
    # Movies
    movies = _xon_cache.get("movies", [])[:20]
    if movies:
        items = [
            ContentItem(
                id=f"xon:movie-{m.get('id')}",
                title=m.get("name", ""),
                cover_image=_normalize_image(m.get("thumb") or m.get("cover")),
                type="movie"
            )
            for m in movies if m.get("id")
        ]
        if items:
            rows.append(HomeRow(name="Xon • Movies", contents=items))
    
    return rows


async def _xon_search(client: httpx.AsyncClient, query: str) -> list[ContentItem]:
    """Search Xon content."""
    await _xon_refresh_cache(client)
    
    query_lower = query.lower()
    results: list[ContentItem] = []
    
    # Search seasons
    for season in _xon_cache.get("seasons", []):
        name = str(season.get("name", "")).lower()
        if query_lower in name:
            results.append(ContentItem(
                id=f"xon:season-{season.get('id')}",
                title=season.get("name", ""),
                cover_image=_normalize_image(season.get("thumb") or season.get("cover")),
                type="series"
            ))
    
    # Search movies
    for movie in _xon_cache.get("movies", []):
        name = str(movie.get("name", "")).lower()
        if query_lower in name:
            results.append(ContentItem(
                id=f"xon:movie-{movie.get('id')}",
                title=movie.get("name", ""),
                cover_image=_normalize_image(movie.get("thumb") or movie.get("cover")),
                type="movie"
            ))
    
    return results[:30]


async def _xon_fetch_details(client: httpx.AsyncClient, xon_id: str) -> MovieDetails | None:
    """Fetch Xon content details."""
    await _xon_refresh_cache(client)
    
    # Parse ID type
    if xon_id.startswith("movie-"):
        movie_id = int(xon_id[6:])
        for movie in _xon_cache.get("movies", []):
            if movie.get("id") == movie_id:
                return MovieDetails(
                    id=f"xon:{xon_id}",
                    title=movie.get("name", ""),
                    description=movie.get("des"),
                    cover_image=_normalize_image(movie.get("thumb") or movie.get("cover")),
                    background_image=_normalize_image(movie.get("cover")),
                    episodes=[Episode(
                        id=f"xon:movie-{movie_id}",
                        title=movie.get("name", ""),
                        number=1,
                        season=1,
                        source_movie_id=f"xon:{xon_id}"
                    )]
                )
    elif xon_id.startswith("season-"):
        season_id = int(xon_id[7:])
        season_data = None
        for s in _xon_cache.get("seasons", []):
            if s.get("id") == season_id:
                season_data = s
                break
        
        if season_data:
            # Find episodes for this season
            episodes = [
                Episode(
                    id=f"xon:{ep.get('id')}",
                    title=ep.get("name", ""),
                    number=ep.get("no", 1),
                    season=1,
                    cover_image=_normalize_image(ep.get("thumb")),
                    source_movie_id=f"xon:{xon_id}"
                )
                for ep in _xon_cache.get("episodes", [])
                if ep.get("season_id") == season_id
            ]
            
            return MovieDetails(
                id=f"xon:{xon_id}",
                title=season_data.get("name", ""),
                description=season_data.get("des"),
                cover_image=_normalize_image(season_data.get("thumb") or season_data.get("cover")),
                background_image=_normalize_image(season_data.get("cover")),
                episodes=sorted(episodes, key=lambda e: (e.season, e.number))
            )
    else:
        # Episode ID - find episode and its season
        try:
            ep_id = int(xon_id)
            for ep in _xon_cache.get("episodes", []):
                if ep.get("id") == ep_id:
                    season_id = ep.get("season_id")
                    # Find season name
                    season_name = ""
                    for s in _xon_cache.get("seasons", []):
                        if s.get("id") == season_id:
                            season_name = s.get("name", "")
                            break
                    
                    return MovieDetails(
                        id=f"xon:{xon_id}",
                        title=season_name or ep.get("name", ""),
                        description=ep.get("des"),
                        cover_image=_normalize_image(ep.get("thumb") or ep.get("cover")),
                        episodes=[Episode(
                            id=f"xon:{ep_id}",
                            title=ep.get("name", ""),
                            number=ep.get("no", 1),
                            season=1,
                            source_movie_id=f"xon:{xon_id}"
                        )]
                    )
        except ValueError:
            pass
    
    return None


async def _xon_fetch_stream(client: httpx.AsyncClient, xon_id: str) -> VideoResponse | None:
    """Fetch Xon stream URL."""
    await _xon_refresh_cache(client)
    
    # Find the content
    video_data: dict = {}
    
    if xon_id.startswith("movie-"):
        movie_id = int(xon_id[6:])
        for movie in _xon_cache.get("movies", []):
            if movie.get("id") == movie_id:
                video_data = movie
                break
    else:
        try:
            ep_id = int(xon_id)
            for ep in _xon_cache.get("episodes", []):
                if ep.get("id") == ep_id:
                    video_data = ep
                    break
        except ValueError:
            pass
    
    if not video_data:
        return None
    
    # Get stream URLs - prefer higher quality
    qualities: list[Quality] = []
    for label, key in [("1080p", "fhd"), ("720p", "hd"), ("480p", "sd"), ("360p", "basic")]:
        url = _format_media_url(video_data.get(key))
        if url:
            qualities.append(Quality(quality=label, url=url))
    
    if not qualities:
        # Try link field
        link = _format_media_url(video_data.get("link"))
        if link:
            qualities.append(Quality(quality="Auto", url=link))
    
    if not qualities:
        return None
    
    return VideoResponse(
        video_url=qualities[0].url,
        qualities=qualities
    )


class MeowToonProvider(Provider):
    """MeowToon (Kartoons + Xon) content provider."""

    @property
    def name(self) -> str:
        return "MeowToon"

    async def fetch_home(self, page: int = 1) -> list[HomeRow]:
        """Fetch home page content from both Kartoons and Xon."""
        if page > 1:
            return []

        async with httpx.AsyncClient(timeout=30) as client:
            rows: list[HomeRow] = []
            
            # Fetch from Kartoons
            try:
                shows_task = _fetch_json(client, f"{MAIN_URL}/api/shows/?page=1&limit=20")
                movies_task = _fetch_json(client, f"{MAIN_URL}/api/movies/?page=1&limit=20")
                pop_shows_task = _fetch_json(client, f"{MAIN_URL}/api/popularity/shows?limit=15&period=day")
                pop_movies_task = _fetch_json(client, f"{MAIN_URL}/api/popularity/movies?limit=15&period=day")
                
                results = await asyncio.gather(
                    shows_task, movies_task, pop_shows_task, pop_movies_task,
                    return_exceptions=True
                )
                
                shows_data, movies_data, pop_shows, pop_movies = results
                
                def map_item(item: Any, item_type: str) -> ContentItem:
                    return ContentItem(
                        id=f"{item_type}-{item.get('slug') or item.get('id', '')}",
                        title=item.get("title", ""),
                        cover_image=_normalize_image(item.get("image")),
                        type=item_type  # type: ignore
                    )
                
                if isinstance(pop_shows, dict):
                    items = [map_item(i, "series") for i in pop_shows.get("data", [])]
                    if items:
                        rows.append(HomeRow(name="Popular Shows", contents=items))
                
                if isinstance(pop_movies, dict):
                    items = [map_item(i, "movie") for i in pop_movies.get("data", [])]
                    if items:
                        rows.append(HomeRow(name="Popular Movies", contents=items))
                
                if isinstance(shows_data, dict):
                    items = [map_item(i, "series") for i in shows_data.get("data", [])]
                    if items:
                        rows.append(HomeRow(name="Shows", contents=items))
                
                if isinstance(movies_data, dict):
                    items = [map_item(i, "movie") for i in movies_data.get("data", [])]
                    if items:
                        rows.append(HomeRow(name="Movies", contents=items))
                        
            except Exception as e:
                print(f"[MeowToon] Kartoons home error: {e}")
            
            # Fetch from Xon
            try:
                xon_rows = await _xon_fetch_home(client)
                rows.extend(xon_rows)
            except Exception as e:
                print(f"[MeowToon] Xon home error: {e}")
            
            return rows

    async def search(self, query: str) -> list[ContentItem]:
        """Search both Kartoons and Xon."""
        async with httpx.AsyncClient(timeout=30) as client:
            results: list[ContentItem] = []
            
            # Search Kartoons
            try:
                data = await _fetch_json(
                    client, 
                    f"{MAIN_URL}/api/search/suggestions?q={query}&limit=20"
                )
                
                for item in data.get("data", []):
                    t = str(item.get("type", "")).lower()
                    item_type = "movie" if t == "movie" else "series"
                    identifier = item.get("id") or item.get("slug")
                    results.append(ContentItem(
                        id=f"{item_type}-{identifier}",
                        title=item.get("title", ""),
                        cover_image=item.get("image", ""),
                        type=item_type  # type: ignore
                    ))
            except Exception as e:
                print(f"[MeowToon] Kartoons search error: {e}")
            
            # Search Xon
            try:
                xon_results = await _xon_search(client, query)
                results.extend(xon_results)
            except Exception as e:
                print(f"[MeowToon] Xon search error: {e}")
            
            # De-duplicate
            seen: set[str] = set()
            unique: list[ContentItem] = []
            for r in results:
                if r.id and r.id not in seen:
                    seen.add(r.id)
                    unique.append(r)
            
            return unique

    async def fetch_details(self, content_id: str, include_episodes: bool = True) -> MovieDetails | None:
        """Fetch content details."""
        async with httpx.AsyncClient(timeout=30) as client:
            # Handle Xon content
            if content_id.startswith("xon:"):
                return await _xon_fetch_details(client, content_id[4:])
            
            # Parse Kartoons content ID
            parsed = _parse_content_id(content_id)
            if not parsed:
                return None
            
            content_type, identifier = parsed
            api_type = "shows" if content_type == "series" else "movies"
            
            try:
                json_data = await _fetch_json(client, f"{MAIN_URL}/api/{api_type}/{identifier}")
                data = json_data.get("data")
                if not data:
                    return None
                
                title = data.get("title", "")
                cover_image = data.get("image", "")
                background_image = data.get("coverImage") or data.get("hoverImage")
                
                if content_type == "series":
                    show_slug = data.get("slug")
                    seasons_raw = data.get("seasons", [])
                    
                    # Parse seasons
                    seasons: list[Season] = []
                    for i, s in enumerate(seasons_raw):
                        season_slug = _normalize_id(s.get("slug") or s.get("_id") or s.get("id"))
                        if season_slug:
                            season_num = _derive_season_number(s, i)
                            seasons.append(Season(
                                id=season_slug,
                                number=season_num,
                                name=f"Season {season_num}"
                            ))
                    
                    # Fetch episodes for each season
                    episodes: list[Episode] = []
                    if include_episodes:
                        for i, season in enumerate(seasons_raw):
                            season_slug = _normalize_id(season.get("slug") or season.get("_id") or season.get("id"))
                            season_num = _derive_season_number(season, i)
                            
                            if show_slug and season_slug:
                                try:
                                    ep_url = f"{MAIN_URL}/api/shows/{show_slug}/season/{season_slug}/all-episodes"
                                    ep_data = await _fetch_json(client, ep_url)
                                    
                                    for ep in ep_data.get("data", []):
                                        ep_id = _normalize_id(ep.get("id") or ep.get("_id"))
                                        if ep_id:
                                            ep_num = int(str(ep.get("episodeNumber", 0)))
                                            episodes.append(Episode(
                                                id=f"ep-{ep_id}",
                                                title=ep.get("title") or f"Episode {ep_num}",
                                                number=ep_num if ep_num > 0 else 1,
                                                season=season_num,
                                                cover_image=ep.get("image"),
                                                description=ep.get("description"),
                                                source_movie_id=content_id
                                            ))
                                except Exception as e:
                                    print(f"[MeowToon] Failed to fetch episodes: {e}")
                        
                        episodes.sort(key=lambda e: (e.season, e.number))
                    
                    # Related content
                    related: list[RelatedItem] = []
                    for r in json_data.get("related", []):
                        r_type = "movie" if r.get("type") == "movie" else "series"
                        r_id = r.get("slug") or r.get("_id") or r.get("id")
                        related.append(RelatedItem(
                            id=f"{r_type}-{r_id}",
                            title=r.get("title", ""),
                            image=r.get("image", ""),
                            type="movie" if r_type == "movie" else "show",
                            year=int(r.get("startYear")) if r.get("startYear") else None
                        ))
                    
                    return MovieDetails(
                        id=content_id,
                        title=title,
                        description=data.get("description"),
                        cover_image=cover_image,
                        background_image=background_image,
                        year=int(data.get("startYear")) if data.get("startYear") else None,
                        score=data.get("rating"),
                        episodes=episodes,
                        seasons=seasons,
                        tags=data.get("tags", []),
                        related_content=related
                    )
                else:
                    # Movie
                    movie_id = _normalize_id(data.get("id") or data.get("_id"))
                    if not movie_id:
                        return None
                    
                    episodes = [Episode(
                        id=f"mov-{movie_id}",
                        title=title,
                        number=1,
                        season=1,
                        cover_image=cover_image,
                        source_movie_id=content_id
                    )]
                    
                    return MovieDetails(
                        id=content_id,
                        title=title,
                        description=data.get("description"),
                        cover_image=cover_image,
                        background_image=background_image,
                        year=int(data.get("startYear")) if data.get("startYear") else None,
                        score=data.get("rating"),
                        episodes=episodes,
                        tags=data.get("tags", [])
                    )
                    
            except Exception as e:
                print(f"[MeowToon] Details error: {e}")
                return None

    async def fetch_stream(
        self,
        movie_id: str,
        episode_id: str,
        language_id: str | int | None = None
    ) -> VideoResponse | None:
        """Fetch stream URL."""
        async with httpx.AsyncClient(timeout=30) as client:
            # Handle Xon content
            if episode_id.startswith("xon:"):
                return await _xon_fetch_stream(client, episode_id[4:])
            
            # Handle Kartoons content
            try:
                if episode_id.startswith("ep-"):
                    url = f"{MAIN_URL}/api/shows/episode/{episode_id[3:]}/links"
                elif episode_id.startswith("mov-"):
                    url = f"{MAIN_URL}/api/movies/{episode_id[4:]}/links"
                else:
                    print(f"[MeowToon] Unknown episode ID format: {episode_id}")
                    return None
                
                json_data = await _fetch_json(client, url, timeout=8.0)
                links = json_data.get("data", {}).get("links", [])
                
                if not links:
                    return None
                
                # Get first valid link
                for link in links:
                    encoded = link.get("url")
                    if encoded:
                        # Use decrypt service URL directly - it returns M3U8 content
                        decrypt_url = _to_kartoons_stream_url(str(encoded))
                        
                        # The decrypt service returns M3U8 content directly,
                        # so we use the decrypt URL as the stream URL
                        return VideoResponse(video_url=decrypt_url)
                
                return None
                
            except Exception as e:
                print(f"[MeowToon] Stream error: {e}")
                return None
