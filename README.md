# FluxDL

[English](README.md) · [简体中文](README.zh-CN.md)

A private, local-first web interface for [yt-dlp](https://github.com/yt-dlp/yt-dlp). FluxDL lets you inspect and download supported videos from a browser, then create and translate subtitles locally.

> [!IMPORTANT]
> Download only content you own or are authorized to save. Follow the source website's terms of service and applicable laws.

## Features

- Inspect titles, thumbnails, duration, creator information, and available qualities.
- Download the best available quality or choose 4K, 2K, 1080p, 720p, or 480p.
- Save video as MP4 or MKV, or extract MP3, M4A, Opus, and WAV audio.
- Track progress, transfer speed, and estimated time; cancel active jobs.
- Optionally download existing subtitles and embed thumbnails.
- Generate subtitles from videos without captions using Faster-Whisper.
- Translate subtitles to Simplified Chinese with Argos Translate.
- Export SRT files or create MKV files with switchable subtitle tracks.
- Keep download history, models, media, and processing state on your machine.
- Listen on `127.0.0.1` by default.

## Requirements

- Python 3.10 or newer
- [uv](https://docs.astral.sh/uv/) (recommended)
- [FFmpeg](https://ffmpeg.org/) for high-quality audio/video merging, audio extraction, thumbnail embedding, and AI subtitles

Install FFmpeg with one of the following:

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg

# Windows
winget install Gyan.FFmpeg
```

## Quick start

### macOS and Linux

```bash
git clone <your-repository-url>
cd fluxdl
chmod +x start.sh
./start.sh
```

The launcher uses `uv` when available. Otherwise it creates `.venv` and installs the project with `pip`.

### Windows

```powershell
git clone <your-repository-url>
cd fluxdl
py -m venv .venv
.\.venv\Scripts\python -m pip install --editable .
.\.venv\Scripts\fluxdl
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765) after the server starts.

## AI-generated subtitles

Open a completed video task and select **AI subtitles**. FluxDL can create:

- an original-language SRT file;
- a Simplified Chinese SRT file;
- a bilingual SRT file; and
- an MKV copy with switchable subtitle tracks.

Available Faster-Whisper model presets:

| Model | Approximate download | Notes |
| --- | ---: | --- |
| Tiny | 75 MB | Fastest, lower accuracy |
| Base | 145 MB | Balanced default |
| Small | 460 MB | More accurate, slower |

The selected speech model is downloaded on first use. Chinese or bilingual output also requires an Argos Translate language package. After the models are present, transcription and translation run locally; the extracted audio is not uploaded by FluxDL.

## Configuration

Copy `.env.example` as a reference or set environment variables before starting:

| Variable | Default | Description |
| --- | --- | --- |
| `FLUXDL_HOST` | `127.0.0.1` | HTTP listen address |
| `FLUXDL_PORT` | `8765` | HTTP listen port |
| `FLUXDL_HOME` | current directory | Runtime data and model root |
| `FLUXDL_DOWNLOAD_DIR` | `<FLUXDL_HOME>/downloads` | Download destination |

Example:

```bash
FLUXDL_PORT=9000 FLUXDL_DOWNLOAD_DIR="$HOME/Downloads" ./start.sh
```

Setting `FLUXDL_HOST=0.0.0.0` makes the app reachable from your network. Do this only on a trusted network; FluxDL does not include authentication.

## Project layout

```text
.
├── src/fluxdl/
│   ├── server.py              # HTTP server, yt-dlp jobs, and API
│   ├── subtitle_engine.py     # Local transcription and translation
│   └── static/                # Browser interface
├── tests/                     # Unit tests
├── downloads/                 # Local media (ignored by Git)
├── .data/                     # Runtime history and temporary audio
├── .models/                   # Local speech models
├── pyproject.toml             # Package metadata and dependencies
└── start.sh                   # macOS/Linux launcher
```

## Development

```bash
uv sync
uv run python -m unittest discover -s tests -v
uv run fluxdl
```

The web interface uses plain HTML, CSS, and JavaScript, so there is no separate frontend build step.

## Security and privacy

FluxDL is designed as a single-user local application, not a hardened public service. Keep the default loopback address unless you understand the risks. See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening an issue or pull request.

## Acknowledgements

FluxDL is powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp), [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper), [Argos Translate](https://github.com/argosopentech/argos-translate), and [FFmpeg](https://ffmpeg.org/). FluxDL is an independent project and is not affiliated with those projects or supported websites.

## License

Released under the [MIT License](LICENSE).
