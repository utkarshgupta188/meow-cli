# MeowTV CLI 🐱📺

A Python CLI for streaming content from MeowTV providers.

## Features

- 🔍 **Search** content across multiple providers
- 📺 **Stream** with mpv or VLC
- ⬇️ **Download** for offline viewing
- ❤️ **Favorites** with local storage
- 🎨 **Beautiful TUI** with rich formatting

## Installation

```bash
cd cli
pip install -e .
```

## Usage

```bash
# Interactive mode
meowtv

# Quick search
meowtv search "breaking bad"

# Play content
meowtv play <content-id> --player mpv

# Download
meowtv download <content-id>

# Manage favorites
meowtv favorites list
meowtv favorites add <content-id>

# Configuration
meowtv config
```

## Providers

- **MeowVerse** - Movies & TV Shows
- **MeowTV** - Castle API content
- **MeowToon** - Cartoons & Anime

## Requirements

- Python 3.10+
- mpv or VLC (for playback)
- yt-dlp (for downloads)
