"""Abstract base class for content providers."""

from abc import ABC, abstractmethod

from meowtv.models import ContentItem, HomeRow, MovieDetails, VideoResponse


from typing import Optional
from urllib.parse import quote

class Provider(ABC):
    """Base class for all content providers."""
    
    def __init__(self, proxy_url: Optional[str] = None):
        self.proxy_url = proxy_url

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for display."""
        ...

    def get_proxied_url(self, url: str) -> str:
        """Prepend proxy worker URL if configured."""
        if self.proxy_url and "workers.dev" in self.proxy_url:
            return f"{self.proxy_url}/api/proxy?url={quote(url)}"
        return url

    @abstractmethod
    async def fetch_home(self, page: int = 1) -> list[HomeRow]:
        """Fetch home page content rows."""
        ...

    @abstractmethod
    async def search(self, query: str) -> list[ContentItem]:
        """Search for content."""
        ...

    @abstractmethod
    async def fetch_details(self, content_id: str, include_episodes: bool = True) -> MovieDetails | None:
        """Fetch full details for a content item."""
        ...

    @abstractmethod
    async def fetch_stream(
        self,
        movie_id: str,
        episode_id: str,
        language_id: str | int | None = None
    ) -> VideoResponse | None:
        """Fetch stream URL for playback."""
        ...
