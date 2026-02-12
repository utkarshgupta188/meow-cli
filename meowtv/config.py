"""Configuration management for MeowTV CLI."""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal


def get_config_dir() -> Path:
    """Get config directory path."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "meowtv"


def get_data_dir() -> Path:
    """Get data directory path."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "meowtv"


@dataclass
class Config:
    """MeowTV CLI configuration."""
    default_player: Literal["mpv", "vlc"] = "mpv"
    default_provider: str = "meowtv"
    download_dir: str = str(Path.home() / "Downloads" / "MeowTV")
    proxy_url: str = "https://meowtvserver.utkarshg.workers.dev"
    preferred_quality: str = "1080p"
    mpv_args: list[str] = field(default_factory=list)
    vlc_args: list[str] = field(default_factory=list)


_config: Config | None = None


def load_config() -> Config:
    """Load configuration from file."""
    global _config
    if _config is not None:
        return _config
    
    config_file = get_config_dir() / "config.json"
    
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            _config = Config(**{k: v for k, v in data.items() if hasattr(Config, k)})
        except Exception as e:
            print(f"[Config] Failed to load config: {e}")
            _config = Config()
    else:
        _config = Config()
    
    return _config


def save_config(config: Config) -> None:
    """Save configuration to file."""
    global _config
    _config = config
    
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    
    config_file = config_dir / "config.json"
    
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(asdict(config), f, indent=2)


def get_config() -> Config:
    """Get current configuration."""
    return load_config()
