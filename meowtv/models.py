"""Data models for MeowTV CLI - ported from TypeScript types."""

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class ContentItem:
    """Search/browse result item."""
    id: str
    title: str
    cover_image: str
    type: Literal["movie", "series"]
    extra: Optional[dict] = None


@dataclass
class RelatedItem:
    """Related content suggestion."""
    id: str
    title: str
    image: str
    type: Optional[Literal["movie", "show"]] = None
    rating: Optional[float] = None
    year: Optional[int] = None


@dataclass
class Track:
    """Audio/subtitle track."""
    name: str
    language_id: Optional[int] = None
    url: Optional[str] = None
    is_default: bool = False


@dataclass
class Episode:
    """Episode data."""
    id: str
    title: str
    number: int
    season: int
    cover_image: Optional[str] = None
    description: Optional[str] = None
    tracks: list[Track] = field(default_factory=list)
    source_movie_id: Optional[str] = None


@dataclass
class Season:
    """Season info."""
    id: str
    number: int
    name: str


@dataclass
class MovieDetails:
    """Full content details."""
    id: str
    title: str
    cover_image: str
    description: Optional[str] = None
    background_image: Optional[str] = None
    year: Optional[int] = None
    score: Optional[float] = None
    episodes: list[Episode] = field(default_factory=list)
    seasons: list[Season] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    actors: list[dict] = field(default_factory=list)
    related_content: list[RelatedItem] = field(default_factory=list)


@dataclass
class Subtitle:
    """Subtitle track."""
    language: str
    url: str
    label: str


@dataclass
class Quality:
    """Video quality option."""
    quality: str  # "1080p", "720p", etc.
    url: str


@dataclass
class VideoResponse:
    """Stream response with URL and metadata."""
    video_url: str
    subtitles: list[Subtitle] = field(default_factory=list)
    qualities: list[Quality] = field(default_factory=list)
    audio_tracks: list[Track] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class HomeRow:
    """Home page content row."""
    name: str
    contents: list[ContentItem]
