# ausum - Audio Summarization

Automatically transcribe and summarize any audio or video file using local AI (FluidAudio Parakeet) + Claude. Works with YouTube videos, podcasts, recordings, meetings, lectures - any audio content.

This is a tool built for macOS.

## Why?

Reading is faster than watching videos. For certain types of videos I find it faster to read a detailed summary versus watching the video at a faster speed.

## Features

- **Local speech-to-text** using FluidAudio's Parakeet model (600M parameters, 25 European languages)
- **Automatic summarization** with Claude (falls back to pi if claude is unavailable or not logged in)
- **Privacy-first** - all transcription runs locally on your Mac
- **Simple CLI** - one command to get transcript + summary

## Prerequisites

Install required tools:

```bash
# Package managers (one-time setup)
brew install yt-dlp ffmpeg

# Claude CLI (recommended)
# Follow: https://docs.anthropic.com/claude-cli

# OR pi (used as automatic fallback if claude is unavailable or not logged in)
# Follow: https://github.com/mariozechner/pi

# FluidAudio (build from source)
git clone https://github.com/FluidInference/FluidAudio.git
cd FluidAudio
swift build -c release
```

Set environment variable:

```bash
# Add to ~/.zshrc or ~/.bashrc
export FLUIDAUDIO_PATH=~/path/to/FluidAudio
```

## Installation

```bash
# Clone this repo
git clone https://github.com/roybotbot/ausum.git
cd ausum

# Install with pip
pip install .

# Or with pipx (recommended)
pipx install .
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

# Override saved directory for a single run
ausum "https://www.youtube.com/watch?v=VIDEO_ID" -d ~/my-transcripts

# Open summary in mdv after creation
ausum "https://www.youtube.com/watch?v=VIDEO_ID" --read
```

**Supported formats:** Any audio or video format that ffmpeg can read (mp4, mp3, wav, m4a, webm, mkv, avi, flac, ogg, etc.)

Output files:
- `<video-title>.txt` or `<filename>.txt` - Full transcript
- `<video-title>-summary.md` or `<filename>-summary.md` - Structured summary

## First Run

On your first run, `ausum` will:
1. Ask where summaries should be saved (defaults to `~/Documents` if it exists)
2. Ask where transcripts should be saved (press Enter to use the same directory as summaries)
3. Ask whether to save transcript `.txt` files at all
4. Save preferences to `~/.config/ausum/config.json`
5. Download the Parakeet model (~600MB) from HuggingFace on first transcription

Subsequent runs use your saved preferences. You can always override the output directory for a single run with `-d`.

## Configuration

Preferences are stored in `~/.config/ausum/config.json`. You can edit it directly to change settings without re-running the setup prompt:

```json
{
  "summary_dir": "/path/to/summaries",
  "transcript_dir": "/path/to/transcripts",
  "save_transcript": true
}
```

- **`summary_dir`** — where `.md` summary files are saved
- **`transcript_dir`** — where `.txt` transcript files are saved (optional; if omitted, uses `summary_dir`)
- **`save_transcript`** — set to `false` to skip saving the raw transcript

## Model Storage

The Parakeet model (~460MB) is cached in `~/Library/Application Support/FluidAudio/Models/` and persists across ausum updates. It is NOT deleted when you reinstall ausum with pipx - the cache is managed by FluidAudio, not ausum.

If you need to free up disk space, you can manually delete the cache:
```bash
rm -rf ~/Library/Application\ Support/FluidAudio/Models/parakeet*
```

The model will be re-downloaded on next use.

## Summary Format

Summaries follow the structure defined in `transcript-summary.md`:
- Major sections with short headers
- Concise bullet points of key points
- Step-by-step instructions (if applicable)
- Next steps for learning more

## License

MIT - See LICENSE file
