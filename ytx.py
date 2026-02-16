#!/usr/bin/env python3

import os
import shutil
import sys
from pathlib import Path


def check_command(cmd: str) -> bool:
    """Check if a command exists on PATH."""
    return shutil.which(cmd) is not None


def check_prerequisites() -> None:
    """Verify all required tools are available."""
    missing = []
    
    if not check_command("yt-dlp"):
        missing.append("yt-dlp (install: brew install yt-dlp)")
    
    if not check_command("ffmpeg"):
        missing.append("ffmpeg (install: brew install ffmpeg)")
    
    if not check_command("swift"):
        missing.append("swift (comes with Xcode)")
    
    if not check_command("claude"):
        missing.append("claude CLI (https://docs.anthropic.com/claude-cli)")
    
    fluidaudio_path = os.environ.get("FLUIDAUDIO_PATH")
    if not fluidaudio_path:
        missing.append("FLUIDAUDIO_PATH environment variable not set")
    elif not Path(fluidaudio_path).is_dir():
        missing.append(f"FLUIDAUDIO_PATH points to non-existent directory: {fluidaudio_path}")
    elif not (Path(fluidaudio_path) / "Package.swift").exists():
        missing.append(f"No Package.swift found in FLUIDAUDIO_PATH: {fluidaudio_path}")
    
    if missing:
        print("ytx: missing prerequisites:", file=sys.stderr)
        for item in missing:
            print(f"  - {item}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    check_prerequisites()
    print("All prerequisites satisfied")
