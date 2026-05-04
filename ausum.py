#!/usr/bin/env python3

import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import quote


POLL_LABEL = "com.ausum.poll"
POLL_INTERVAL_SECONDS = 1800
POLL_LOG_PATH = Path.home() / ".config" / "ausum" / "poll.log"


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


def queue_fetch(queue_url: str, queue_token: str) -> list[dict]:
    """Fetch pending items from the remote queue."""
    req = urllib.request.Request(
        f"{queue_url.rstrip('/')}/queue",
        headers={"X-Token": queue_token, "User-Agent": "ausum/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    if not isinstance(data, dict):
        raise ValueError("Malformed queue payload: expected JSON object")

    items = data.get("items", [])
    if not isinstance(items, list):
        raise ValueError("Malformed queue payload: items must be a list")

    return items


def queue_delete(queue_url: str, queue_token: str, item_id: str) -> None:
    """Delete a processed item from the remote queue."""
    encoded_item_id = quote(str(item_id), safe="")
    req = urllib.request.Request(
        f"{queue_url.rstrip('/')}/queue/{encoded_item_id}",
        method="DELETE",
        headers={"X-Token": queue_token, "User-Agent": "ausum/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()



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
    """Summarize transcript using pi via RPC mode."""
    prompt = f"{SUMMARY_INSTRUCTIONS}\n\nTranscript:\n\n{transcript}"

    proc = subprocess.Popen(
        ["pi", "--model", "opencode/minimax-m2.5-free", "--thinking", "minimal", "--mode", "rpc", "--no-session"],
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



def process_input(input_arg: str, outdir: str | None = None, read_summary: bool = False) -> int:
    """Process a URL or local file using the existing direct CLI behavior."""
    check_prerequisites()

    if outdir:
        output_dir = Path(outdir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        summary_dir = transcript_dir = output_dir
        save_transcript = True
    else:
        summary_dir, transcript_dir = get_output_dirs()
        config = load_config()
        save_transcript = config.get("save_transcript", True)

    is_remote = is_url(input_arg)

    if is_remote:
        print("Getting video title...", file=sys.stderr)
        title = get_video_title(input_arg)
    else:
        input_path = Path(input_arg).expanduser()
        title = get_file_title(input_path)

    txt_path = transcript_dir / f"{title}.txt"
    summary_path = summary_dir / f"{title}-summary.md"

    with tempfile.TemporaryDirectory(prefix="ausum_") as tmpdir:
        wav_path = Path(tmpdir) / "audio.wav"

        if is_remote:
            print("Downloading and converting audio...", file=sys.stderr)
            download_and_convert_audio(input_arg, wav_path)
        else:
            print("Converting audio...", file=sys.stderr)
            convert_to_wav(input_path, wav_path)

        print("Transcribing audio...", file=sys.stderr)
        transcript = transcribe_audio(wav_path)

    if save_transcript:
        txt_path.write_text(transcript, encoding="utf-8")
        print("Transcript saved:", format_clickable_path(txt_path), file=sys.stderr)

    print("Generating summary...", file=sys.stderr)
    summary = summarize_transcript(transcript)

    source = input_arg.split("?")[0] if is_remote else input_arg
    summary = f"{summary}\n\n---\nSource: {source}"

    summary_path.write_text(summary, encoding="utf-8")
    print("Summary saved:", format_clickable_path(summary_path), file=sys.stderr)

    if save_transcript:
        print(format_clickable_path(txt_path))
    print(format_clickable_path(summary_path))

    if read_summary:
        subprocess.run(["mdv", str(summary_path)])

    return 0



def cmd_poll() -> int:
    """Process queued URLs using the standard ausum flow."""
    config = load_config()

    raw_queue_url = config.get("queue_url")
    raw_queue_token = config.get("queue_token")
    queue_url = raw_queue_url.strip() if isinstance(raw_queue_url, str) else ""
    queue_token = raw_queue_token.strip() if isinstance(raw_queue_token, str) else ""

    if not queue_url or not queue_token:
        print(
            "Error: queue_url and queue_token not configured.\n"
            f"Add them to {get_config_path()}",
            file=sys.stderr,
        )
        return 1

    try:
        summary_dir, transcript_dir = resolve_dirs(config)
        summary_dir.mkdir(parents=True, exist_ok=True)
        transcript_dir.mkdir(parents=True, exist_ok=True)
    except (RuntimeError, TypeError, ValueError):
        print(
            "Error: summary_dir/transcript_dir not configured. "
            "Configure summary_dir and transcript_dir before using poll/install-service.",
            file=sys.stderr,
        )
        return 1

    try:
        items = queue_fetch(queue_url, queue_token)
    except Exception as exc:
        print(f"Error fetching queue: {exc}", file=sys.stderr)
        return 1

    if not isinstance(items, list):
        print("Error fetching queue: Malformed queue payload: items must be a list", file=sys.stderr)
        return 1

    if not items:
        print("No pending URLs.")
        return 0

    processed = 0
    errors = 0
    interrupted = False

    for item in items:
        if not isinstance(item, dict):
            print(f"Skipping malformed queue item: {item}", file=sys.stderr)
            errors += 1
            continue

        item_id = item.get("id")
        url = item.get("url")

        if type(item_id) not in (str, int) or not isinstance(url, str):
            print(f"Skipping malformed queue item: {item}", file=sys.stderr)
            errors += 1
            continue

        normalized_item_id = str(item_id)
        url = url.strip()

        if not normalized_item_id.strip() or not url or not is_url(url):
            print(f"Skipping malformed queue item: {item}", file=sys.stderr)
            errors += 1
            continue

        print(f"\n→ {url}", file=sys.stderr)

        try:
            result = process_input(url)
        except KeyboardInterrupt:
            print("\nInterrupted, leaving remaining items in queue.", file=sys.stderr)
            interrupted = True
            break
        except Exception as exc:
            print(f"  Error: {exc} — will retry next poll", file=sys.stderr)
            errors += 1
            continue

        if result != 0:
            print(f"  Failed with exit code {result}, keeping item in queue", file=sys.stderr)
            errors += 1
            continue

        try:
            queue_delete(queue_url, queue_token, normalized_item_id)
        except KeyboardInterrupt:
            print("\nInterrupted, leaving remaining items in queue.", file=sys.stderr)
            interrupted = True
            break
        except Exception as exc:
            print(
                f"  Processed successfully but failed to acknowledge queue item {item_id}: {exc}",
                file=sys.stderr,
            )
            errors += 1
            continue

        processed += 1

    print(f"\nDone: {processed} processed, {errors} errors.", file=sys.stderr)
    if interrupted:
        return 130
    return 1 if errors else 0



def _ausum_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{POLL_LABEL}.plist"



def cmd_install_service() -> int:
    """Create a launchd plist that runs ausum poll every 30 minutes."""
    plist_path = _ausum_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    POLL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    python_bin = Path(sys.executable).resolve()
    script_path = Path(__file__).resolve()

    plist = {
        "Label": POLL_LABEL,
        "ProgramArguments": [str(python_bin), str(script_path), "poll"],
        "StartInterval": POLL_INTERVAL_SECONDS,
        "RunAtLoad": True,
        "StandardOutPath": str(POLL_LOG_PATH),
        "StandardErrorPath": str(POLL_LOG_PATH),
    }

    plist_path.write_bytes(plistlib.dumps(plist))
    print(f"Installed: {plist_path}")
    print(f"ausum poll will run every 30 minutes. Logs at {POLL_LOG_PATH}")
    return 0



def cmd_uninstall_service() -> int:
    """Unload and remove the launchd plist."""
    plist_path = _ausum_plist_path()
    if not plist_path.exists():
        print("Not installed — nothing to remove.")
        return 0

    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    plist_path.unlink()
    print(f"Unloaded and removed {plist_path}")
    return 0



def build_command_parser() -> argparse.ArgumentParser:
    """Build parser for management subcommands."""
    parser = argparse.ArgumentParser(
        prog="ausum",
        description="Transcribe and summarize audio/video files or YouTube videos using whisper.cpp + pi"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    subparsers.add_parser("poll", help="Process URLs queued from your phone")
    subparsers.add_parser("install-service", help="Install launchd plist for auto-polling")
    subparsers.add_parser("uninstall-service", help="Remove launchd plist")
    return parser



def build_legacy_parser() -> argparse.ArgumentParser:
    """Build parser for the original direct CLI form."""
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
    return parser



def print_main_help() -> None:
    """Print direct CLI help plus discoverable management subcommands."""
    build_legacy_parser().print_help()
    print("\nCommands:")
    print("  poll               Process URLs queued from your phone")
    print("  install-service    Install launchd plist for auto-polling")
    print("  uninstall-service  Remove launchd plist")



def should_run_subcommand(first_arg: str, command_names: set[str]) -> bool:
    """Return True only when the arg is a command name and not an existing local path."""
    if first_arg not in command_names:
        return False
    return not Path(first_arg).expanduser().exists()



def main() -> int:
    """Main CLI entry point."""
    argv = sys.argv[1:]
    command_names = {"poll", "install-service", "uninstall-service"}

    if argv and argv[0] in {"-h", "--help"}:
        print_main_help()
        return 0

    if argv and should_run_subcommand(argv[0], command_names):
        args = build_command_parser().parse_args(argv)

        if args.command == "poll":
            return cmd_poll()
        if args.command == "install-service":
            return cmd_install_service()
        if args.command == "uninstall-service":
            return cmd_uninstall_service()

    args = build_legacy_parser().parse_args(argv)
    return process_input(args.input, outdir=args.outdir, read_summary=args.read)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"ausum: error: {e}", file=sys.stderr)
        sys.exit(1)
