"""Providers package."""

from meowtv.providers.base import Provider
from meowtv.providers.meowverse import MeowVerseProvider
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
    PROVIDERS = {
        "meowverse": MeowVerseProvider(),
        "meowtv": MeowTVProvider(),
        "meowtoon": MeowToonProvider(),
    }


# Auto-register on import
register_providers()
