# MeowTV CLI 🐱📺

[![PyPI version](https://badge.fury.io/py/meowtv.svg)](https://badge.fury.io/py/meowtv)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**MeowTV CLI** is a feature-rich terminal application for streaming movies, TV shows, and cartoons directly from the command line. It supports multiple providers, local favorites, downloads, and integration with high-quality media players like mpv and VLC.

## ✨ Features

- **Multi-Provider Support**:
  - 🌌 **MeowVerse**: Huge library of Movies & TV Shows.
  - 🏰 **MeowTV**: High-quality streams from Castle API.
  - 🦁 **MeowToon**: Cartoons and Anime content.
- **Interactive TUI**: Beautiful, easy-to-use terminal interface powered by `rich`.
- **Powerful Playback**: Streaming support via **mpv** (recommended) or **VLC**.
- **Downloads**: Download content for offline viewing (HLS/m3u8 support).
- **Favorites**: Manage your watchlist locally.
- **Smart Search**: Unified search across providers.

## 📦 Installation

Install directly from PyPI:

```bash
pip install meowtv
```

### System Requirements
External players are required for playback:
- **[mpv](https://mpv.io/)** (Recommended) or **VLC**
- **[FFmpeg](https://ffmpeg.org/)** (Required for downloads)

Ensure these are installed and available in your system PATH.

## 🚀 Usage

Start the interactive mode:
```bash
meowtv
```

### Quick Commands

**Search:**
```bash
meowtv search "breaking bad"
meowtv search "naruto" -p meowtoon
```

**Play:**
```bash
meowtv play <content_id>
meowtv play <content_id> --player vlc
```

**Download:**
```bash
meowtv download <content_id> -o ~/Downloads
```

**Favorites:**
```bash
meowtv favorites list
meowtv favorites add <content_id>
```

**Configuration:**
```bash
meowtv config --player mpv
meowtv config --proxy <url>
```

## ⚙️ Configuration

Configuration is stored in `~/.config/meowtv/config.json`. You can edit it manually or via the CLI:
```bash
meowtv config --show
```

## 📝 License

This project is licensed under the MIT License.

## ⚠️ Disclaimer

This tool is for educational purposes only. The developers do not host any content. content is scraped from third-party providers.
