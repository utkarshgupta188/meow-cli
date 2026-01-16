"""Abstract base class for content providers."""

from abc import ABC, abstractmethod

from meowtv.models import ContentItem, HomeRow, MovieDetails, VideoResponse


class Provider(ABC):
    """Base class for all content providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for display."""
        ...

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
