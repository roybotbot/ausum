#!/usr/bin/env python3

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def format_clickable_path(path: Path) -> str:
    """Return a shell-escaped path that terminals can usually click as one token."""
    return re.sub(r'([\s\\"\'\(\)\[\]\{\}&;])', r'\\\1', str(path))


SUMMARY_INSTRUCTIONS = """Create a comprehensive markdown summary of the following transcript. Output ONLY the markdown summary, no meta-commentary.

Structure:

1. **Overview** (bullet list)
   - High-level concepts and first principles as skimmable bullets
   - Core thesis or central argument
   - Key takeaways and why this matters
   - Each bullet should be a complete, standalone point

2. **Detailed Summary**
   - Major sections with descriptive headers
   - Under each section, detailed bullets that explain:
     * What the concept/point is
     * Why it matters
     * How it works or applies
     * Examples or context from the transcript
   - If the transcript describes building/making/producing anything, include a clear step-by-step numbered list with explanations
   - Include relevant quotes, data, or specific examples mentioned

3. **Next Steps**
   - Actionable recommendations for learning more
   - Key resources or concepts to explore further

Requirements:
- Add substance to each bullet - avoid sparse one-liners
- Stay factual - no filler or invented content
- Output the summary directly - do not describe what you would do
- Do not ask for confirmation or approval
- Start immediately with" #[Title of Youtube Video] - Summary
- Then begin first section with "## Overview" """


def get_config_path() -> Path:
    """Get path to config file."""
    config_dir = Path.home() / ".config" / "ausum"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"


def load_config() -> dict:
    """Load config from file or return empty dict."""
    config_path = get_config_path()
    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_config(config: dict) -> None:
    """Save config to file."""
    config_path = get_config_path()
    config_path.write_text(json.dumps(config, indent=2))


def resolve_dirs(config: dict) -> tuple[Path, Path]:
    """Resolve (summary_dir, transcript_dir) from config.

    If only one dir is configured, both outputs go there.
    """
    raw_summary = config.get("summary_dir") or config.get("output_dir")  # migrate old key
    raw_transcript = config.get("transcript_dir")

    if not raw_summary and not raw_transcript:
        raise RuntimeError("No output directory configured")

    summary_dir = Path(raw_summary).expanduser() if raw_summary else Path(raw_transcript).expanduser()
    transcript_dir = Path(raw_transcript).expanduser() if raw_transcript else summary_dir

    return summary_dir, transcript_dir


def get_output_dirs() -> tuple[Path, Path]:
    """Return (summary_dir, transcript_dir), prompting on first run."""
    config = load_config()

    # Migrate old single output_dir key
    if "output_dir" in config and "summary_dir" not in config:
        config["summary_dir"] = config.pop("output_dir")
        save_config(config)

    if "summary_dir" in config or "transcript_dir" in config:
        summary_dir, transcript_dir = resolve_dirs(config)
        summary_dir.mkdir(parents=True, exist_ok=True)
        transcript_dir.mkdir(parents=True, exist_ok=True)
        return summary_dir, transcript_dir

    # First run — prompt
    default_dir = Path("~/Documents").expanduser()
    default_hint = f" (default: {default_dir})" if default_dir.exists() else ""

    print("First run setup:", file=sys.stderr)

    raw = input(f"Where should summaries be saved?{default_hint}\nPress Enter for default, or enter a path: ").strip()
    if raw:
        summary_dir = Path(raw).expanduser()
    elif default_dir.exists():
        summary_dir = default_dir
    else:
        print("No default directory available. Please enter a valid path.", file=sys.stderr)
        sys.exit(1)

    raw = input("Where should transcripts be saved? (press Enter to use summary directory): ").strip()
    transcript_dir = Path(raw).expanduser() if raw else summary_dir

    raw = input("Save transcript .txt files? [Y/n]: ").strip().lower()
    save_transcript = raw != "n"

    summary_dir.mkdir(parents=True, exist_ok=True)
    transcript_dir.mkdir(parents=True, exist_ok=True)

    config["summary_dir"] = str(summary_dir)
    config["transcript_dir"] = str(transcript_dir)
    config["save_transcript"] = save_transcript
    save_config(config)

    print(f"\nSummaries → {summary_dir}", file=sys.stderr)
    print(f"Transcripts → {transcript_dir}", file=sys.stderr)
    print(f"Save transcripts: {save_transcript}", file=sys.stderr)

    return summary_dir, transcript_dir


