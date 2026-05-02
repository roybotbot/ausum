import plistlib
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
    plist = plistlib.loads(plist_path.read_bytes())
    assert plist["ProgramArguments"][-1] == "poll"
    assert plist["StandardOutPath"] == str(log_path)
    assert plist["StandardErrorPath"] == str(log_path)
    assert subprocess_calls == []

    captured = capsys.readouterr()
    assert f"Installed: {plist_path}" in captured.out
    assert f"Logs at {log_path}" in captured.out



def test_cmd_poll_returns_nonzero_when_queue_delete_fails_after_processing(monkeypatch, capsys):
    monkeypatch.setattr(
        ausum,
        "load_config",
        lambda: {
            "queue_url": "https://queue.example",
            "queue_token": "secret",
            "summary_dir": "/tmp/summaries",
            "transcript_dir": "/tmp/transcripts",
        },
    )
    monkeypatch.setattr(ausum, "queue_fetch", lambda *_: [{"id": "123", "url": "https://example.com/video"}])
    monkeypatch.setattr(ausum, "process_input", lambda *_args, **_kwargs: 0)

    def fail_delete(*_args, **_kwargs):
        raise RuntimeError("delete failed")

    monkeypatch.setattr(ausum, "queue_delete", fail_delete)

    assert ausum.cmd_poll() == 1

    captured = capsys.readouterr()
    assert "Processed successfully but failed to acknowledge queue item 123" in captured.err
    assert "Done: 0 processed, 1 errors." in captured.err



