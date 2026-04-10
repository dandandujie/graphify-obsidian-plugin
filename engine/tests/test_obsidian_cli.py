"""Tests for `graphify obsidian ...` CLI contract."""

from __future__ import annotations

import json
from pathlib import Path

from graphify.obsidian import run_obsidian_cli


def _parse_last_json(capsys) -> dict:
    out = capsys.readouterr().out.strip().splitlines()
    assert out, "Expected JSON output from run_obsidian_cli"
    return json.loads(out[-1])


def test_obsidian_index_writes_vault_state(tmp_path, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    code = run_obsidian_cli(["index", "--vault", str(vault)])
    payload = _parse_last_json(capsys)

    assert code == 0
    assert payload["ok"] is True
    assert payload["code"] == "OK"
    assert (vault / ".graphify" / "graph.json").exists()
    assert (vault / "Graphify" / "GRAPH_REPORT.md").exists()
    assert not (vault / "graphify-out").exists()
    assert set(payload.keys()) == {"ok", "code", "message", "data", "metrics"}


def test_obsidian_query_requires_graph(tmp_path, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()

    code = run_obsidian_cli(["query", "--vault", str(vault), "--question", "auth flow"])
    payload = _parse_last_json(capsys)

    assert code == 1
    assert payload["ok"] is False
    assert payload["code"] == "GRAPH_NOT_FOUND"


def test_obsidian_update_incremental(tmp_path, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()
    file_path = vault / "sample.py"
    file_path.write_text("def first():\n    return 1\n", encoding="utf-8")

    assert run_obsidian_cli(["index", "--vault", str(vault)]) == 0
    _ = _parse_last_json(capsys)

    file_path.write_text("def first():\n    return 2\n", encoding="utf-8")
    code = run_obsidian_cli(["update", "--vault", str(vault)])
    payload = _parse_last_json(capsys)

    assert code == 0
    assert payload["ok"] is True
    assert payload["metrics"]["changed_code_files"] >= 1
    assert (vault / ".graphify" / "manifest.json").exists()


def test_obsidian_invalid_vault_path(capsys):
    code = run_obsidian_cli(["index", "--vault", "/path/does/not/exist"])
    payload = _parse_last_json(capsys)

    assert code == 1
    assert payload["ok"] is False
    assert payload["code"] == "PATH_INVALID"


def test_obsidian_watch_status_not_running(tmp_path, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()

    code = run_obsidian_cli(["watch", "--vault", str(vault), "status"])
    payload = _parse_last_json(capsys)

    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["running"] is False