def check_prerequisites() -> None:
    """Verify all required tools are available."""
    missing = []

    if not shutil.which("yt-dlp"):
        missing.append("yt-dlp (install: brew install yt-dlp)")

    if not shutil.which("ffmpeg"):
        missing.append("ffmpeg (install: brew install ffmpeg)")

    if not shutil.which("pi"):
        missing.append("pi (https://github.com/mariozechner/pi-coding-agent)")

    whisper_cli = os.environ.get("WHISPER_CLI", shutil.which("whisper-cli"))
    if not whisper_cli or not Path(whisper_cli).is_file():
        missing.append("whisper-cli binary not found (set WHISPER_CLI env var or add to PATH)")

    whisper_model = os.environ.get("WHISPER_MODEL")
    if not whisper_model:
        missing.append("WHISPER_MODEL environment variable not set (path to .bin model file)")
    elif not Path(whisper_model).is_file():
        missing.append(f"WHISPER_MODEL points to non-existent file: {whisper_model}")

    if missing:
        print("ausum: missing prerequisites:", file=sys.stderr)
        for item in missing:
            print(f"  - {item}", file=sys.stderr)
        sys.exit(1)


def sanitize_filename(name: str, max_len: int = 180) -> str:
    """Sanitize a string for use as a filename."""
    name = name.strip()
    name = re.sub(r'[\/:\*\?"<>\|]', "-", name)
    name = re.sub(r'\s+', " ", name)
    name = re.sub(r'\.+$', "", name)
    if not name:
        name = "untitled"
    if len(name) > max_len:
        name = name[:max_len].rstrip()
    return name


def is_url(input_str: str) -> bool:
    """Check if input is a URL."""
    return input_str.startswith(("http://", "https://", "www."))