def test_cmd_poll_skips_malformed_queue_items_and_payload(monkeypatch, capsys):
    monkeypatch.setattr(
        ausum,
        "load_config",
        lambda: {
            "queue_url": "https://queue.example",
            "queue_token": "secret",
            "summary_dir": "/tmp/summaries",
            "transcript_dir": "/tmp/transcripts",
        },
    )

    fetches = iter([
        "not-a-list",
        [None, {"id": "missing-url"}, {"url": "missing-id"}, {"id": "ok", "url": "https://example.com/video"}],
    ])

    monkeypatch.setattr(ausum, "queue_fetch", lambda *_: next(fetches))
    monkeypatch.setattr(ausum, "process_input", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(ausum, "queue_delete", lambda *_args, **_kwargs: None)

    assert ausum.cmd_poll() == 1
    first = capsys.readouterr()
    assert "Malformed queue payload: items must be a list" in first.err

    assert ausum.cmd_poll() == 1
    second = capsys.readouterr()
    assert "Skipping malformed queue item: None" in second.err
    assert "Skipping malformed queue item: {'id': 'missing-url'}" in second.err
    assert "Skipping malformed queue item: {'url': 'missing-id'}" in second.err
    assert "Done: 1 processed, 3 errors." in second.err



def test_cmd_poll_treats_non_string_url_as_malformed(monkeypatch, capsys):
    monkeypatch.setattr(
        ausum,
        "load_config",
        lambda: {
            "queue_url": "https://queue.example",
            "queue_token": "secret",
            "summary_dir": "/tmp/summaries",
            "transcript_dir": "/tmp/transcripts",
        },
    )
    monkeypatch.setattr(
        ausum,
        "queue_fetch",
        lambda *_: [
            {"id": "123", "url": 42},
            {"id": "ok", "url": "https://example.com/video"},
        ],
    )

    calls = {"processed": [], "deleted": []}
    monkeypatch.setattr(
        ausum,
        "process_input",
        lambda url, *_args, **_kwargs: calls["processed"].append(url) or 0,
    )
    monkeypatch.setattr(
        ausum,
        "queue_delete",
        lambda *_args: calls["deleted"].append(_args[-1]),
    )

    assert ausum.cmd_poll() == 1
    assert calls["processed"] == ["https://example.com/video"]
    assert calls["deleted"] == ["ok"]

    captured = capsys.readouterr()
    assert "Skipping malformed queue item: {'id': '123', 'url': 42}" in captured.err
    assert "Done: 1 processed, 1 errors." in captured.err



def test_cmd_poll_skips_non_url_string_values_as_malformed(monkeypatch, capsys):
    monkeypatch.setattr(
        ausum,
        "load_config",
        lambda: {
            "queue_url": "https://queue.example",
            "queue_token": "secret",
            "summary_dir": "/tmp/summaries",
            "transcript_dir": "/tmp/transcripts",
        },
    )
    monkeypatch.setattr(
        ausum,
        "queue_fetch",
        lambda *_: [
            {"id": "readme", "url": "README.md"},
            {"id": "bad", "url": "not-a-url"},
            {"id": "ok", "url": "https://example.com/video"},
        ],
    )

    calls = {"processed": [], "deleted": []}
    monkeypatch.setattr(
        ausum,
        "process_input",
        lambda url, *_args, **_kwargs: calls["processed"].append(url) or 0,
    )
    monkeypatch.setattr(
        ausum,
        "queue_delete",
        lambda *_args: calls["deleted"].append(_args[-1]),
    )

    assert ausum.cmd_poll() == 1
    assert calls["processed"] == ["https://example.com/video"]
    assert calls["deleted"] == ["ok"]

    captured = capsys.readouterr()
    assert "Skipping malformed queue item: {'id': 'readme', 'url': 'README.md'}" in captured.err
    assert "Skipping malformed queue item: {'id': 'bad', 'url': 'not-a-url'}" in captured.err
    assert "Done: 1 processed, 2 errors." in captured.err



def test_cmd_poll_skips_invalid_item_id_scalar_types(monkeypatch, capsys):
    monkeypatch.setattr(
        ausum,
        "load_config",
        lambda: {
            "queue_url": "https://queue.example",
            "queue_token": "secret",
            "summary_dir": "/tmp/summaries",
            "transcript_dir": "/tmp/transcripts",
        },
    )
    monkeypatch.setattr(
        ausum,
        "queue_fetch",
        lambda *_: [
            {"id": False, "url": "https://example.com/false"},
            {"id": [], "url": "https://example.com/list"},
            {"id": {}, "url": "https://example.com/dict"},
            {"id": 1.5, "url": "https://example.com/float"},
            {"id": "ok", "url": "https://example.com/video"},
        ],
    )

    calls = {"processed": [], "deleted": []}
    monkeypatch.setattr(
        ausum,
        "process_input",
        lambda url, *_args, **_kwargs: calls["processed"].append(url) or 0,
    )
    monkeypatch.setattr(
        ausum,
        "queue_delete",
        lambda *_args: calls["deleted"].append(_args[-1]),
    )

    assert ausum.cmd_poll() == 1
    assert calls["processed"] == ["https://example.com/video"]
    assert calls["deleted"] == ["ok"]

    captured = capsys.readouterr()
    assert "Skipping malformed queue item: {'id': False, 'url': 'https://example.com/false'}" in captured.err
    assert "Skipping malformed queue item: {'id': [], 'url': 'https://example.com/list'}" in captured.err
    assert "Skipping malformed queue item: {'id': {}, 'url': 'https://example.com/dict'}" in captured.err
    assert "Skipping malformed queue item: {'id': 1.5, 'url': 'https://example.com/float'}" in captured.err
    assert "Done: 1 processed, 4 errors." in captured.err



def test_cmd_poll_returns_nonzero_on_partial_processing_failure(monkeypatch, capsys):
    monkeypatch.setattr(
        ausum,
        "load_config",
        lambda: {
            "queue_url": "https://queue.example",
            "queue_token": "secret",
            "summary_dir": "/tmp/summaries",
            "transcript_dir": "/tmp/transcripts",
        },
    )
    monkeypatch.setattr(
        ausum,
        "queue_fetch",
        lambda *_: [
            {"id": "ok", "url": "https://example.com/ok"},
            {"id": "bad", "url": "https://example.com/bad"},
        ],
    )

    def fake_process_input(url, *_args, **_kwargs):
        return 2 if url.endswith("/bad") else 0

    deleted = []
    monkeypatch.setattr(ausum, "process_input", fake_process_input)
    monkeypatch.setattr(ausum, "queue_delete", lambda *_args: deleted.append(_args[-1]))

    assert ausum.cmd_poll() == 1
    assert deleted == ["ok"]

    captured = capsys.readouterr()
    assert "Failed with exit code 2, keeping item in queue" in captured.err
    assert "Done: 1 processed, 1 errors." in captured.err



def test_cmd_poll_is_noninteractive_when_output_dirs_unconfigured(monkeypatch, capsys):
    monkeypatch.setattr(
        ausum,
        "load_config",
        lambda: {"queue_url": "https://queue.example", "queue_token": "secret"},
    )

    def fail_queue_fetch(*_args, **_kwargs):
        raise AssertionError("queue_fetch should not be called when output dirs are missing")

    def fail_process_input(*_args, **_kwargs):
        raise AssertionError("process_input should not be called when output dirs are missing")

    def fail_input(*_args, **_kwargs):
        raise AssertionError("input should not be called during poll")

    monkeypatch.setattr(ausum, "queue_fetch", fail_queue_fetch)
    monkeypatch.setattr(ausum, "process_input", fail_process_input)
    monkeypatch.setattr("builtins.input", fail_input)

    assert ausum.cmd_poll() == 1

    captured = capsys.readouterr()
    assert "summary_dir/transcript_dir" in captured.err
    assert "poll/install-service" in captured.err


def test_cmd_poll_rejects_non_string_queue_config(monkeypatch, capsys):
    monkeypatch.setattr(
        ausum,
        "load_config",
        lambda: {
            "queue_url": None,
            "queue_token": "secret",
            "summary_dir": "/tmp/summaries",
            "transcript_dir": "/tmp/transcripts",
        },
    )

    def fail_queue_fetch(*_args, **_kwargs):
        raise AssertionError("queue_fetch should not be called when queue config is invalid")

    monkeypatch.setattr(ausum, "queue_fetch", fail_queue_fetch)

    assert ausum.cmd_poll() == 1

    captured = capsys.readouterr()
    assert "queue_url and queue_token not configured" in captured.err


def test_cmd_poll_rejects_non_string_output_dirs_noninteractively(monkeypatch, capsys):
    monkeypatch.setattr(
        ausum,
        "load_config",
        lambda: {
            "queue_url": "https://queue.example",
            "queue_token": "secret",
            "summary_dir": 123,
            "transcript_dir": "/tmp/transcripts",
        },
    )

    def fail_queue_fetch(*_args, **_kwargs):
        raise AssertionError("queue_fetch should not be called when output dirs are invalid")

    monkeypatch.setattr(ausum, "queue_fetch", fail_queue_fetch)

    assert ausum.cmd_poll() == 1

    captured = capsys.readouterr()
    assert "summary_dir/transcript_dir" in captured.err
    assert "poll/install-service" in captured.err


def test_queue_delete_url_encodes_reserved_item_id(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b""

    def fake_urlopen(req, timeout=15):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(ausum.urllib.request, "urlopen", fake_urlopen)

    ausum.queue_delete("https://queue.example", "secret", "a/b?c#d")

    assert captured == {
        "url": "https://queue.example/queue/a%2Fb%3Fc%23d",
        "method": "DELETE",
        "timeout": 15,
    }


def test_cmd_poll_accepts_zero_id_with_valid_url(monkeypatch, capsys):
    monkeypatch.setattr(
        ausum,
        "load_config",
        lambda: {
            "queue_url": "https://queue.example",
            "queue_token": "secret",
            "summary_dir": "/tmp/summaries",
            "transcript_dir": "/tmp/transcripts",
        },
    )
    monkeypatch.setattr(ausum, "queue_fetch", lambda *_: [{"id": 0, "url": "https://example.com/video"}])

    calls = {"processed": [], "deleted": []}
    monkeypatch.setattr(
        ausum,
        "process_input",
        lambda url, *_args, **_kwargs: calls["processed"].append(url) or 0,
    )
    monkeypatch.setattr(
        ausum,
        "queue_delete",
        lambda *_args: calls["deleted"].append(_args[-1]),
    )

    assert ausum.cmd_poll() == 0
    assert calls["processed"] == ["https://example.com/video"]
    assert calls["deleted"] == ["0"]

    captured = capsys.readouterr()
    assert "Skipping malformed queue item" not in captured.err
    assert "Done: 1 processed, 0 errors." in captured.err
