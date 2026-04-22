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



def test_main_help_exposes_subcommands_and_direct_cli_usage(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["ausum", "--help"])

    assert ausum.main() == 0

    captured = capsys.readouterr()
    assert "usage: ausum [-h] [-d OUTDIR] [--read] input" in captured.out
    assert "Commands:" in captured.out
    assert "poll" in captured.out
    assert "install-service" in captured.out
    assert "uninstall-service" in captured.out



def test_main_prefers_existing_local_path_named_poll(monkeypatch, tmp_path):
    called = {}
    poll_path = tmp_path / "poll"
    poll_path.write_text("audio", encoding="utf-8")

    def fake_process_input(input_arg, outdir=None, read_summary=False):
        called["args"] = (input_arg, outdir, read_summary)
        return 0

    monkeypatch.setattr(ausum, "process_input", fake_process_input)
    monkeypatch.setattr(sys, "argv", ["ausum", str(poll_path)])

    assert ausum.main() == 0
    assert called["args"] == (str(poll_path), None, False)



def test_main_prefers_existing_local_path_named_subcommand_in_cwd(monkeypatch, tmp_path):
    called = {}
    install_path = tmp_path / "install-service"
    install_path.write_text("audio", encoding="utf-8")

    def fake_process_input(input_arg, outdir=None, read_summary=False):
        called["args"] = (input_arg, outdir, read_summary)
        return 0

    monkeypatch.setattr(ausum, "process_input", fake_process_input)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["ausum", "install-service"])

    assert ausum.main() == 0
    assert called["args"] == ("install-service", None, False)



def test_main_uses_subcommand_when_name_is_not_existing_local_path(monkeypatch):
    called = {"poll": 0}

    monkeypatch.setattr(ausum, "cmd_poll", lambda: called.__setitem__("poll", called["poll"] + 1) or 0)
    monkeypatch.setattr(sys, "argv", ["ausum", "poll"])

    assert ausum.main() == 0
    assert called["poll"] == 1



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