def get_video_title(url: str) -> str:
    """Get video title from URL."""
    result = subprocess.run(
        ["yt-dlp", "--no-warnings", "--impersonate", "chrome-131", "--no-playlist", "--print", "%(title)s", url],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "Unsupported URL" in stderr or "Unable to extract" in stderr or "no video" in stderr.lower():
            raise RuntimeError(f"No video found at URL (site may require JavaScript or use an unsupported player): {url}")
        raise RuntimeError(f"Failed to get video title: {stderr}")

    title = result.stdout.strip()
    return sanitize_filename(title) if title else "untitled"


def get_file_title(file_path: Path) -> str:
    """Get title from local file path (filename without extension)."""
    return sanitize_filename(file_path.stem)


def convert_to_wav(input_file: Path, output_wav: Path) -> None:
    """Convert audio/video file to 16kHz mono WAV."""
    if not input_file.exists():
        raise RuntimeError(f"File not found: {input_file}")

    result = subprocess.run(
        ["ffmpeg", "-i", str(input_file), "-ar", "16000", "-ac", "1", "-y", str(output_wav)],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to convert audio: {result.stderr.strip()}")


def download_and_convert_audio(url: str, output_wav: Path) -> None:
    """Download YouTube audio and convert to 16kHz mono WAV."""
    with tempfile.TemporaryDirectory(prefix="ausum_") as tmpdir:
        # Download as best audio
        audio_file = Path(tmpdir) / "audio"
        result = subprocess.run(
            [
                "yt-dlp",
                "--no-warnings",
                "--impersonate", "chrome-131",
                "--no-playlist",
                "-f", "bestaudio/best",
                "-o", str(audio_file) + ".%(ext)s",
                url,
            ],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "Unsupported URL" in stderr or "Unable to extract" in stderr or "no video" in stderr.lower():
                raise RuntimeError(f"No video found at URL (site may require JavaScript or use an unsupported player): {url}")
            raise RuntimeError(f"Failed to download audio: {stderr}")

        # Find the actual downloaded file (yt-dlp may or may not add extension)
        matches = list(Path(tmpdir).glob("audio*"))
        if not matches:
            raise RuntimeError("Audio downloaded but file not found")

        convert_to_wav(matches[0], output_wav)


def transcribe_audio(wav_path: Path) -> str:
    """Transcribe audio using whisper.cpp."""
    whisper_cli = os.environ.get("WHISPER_CLI") or shutil.which("whisper-cli")
    whisper_model = os.environ["WHISPER_MODEL"]

    result = subprocess.run(
        [whisper_cli, "-m", whisper_model, "-f", str(wav_path), "--output-txt", "--no-prints", "-of", str(wav_path)],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f"Transcription failed: {result.stderr.strip()}")

    # whisper-cli writes <file>.txt alongside the input file
    txt_output = Path(str(wav_path) + ".txt")
    if not txt_output.exists():
        raise RuntimeError("Transcription produced no output file")

    transcript = txt_output.read_text(encoding="utf-8").strip()
    txt_output.unlink()

    if not transcript:
        raise RuntimeError("Transcription produced no output")

    return transcript


def summarize_transcript(transcript: str) -> str:
    """Summarize transcript using pi via RPC mode with kimi-k2.5 model."""
    prompt = f"{SUMMARY_INSTRUCTIONS}\n\nTranscript:\n\n{transcript}"

    proc = subprocess.Popen(
        ["pi", "--model", "opencode-go/kimi-k2.5", "--mode", "rpc", "--no-session"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True
    )

    proc.stdin.write(json.dumps({"type": "prompt", "message": prompt}) + "\n")
    proc.stdin.flush()

    chunks = []
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if event.get("type") == "message_update":
            delta = event.get("assistantMessageEvent", {})
            if delta.get("type") == "text_delta":
                chunk = delta.get("delta", "")
                chunks.append(chunk)
                print(chunk, end="", flush=True, file=sys.stderr)

        if event.get("type") == "agent_end":
            break

    proc.terminate()
    proc.wait()
    print(file=sys.stderr)

    summary = "".join(chunks).strip()
    if not summary:
        raise RuntimeError("Summarization produced no output")

    return summary


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="ausum",
        description="Transcribe and summarize audio/video files or YouTube videos using whisper.cpp + pi"
    )
    parser.add_argument("input", help="YouTube URL or path to local audio/video file")
    parser.add_argument(
        "-d", "--outdir",
        help="Output directory (overrides saved preference)"
    )
    parser.add_argument(
        "--read",
        action="store_true",
        help="Open the summary in mdv after it's created"
    )

    args = parser.parse_args()

    # Check prerequisites
    check_prerequisites()

    # Setup output directories
    if args.outdir:
        outdir = Path(args.outdir).expanduser()
        outdir.mkdir(parents=True, exist_ok=True)
        summary_dir = transcript_dir = outdir
        save_transcript = True
    else:
        summary_dir, transcript_dir = get_output_dirs()
        config = load_config()
        save_transcript = config.get("save_transcript", True)

    # Determine if input is URL or local file
    is_remote = is_url(args.input)

    # Get title for filenames
    if is_remote:
        print("Getting video title...", file=sys.stderr)
        title = get_video_title(args.input)
    else:
        input_path = Path(args.input).expanduser()
        title = get_file_title(input_path)

    txt_path = transcript_dir / f"{title}.txt"
    summary_path = summary_dir / f"{title}-summary.md"

    # Process audio
    with tempfile.TemporaryDirectory(prefix="ausum_") as tmpdir:
        wav_path = Path(tmpdir) / "audio.wav"

        if is_remote:
            print("Downloading and converting audio...", file=sys.stderr)
            download_and_convert_audio(args.input, wav_path)
        else:
            print("Converting audio...", file=sys.stderr)
            convert_to_wav(input_path, wav_path)

        print("Transcribing audio...", file=sys.stderr)
        transcript = transcribe_audio(wav_path)

    # Save transcript (optional)
    if save_transcript:
        txt_path.write_text(transcript, encoding="utf-8")
        print("Transcript saved:", format_clickable_path(txt_path), file=sys.stderr)

    # Summarize
    print("Generating summary...", file=sys.stderr)
    summary = summarize_transcript(transcript)

    # Append source footer
    source = args.input.split("?")[0] if is_remote else args.input
    summary = f"{summary}\n\n---\nSource: {source}"

    # Save summary
    summary_path.write_text(summary, encoding="utf-8")
    print("Summary saved:", format_clickable_path(summary_path), file=sys.stderr)

    # Print output paths
    if save_transcript:
        print(format_clickable_path(txt_path))
    print(format_clickable_path(summary_path))

    if args.read:
        subprocess.run(["mdv", str(summary_path)])

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"ausum: error: {e}", file=sys.stderr)
        sys.exit(1)
