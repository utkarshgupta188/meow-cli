"""Providers package."""

from meowtv.providers.base import Provider
from meowtv.providers.meowtv import MeowTVProvider
from meowtv.providers.meowtoon import MeowToonProvider
from meowtv.providers.meowverse import MeowVerseProvider

__all__ = [
    "Provider",
    "MeowTVProvider",
    "MeowToonProvider",
    "MeowVerseProvider",
]


# Provider registry for easy access
PROVIDERS: dict[str, Provider] = {}


def get_provider(name: str) -> Provider | None:
    """Get a provider by name."""
    from meowtv.config import get_config
    prov = PROVIDERS.get(name.lower())
    if prov:
        prov.proxy_url = get_config().proxy_url
    return prov


def get_all_providers() -> list[Provider]:
    """Get all registered providers."""
    return list(PROVIDERS.values())


def register_providers():
    """Register all available providers."""
    global PROVIDERS
    # Delay import of MeowVerseProvider to avoid circular dependency if needed, 
    # but strictly we import it at top. MeowVerseProvider will be the new CineStream one.
    
    PROVIDERS = {
        "meowverse": MeowVerseProvider(),
        "meowtv": MeowTVProvider(),
        "meowtoon": MeowToonProvider(),
    }


# Auto-register on import
register_providers()
