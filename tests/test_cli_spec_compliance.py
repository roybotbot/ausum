import sys
from pathlib import Path

import pytest

import ausum


def test_subcommand_parser_exposes_only_required_subcommands():
    parser = ausum.build_command_parser()
    subparsers_action = next(
        action for action in parser._actions if getattr(action, "choices", None)
    )

    assert set(subparsers_action.choices) == {
        "poll",
        "install-service",
        "uninstall-service",
    }



def test_main_preserves_direct_invocation_without_dl(monkeypatch):
    called = {}

    def fake_process_input(input_arg, outdir=None, read_summary=False):
        called["args"] = (input_arg, outdir, read_summary)
        return 0

    monkeypatch.setattr(ausum, "process_input", fake_process_input)
    monkeypatch.setattr(sys, "argv", ["ausum", "https://example.com/video", "-d", "/tmp/out", "--read"])

    assert ausum.main() == 0
    assert called["args"] == ("https://example.com/video", "/tmp/out", True)



def test_main_help_uses_legacy_direct_cli_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["ausum", "--help"])

    assert ausum.main() == 0

    captured = capsys.readouterr()
    assert "usage: ausum [-h] [-d OUTDIR] [--read] input" in captured.out
    assert "poll" not in captured.out
    assert "install-service" not in captured.out
    assert "uninstall-service" not in captured.out



def test_install_service_only_writes_plist(monkeypatch, tmp_path, capsys):
    plist_path = tmp_path / "Library" / "LaunchAgents" / "com.ausum.poll.plist"
    log_path = tmp_path / ".config" / "ausum" / "poll.log"
    subprocess_calls = []

    def fake_run(*args, **kwargs):
        subprocess_calls.append((args, kwargs))
        raise AssertionError("launchctl should not be called during install-service")

    monkeypatch.setattr(ausum, "_ausum_plist_path", lambda: plist_path)
    monkeypatch.setattr(ausum, "POLL_LOG_PATH", log_path)
    monkeypatch.setattr(ausum.subprocess, "run", fake_run)

    assert ausum.cmd_install_service() == 0

    assert plist_path.exists()
    plist = plist_path.read_text(encoding="utf-8")
    assert "<string>poll</string>" in plist
    assert str(log_path) in plist
    assert subprocess_calls == []

    captured = capsys.readouterr()
    assert f"Installed: {plist_path}" in captured.out
    assert f"Logs at {log_path}" in captured.out
