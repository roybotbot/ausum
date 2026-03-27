# ausum - Audio Summarization

Automatically transcribe and summarize any audio or video file using local transcription (whisper.cpp) and AI summarization (Anthropic Claude or OpenAI ChatGPT). Works with YouTube videos, podcasts, recordings, meetings, lectures - any audio content.

This is a tool built for macOS.

## Why?

Reading is faster than watching videos. For certain types of videos I find it faster to read a detailed summary versus watching the video at a faster speed.

## Features

- **Local speech-to-text** using [whisper.cpp](https://github.com/ggml-org/whisper.cpp) with Metal GPU acceleration
- **AI summarization** via Anthropic Claude or OpenAI ChatGPT APIs with live streaming output
- **Privacy-first** - all transcription runs locally on your Mac
- **Simple CLI** - one command to get transcript + summary

## Prerequisites

Install required tools:

```bash
# Package managers (one-time setup)
brew install yt-dlp ffmpeg

# whisper.cpp (build from source)
git clone https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp
cmake -B build -DWHISPER_METAL=ON
cmake --build build --config Release

# Download a whisper model
bash models/download-ggml-model.sh large-v3-turbo
```

Set environment variables:

```bash
# Add to ~/.zshrc or ~/.bashrc

# whisper.cpp
export WHISPER_CLI=~/path/to/whisper.cpp/build/bin/whisper-cli
export WHISPER_MODEL=~/path/to/whisper.cpp/models/ggml-large-v3-turbo.bin

# One of these, depending on your chosen provider:
export ANTHROPIC_API_KEY="your-key"   # https://console.anthropic.com
export OPENAI_API_KEY="your-key"      # https://platform.openai.com/api-keys
```

## Installation

```bash
# Clone this repo
git clone https://github.com/roybotbot/ausum.git
cd ausum

# Install with pipx (recommended)
pipx install .

# Or with pip
pip install .
```

## Usage

```bash
# YouTube videos
ausum "https://www.youtube.com/watch?v=VIDEO_ID"

# YouTube videos with playlist in URL (only processes the single video)
ausum "https://www.youtube.com/watch?v=VIDEO_ID&list=PLAYLIST_ID"

# Local audio/video files
ausum /path/to/video.mp4
ausum ~/Downloads/podcast.mp3
ausum ./recording.wav

# Override provider or model for a single run
ausum --provider openai --model gpt-4o "https://www.youtube.com/watch?v=VIDEO_ID"

# Override saved directory for a single run
ausum "https://www.youtube.com/watch?v=VIDEO_ID" -d ~/my-transcripts

# Open summary in mdv after creation
ausum "https://www.youtube.com/watch?v=VIDEO_ID" --read
```

**Supported formats:** Any audio or video format that ffmpeg can read (mp4, mp3, wav, m4a, webm, mkv, avi, flac, ogg, etc.)

Output files:
- `<title>.txt` - Full transcript
- `<title>-summary.md` - Structured summary

## First Run

On your first run, `ausum` will:
1. Ask where summaries should be saved (defaults to `~/Documents` if it exists)
2. Ask where transcripts should be saved (press Enter to use the same directory)
3. Ask whether to save transcript `.txt` files at all
4. Ask which AI provider to use (Anthropic Claude or OpenAI ChatGPT)
5. Ask which model to use (with links to model docs)

Subsequent runs use your saved preferences. You can override provider, model, or output directory per-run with flags.

## Configuration

Preferences are stored in `~/.config/ausum/config.json`. You can edit it directly:

```json
{
  "summary_dir": "/path/to/summaries",
  "transcript_dir": "/path/to/transcripts",
  "save_transcript": true,
  "provider": "anthropic",
  "model": "claude-sonnet-4-6"
}
```

- **`summary_dir`** — where `.md` summary files are saved
- **`transcript_dir`** — where `.txt` transcript files are saved (optional; if omitted, uses `summary_dir`)
- **`save_transcript`** — set to `false` to skip saving the raw transcript
- **`provider`** — `"anthropic"` or `"openai"`
- **`model`** — model ID to use for summarization
  - Anthropic models: https://platform.claude.com/docs/en/about-claude/models/overview
  - OpenAI models: https://developers.openai.com/api/docs/models

## Summary Format

Summaries follow a structured format:
- **Overview** — bullet list of high-level concepts and key takeaways
- **Detailed Summary** — major sections with descriptive headers and detailed bullets
- **Next Steps** — actionable recommendations for learning more

Each summary includes a source link at the bottom.

## License

MIT - See LICENSE file
