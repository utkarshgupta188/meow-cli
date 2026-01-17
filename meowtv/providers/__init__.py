"""Providers package."""

from meowtv.providers.base import Provider
from meowtv.providers.meowtv import MeowTVProvider
from meowtv.providers.meowtoon import MeowToonProvider

__all__ = [
    "Provider",
    "MeowVerseProvider",
    "MeowTVProvider",
    "MeowToonProvider",
]

# Provider registry for easy access
PROVIDERS: dict[str, Provider] = {}


def get_provider(name: str) -> Provider | None:
    """Get a provider by name."""
    return PROVIDERS.get(name.lower())


def get_all_providers() -> list[Provider]:
    """Get all registered providers."""
    return list(PROVIDERS.values())


def register_providers():
    """Register all available providers."""
    global PROVIDERS
    # Delay import of MeowVerseProvider to avoid circular dependency if needed, 
    # but strictly we import it at top. MeowVerseProvider will be the new CineStream one.
    from meowtv.providers.meowverse import MeowVerseProvider
    
    PROVIDERS = {
        "meowverse": MeowVerseProvider(),
        "meowtv": MeowTVProvider(),
        "meowtoon": MeowToonProvider(),
    }


# Auto-register on import
register_providers()
