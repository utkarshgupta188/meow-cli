"""Favorites management for MeowTV CLI."""

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from meowtv.config import get_data_dir


@dataclass
class FavoriteItem:
    """A favorited content item."""
    id: str
    title: str
    cover_image: str
    type: str  # "movie" or "series"
    provider: str
    added_at: str  # ISO timestamp
    last_watched_episode: str | None = None
    last_watched_at: str | None = None


class FavoritesManager:
    """Manage favorites with JSON persistence."""
    
    def __init__(self):
        self._favorites: dict[str, FavoriteItem] = {}
        self._load()
    
    @property
    def _file_path(self) -> Path:
        return get_data_dir() / "favorites.json"
    
    def _load(self) -> None:
        """Load favorites from file."""
        if self._file_path.exists():
            try:
                with open(self._file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                for key, item_data in data.items():
                    self._favorites[key] = FavoriteItem(**item_data)
            except Exception as e:
                print(f"[Favorites] Failed to load: {e}")
    
    def _save(self) -> None:
        """Save favorites to file."""
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {key: asdict(item) for key, item in self._favorites.items()}
        
        with open(self._file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    def _make_key(self, provider: str, content_id: str) -> str:
        """Create unique key for a favorite."""
        return f"{provider}:{content_id}"
    
    def add(
        self,
        content_id: str,
        title: str,
        cover_image: str,
        content_type: str,
        provider: str
    ) -> FavoriteItem:
        """Add a content item to favorites."""
        key = self._make_key(provider, content_id)
        
        if key in self._favorites:
            return self._favorites[key]
        
        item = FavoriteItem(
            id=content_id,
            title=title,
            cover_image=cover_image,
            type=content_type,
            provider=provider,
            added_at=datetime.now().isoformat()
        )
        
        self._favorites[key] = item
        self._save()
        return item
    
    def remove(self, provider: str, content_id: str) -> bool:
        """Remove a content item from favorites."""
        key = self._make_key(provider, content_id)
        
        if key in self._favorites:
            del self._favorites[key]
            self._save()
            return True
        return False
    
    def is_favorite(self, provider: str, content_id: str) -> bool:
        """Check if a content item is in favorites."""
        key = self._make_key(provider, content_id)
        return key in self._favorites
    
    def get(self, provider: str, content_id: str) -> FavoriteItem | None:
        """Get a favorite item."""
        key = self._make_key(provider, content_id)
        return self._favorites.get(key)
    
    def list_all(self) -> list[FavoriteItem]:
        """List all favorites."""
        return sorted(
            self._favorites.values(),
            key=lambda x: x.added_at,
            reverse=True
        )
    
    def list_by_provider(self, provider: str) -> list[FavoriteItem]:
        """List favorites for a specific provider."""
        return [
            item for item in self.list_all()
            if item.provider.lower() == provider.lower()
        ]
    
    def update_watch_progress(
        self,
        provider: str,
        content_id: str,
        episode_id: str
    ) -> None:
        """Update watch progress for a favorite."""
        key = self._make_key(provider, content_id)
        
        if key in self._favorites:
            self._favorites[key].last_watched_episode = episode_id
            self._favorites[key].last_watched_at = datetime.now().isoformat()
            self._save()
    
    def clear_all(self) -> None:
        """Clear all favorites."""
        self._favorites.clear()
        self._save()
    
    def export_json(self) -> str:
        """Export favorites as JSON string."""
        return json.dumps(
            {key: asdict(item) for key, item in self._favorites.items()},
            indent=2
        )
    
    def import_json(self, json_str: str) -> int:
        """Import favorites from JSON string. Returns count of imported items."""
        try:
            data = json.loads(json_str)
            count = 0
            
            for key, item_data in data.items():
                if key not in self._favorites:
                    self._favorites[key] = FavoriteItem(**item_data)
                    count += 1
            
            self._save()
            return count
        except Exception as e:
            print(f"[Favorites] Import failed: {e}")
            return 0


# Global instance
_manager: FavoritesManager | None = None


def get_favorites_manager() -> FavoritesManager:
    """Get the global favorites manager."""
    global _manager
    if _manager is None:
        _manager = FavoritesManager()
    return _manager
