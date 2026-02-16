# YTX: Parakeet Transcription + Claude Summarization

## Overview

Replace YouTube caption downloading with local speech-to-text using FluidAudio's Parakeet model, followed by automatic Claude summarization.

## Pipeline

`ytx <youtube-url>` runs four steps:

1. **Get video title** — `yt-dlp --print %(title)s` for output file naming.
2. **Extract audio** — `yt-dlp` downloads best audio, `ffmpeg` converts to 16kHz mono `.wav` in a temp directory.
3. **Transcribe** — `swift run fluidaudio transcribe <audio.wav>` from `FLUIDAUDIO_PATH`. Saves `<title>.txt` to output directory.
4. **Summarize** — `claude -p` with transcript + instructions from bundled `transcript-summary.md`. Saves `<title>-summary.md` to output directory.

## CLI Interface

```
ytx <url>            # full pipeline, default output dir
ytx <url> -d ~/out   # custom output directory
```

Default output: `~/Documents/Transcripts/Youtube`

Old flags removed (`-l`, `-a`, `--keep-vtt`). Caption-download code removed entirely.

## Prerequisites

- `yt-dlp`
- `ffmpeg`
- FluidAudio built from source (`FLUIDAUDIO_PATH` env var pointing to repo)
- `claude` CLI

All checked upfront before any work begins.

## File Structure

```
ytx-caption-downloader/
├── ytx.py                  # all logic
├── transcript-summary.md   # Claude summarization instructions
├── pyproject.toml           # pip install creates `ytx` command
├── README.md
└── LICENSE
```

`transcript-summary.md` located at runtime via `Path(__file__).parent / "transcript-summary.md"`.

## Parakeet Model Download

FluidAudio auto-downloads the Parakeet model (~600MB) from HuggingFace on first use. Cached in `~/.cache/huggingface/hub/models--FluidInference--parakeet-tdt*`.

On first run, `ytx` detects the missing cache and prints: "Downloading Parakeet model (~600MB), this only happens once..."

## Transcription Details

- `ffmpeg` converts audio to 16kHz mono wav (FluidAudio's expected format).
- Runs `swift run fluidaudio transcribe` with `cwd=FLUIDAUDIO_PATH`.
- Captures stdout as transcript text.
- Temp audio files cleaned up after transcription.

## Summarization Details

- Reads `transcript-summary.md` for instructions.
- Calls `claude -p "<instructions>\n\nTranscript:\n<text>"`.
- Captures stdout, saves as `<title>-summary.md`.
- If `claude` fails, transcript `.txt` is already saved.

## Error Handling

All prerequisites checked upfront. Clear error messages at each step:

- Missing tools → install instructions
- `FLUIDAUDIO_PATH` not set or invalid → setup instructions
- Download/transcription/summarization failures → surface underlying tool errors
- Empty transcript → explicit error message
