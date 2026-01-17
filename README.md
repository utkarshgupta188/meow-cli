# 🐱 MeowTV CLI - The Purr-fect Streamer

<p align="center">
  <img src="https://img.icons8.com/isometric/512/flat-tv.png" width="128" />
  <br />
  <b>Stream movies, TV shows, and cartoons directly from your terminal.</b>
  <br />
  <i>Fast, lightweight, and absolutely paw-some.</i>
</p>

---

[![PyPI version](https://badge.fury.io/py/meowtv.svg)](https://badge.fury.io/py/meowtv)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.8+](https://img.shields.io/badge/Python-3.8+-green.svg)](https://www.python.org/)

**MeowTV CLI** is a feature-rich terminal application for streaming content. Built with speed in mind, it leverages parallel fetching, HLS proxying, and intelligent variant filtering to give you a buffer-free experience.

---

## 🔥 Key Features

*   🌍 **Universal Search**: Search across multiple high-quality providers simultaneously.
*   🚀 **Turbo Startup**: Parallelized metadata fetching and subtitle downloads for instant launch.
*   🎬 **High Quality**: Support for 1080p+, Multi-audio, and Dual-audio streams.
*   🛡️ **Smart Proxy**: Built-in Flask HLS proxy with **Variant Filtering** to prevent connection starvation.
*   💬 **Subtitles Support**: Multi-language support with automatic local downloading for player compatibility.
*   📥 **Integrated Downloads**: Save your favorite content for offline viewing.
*   ⭐ **Watchlist**: Manage your personal library with local favorites.

---

## 🌌 Providers

| Provider | Content Type | Speciality |
| :--- | :--- | :--- |
| **MeowVerse** | Movies & TV | Global content, multi-audio, high speed |
| **MeowTV** | Movies & TV | Premium Asian & Global library |
| **MeowToon** | Anime & Kids | Extensive cartoon & anime collection |

---

## 📦 Installation

```bash
pip install -U meowtv
```

### 🛠️ Dependencies
- **[mpv](https://mpv.io/)** (Highly recommended) or **VLC**.
- **[FFmpeg](https://ffmpeg.org/)** (Required for HLS downloads).

---

## 🚀 Quick Start

Start the interactive terminal UI:
```bash
meowtv
```

### ⌨️ CLI Commands

**Search & Play:**
```bash
meowtv search "interstellar"
meowtv search "one piece" -p meowtoon
```

**Direct Play:**
```bash
meowtv play <content_id> --player vlc
```

**Downloads:**
```bash
meowtv download <content_id> -o ~/Videos
```

---

## 🏎️ Performance Optimizations (v1.0.8+)

We've recently overhauled the engine for maximum speed:
- **Parallel Fetching**: Fetches all seasons/episodes simultaneously using `asyncio.gather`.
- **HLS Variant Filtering**: Limits stream probing to the top 3 qualities to prevent "14-minute" initial lags.
- **Aggressive Buffering**: Optimized MPV arguments (`--cache-secs=2`) for near-instant playback.

---

## ⚙️ Configuration

Configuration is stored in `~/.config/meowtv/config.json`.
```bash
meowtv config --show
meowtv config --player mpv
```

---

## ⚖️ Disclaimer & License

**Disclaimer**: This tool is for educational purposes only. The developers do not host any content. All content is scraped from third-party publicly available sources.

Licensed under the **MIT License**.

---
<p align="center">Made with ❤️ by the MeowTV Community</p>
