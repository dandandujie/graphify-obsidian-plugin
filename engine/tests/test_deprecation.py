"""Tests for legacy command deprecation warnings."""

import subprocess
import sys

from graphify.__main__ import _print_legacy_deprecation


def test_legacy_deprecation_message(capsys):
    _print_legacy_deprecation("install")
    err = capsys.readouterr().err
    assert "DEPRECATION" in err
    assert "graphify obsidian" in err


def test_removed_legacy_command_errors():
    proc = subprocess.run(
        [sys.executable, "-m", "graphify", "query", "hello"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "removed from the default CLI surface" in proc.stderr
