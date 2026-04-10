"""Obsidian-first CLI contract for graphify."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import networkx as nx
from networkx.readwrite import json_graph

from graphify.analyze import god_nodes, suggest_questions, surprising_connections
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.detect import detect, detect_incremental, save_manifest
from graphify.export import to_json
from graphify.extract import collect_files, extract
from graphify.ingest import ingest
from graphify.report import generate
from graphify.serve import _bfs, _dfs, _score_nodes, _subgraph_to_text

DATA_DIR_NAME = ".graphify"
REPORT_DIR_NAME = "Graphify"
REPORT_FILE_NAME = "GRAPH_REPORT.md"
MANIFEST_FILE_NAME = "manifest.json"
GRAPH_FILE_NAME = "graph.json"
WATCH_PID_FILE_NAME = "watch.pid"
WATCH_LOG_FILE_NAME = "watch.log"
NEEDS_UPDATE_FILE_NAME = "needs_update"
DETECTION_SNAPSHOT_NAME = "detection.json"

CODE_OK = "OK"
CODE_INVALID_ARGS = "INVALID_ARGS"
CODE_PATH_INVALID = "PATH_INVALID"
CODE_GRAPH_NOT_FOUND = "GRAPH_NOT_FOUND"
CODE_TASK_CONFLICT = "TASK_CONFLICT"
CODE_WATCH_NOT_RUNNING = "WATCH_NOT_RUNNING"
CODE_INTERNAL_ERROR = "INTERNAL_ERROR"


def _response(
    ok: bool,
    code: str,
    message: str,
    *,
    data: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "code": code,
        "message": message,
        "data": data or {},
        "metrics": metrics or {},
    }


def _emit(resp: dict[str, Any]) -> int:
    print(json.dumps(resp, ensure_ascii=False))
    return 0 if resp.get("ok") else 1


def _resolve_vault(raw_path: str) -> Path:
    vault = Path(raw_path).expanduser().resolve()
    if not vault.exists():
        raise ValueError(f"Vault path does not exist: {vault}")
    if not vault.is_dir():
        raise ValueError(f"Vault path is not a directory: {vault}")
    return vault


def _paths(vault: Path) -> dict[str, Path]:
    state_dir = vault / DATA_DIR_NAME
    report_dir = vault / REPORT_DIR_NAME
    return {
        "vault": vault,
        "state_dir": state_dir,
        "memory_dir": state_dir / "memory",
        "converted_dir": state_dir / "converted",
        "graph_file": state_dir / GRAPH_FILE_NAME,
        "manifest_file": state_dir / MANIFEST_FILE_NAME,
        "detection_file": state_dir / DETECTION_SNAPSHOT_NAME,
        "needs_update_file": state_dir / NEEDS_UPDATE_FILE_NAME,
        "watch_pid_file": state_dir / WATCH_PID_FILE_NAME,
        "watch_log_file": state_dir / WATCH_LOG_FILE_NAME,
        "report_file": report_dir / REPORT_FILE_NAME,
        "raw_dir": report_dir / "raw",
    }


def _ensure_dirs(paths: dict[str, Path]) -> None:
    paths["state_dir"].mkdir(parents=True, exist_ok=True)
    paths["report_file"].parent.mkdir(parents=True, exist_ok=True)


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_graph(graph_file: Path) -> nx.Graph:
    data = json.loads(graph_file.read_text(encoding="utf-8"))
    return json_graph.node_link_graph(data, edges="links")


def _collect_code_files(code_entries: list[str]) -> list[Path]:
    files: list[Path] = []
    for entry in code_entries:
        p = Path(entry)
        files.extend(collect_files(p) if p.is_dir() else [p])
    deduped = sorted({f.resolve() for f in files if f.exists()})
    return [Path(p) for p in deduped]


@contextmanager
def _cache_override(cache_path: Path):
    """Temporarily redirect extraction cache away from graphify-out/cache."""
    key = "GRAPHIFY_CACHE_DIR"
    previous = os.environ.get(key)
    os.environ[key] = str(cache_path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


def _merge_extraction(G: nx.Graph, extraction: dict[str, Any]) -> None:
    for node in extraction.get("nodes", []):
        nid = node["id"]
        attrs = {k: v for k, v in node.items() if k != "id"}
        G.add_node(nid, **attrs)
    for edge in extraction.get("edges", []):
        src = edge["source"]
        tgt = edge["target"]
        attrs = {k: v for k, v in edge.items() if k not in ("source", "target")}
        attrs["_src"] = src
        attrs["_tgt"] = tgt
        G.add_edge(src, tgt, **attrs)


def _fallback_detection(G: nx.Graph) -> dict[str, Any]:
    source_files = sorted({d.get("source_file", "") for _, d in G.nodes(data=True) if d.get("source_file")})
    return {
        "files": {"code": source_files, "document": [], "paper": [], "image": []},
        "total_files": len(source_files),
        "total_words": 0,
        "needs_graph": True,
        "warning": None,
        "skipped_sensitive": [],
        "graphifyignore_patterns": 0,
    }


def _analyze_and_persist(
    *,
    vault: Path,
    paths: dict[str, Path],
    G: nx.Graph,
    detection_result: dict[str, Any],
    token_cost: dict[str, int] | None = None,
) -> dict[str, Any]:
    communities = cluster(G)
    cohesion = score_all(G, communities)
    labels = {cid: f"Community {cid}" for cid in communities}
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    questions = suggest_questions(G, communities, labels)
    tokens = token_cost or {"input": 0, "output": 0}

    to_json(G, communities, str(paths["graph_file"]))
    report = generate(
        G,
        communities,
        cohesion,
        labels,
        gods,
        surprises,
        detection_result,
        tokens,
        str(vault),
        suggested_questions=questions,
    )
    paths["report_file"].write_text(report, encoding="utf-8")
    _save_json(paths["detection_file"], detection_result)

    return {
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "community_count": len(communities),
        "report_path": str(paths["report_file"]),
        "graph_path": str(paths["graph_file"]),
    }


def _run_index(vault: Path) -> dict[str, Any]:
    paths = _paths(vault)
    _ensure_dirs(paths)

    detection_result = detect(
        vault,
        memory_dir=paths["memory_dir"],
        converted_dir=paths["converted_dir"],
    )
    code_files = _collect_code_files(detection_result["files"].get("code", []))
    if code_files:
        with _cache_override(paths["state_dir"] / "cache"):
            extraction_result = extract(code_files)
    else:
        extraction_result = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}
    G = build_from_json(extraction_result)

    summary = _analyze_and_persist(vault=vault, paths=paths, G=G, detection_result=detection_result)
    save_manifest(detection_result["files"], manifest_path=str(paths["manifest_file"]))

    non_code_files = sum(len(detection_result["files"].get(k, [])) for k in ("document", "paper", "image"))
    metrics = {
        "indexed_code_files": len(code_files),
        "detected_non_code_files": non_code_files,
        "input_tokens": extraction_result.get("input_tokens", 0),
        "output_tokens": extraction_result.get("output_tokens", 0),
    }
    return _response(
        True,
        CODE_OK,
        "Vault index completed.",
        data={
            **summary,
            "vault_path": str(vault),
            "state_dir": str(paths["state_dir"]),
        },
        metrics=metrics,
    )


def _run_update(vault: Path) -> dict[str, Any]:
    paths = _paths(vault)
    _ensure_dirs(paths)

    if not paths["graph_file"].exists() or not paths["manifest_file"].exists():
        return _run_index(vault)

    inc = detect_incremental(
        vault,
        manifest_path=str(paths["manifest_file"]),
        memory_dir=paths["memory_dir"],
        converted_dir=paths["converted_dir"],
    )
    changed_code_files = _collect_code_files(inc.get("new_files", {}).get("code", []))
    deleted_files = set(inc.get("deleted_files", []))
    changed_paths = {str(p) for p in changed_code_files}
    changed_or_deleted = changed_paths | deleted_files
    non_code_changes = sum(len(inc.get("new_files", {}).get(k, [])) for k in ("document", "paper", "image"))

    G = _load_graph(paths["graph_file"])
    if changed_or_deleted:
        to_remove = [
            nid
            for nid, data in G.nodes(data=True)
            if data.get("source_file", "") in changed_or_deleted
        ]
        if to_remove:
            G.remove_nodes_from(to_remove)

    extraction_result = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}
    if changed_code_files:
        with _cache_override(paths["state_dir"] / "cache"):
            extraction_result = extract(changed_code_files)
        _merge_extraction(G, extraction_result)

    if non_code_changes > 0:
        paths["needs_update_file"].write_text("1", encoding="utf-8")
    elif paths["needs_update_file"].exists():
        paths["needs_update_file"].unlink()

    summary = _analyze_and_persist(vault=vault, paths=paths, G=G, detection_result=inc)
    save_manifest(inc["files"], manifest_path=str(paths["manifest_file"]))

    msg = "Vault incremental update completed."
    if non_code_changes > 0:
        msg += " Non-code changes detected; semantic re-extraction is required for full fidelity."

    return _response(
        True,
        CODE_OK,
        msg,
        data={
            **summary,
            "vault_path": str(vault),
            "non_code_changes_require_semantic": non_code_changes > 0,
        },
        metrics={
            "changed_code_files": len(changed_code_files),
            "deleted_files": len(deleted_files),
            "non_code_changes": non_code_changes,
            "input_tokens": extraction_result.get("input_tokens", 0),
            "output_tokens": extraction_result.get("output_tokens", 0),
        },
    )


def _run_query(vault: Path, question: str, *, mode: str, depth: int, budget: int) -> dict[str, Any]:
    paths = _paths(vault)
    if not paths["graph_file"].exists():
        return _response(False, CODE_GRAPH_NOT_FOUND, f"Graph not found: {paths['graph_file']}")

    G = _load_graph(paths["graph_file"])
    terms = [t.lower() for t in question.split() if len(t) > 2]
    scored = _score_nodes(G, terms)
    if not scored:
        return _response(
            True,
            CODE_OK,
            "No matching nodes found.",
            data={"answer": "", "start_nodes": [], "mode": mode},
            metrics={"matched_nodes": 0},
        )

    start_nodes = [nid for _, nid in scored[:5]]
    nodes, edges = (_dfs if mode == "dfs" else _bfs)(G, start_nodes, depth=depth)
    answer = _subgraph_to_text(G, nodes, edges, token_budget=budget)
    start_labels = [G.nodes[n].get("label", n) for n in start_nodes]
    return _response(
        True,
        CODE_OK,
        "Query completed.",
        data={
            "answer": answer,
            "mode": mode,
            "depth": depth,
            "start_nodes": start_labels,
        },
        metrics={
            "matched_nodes": len(nodes),
            "matched_edges": len(edges),
            "budget": budget,
        },
    )


def _run_report(vault: Path) -> dict[str, Any]:
    paths = _paths(vault)
    if not paths["graph_file"].exists():
        return _response(False, CODE_GRAPH_NOT_FOUND, f"Graph not found: {paths['graph_file']}")

    G = _load_graph(paths["graph_file"])
    if paths["detection_file"].exists():
        detection_result = json.loads(paths["detection_file"].read_text(encoding="utf-8"))
    else:
        detection_result = _fallback_detection(G)

    summary = _analyze_and_persist(vault=vault, paths=paths, G=G, detection_result=detection_result)
    return _response(
        True,
        CODE_OK,
        "Report generated.",
        data=summary,
    )


def _run_ingest(vault: Path, url: str, *, author: str | None, contributor: str | None) -> dict[str, Any]:
    paths = _paths(vault)
    _ensure_dirs(paths)
    paths["raw_dir"].mkdir(parents=True, exist_ok=True)

    saved_path = ingest(url, paths["raw_dir"], author=author, contributor=contributor)
    update_resp = _run_update(vault)
    if not update_resp.get("ok"):
        return update_resp

    update_resp["message"] = f"URL ingested and vault updated: {saved_path}"
    update_resp["data"]["saved_path"] = str(saved_path)
    return update_resp


def _read_watch_meta(paths: dict[str, Path]) -> dict[str, Any] | None:
    pid_file = paths["watch_pid_file"]
    if not pid_file.exists():
        return None
    try:
        return json.loads(pid_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _run_watch_start(vault: Path, *, debounce: float) -> dict[str, Any]:
    paths = _paths(vault)
    _ensure_dirs(paths)

    meta = _read_watch_meta(paths)
    if meta and _is_pid_running(int(meta.get("pid", -1))):
        return _response(
            False,
            CODE_TASK_CONFLICT,
            f"Watch is already running (pid={meta['pid']}).",
            data={"pid": meta["pid"]},
        )

    log_file = paths["watch_log_file"]
    log_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "graphify.obsidian_watch_worker",
        "--vault",
        str(vault),
        "--debounce",
        str(debounce),
    ]
    with log_file.open("a", encoding="utf-8") as stream:
        kwargs: dict[str, Any] = {"stdout": stream, "stderr": subprocess.STDOUT}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **kwargs)

    meta = {
        "pid": proc.pid,
        "started_at": int(time.time()),
        "debounce": debounce,
        "vault": str(vault),
        "log_file": str(log_file),
    }
    _save_json(paths["watch_pid_file"], meta)
    return _response(
        True,
        CODE_OK,
        "Watch started.",
        data={"pid": proc.pid, "log_file": str(log_file)},
        metrics={"debounce": debounce},
    )


def _run_watch_stop(vault: Path) -> dict[str, Any]:
    paths = _paths(vault)
    meta = _read_watch_meta(paths)
    if not meta:
        return _response(False, CODE_WATCH_NOT_RUNNING, "Watch is not running.")

    pid = int(meta.get("pid", -1))
    if _is_pid_running(pid):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
        else:
            os.kill(pid, signal.SIGTERM)
            for _ in range(20):
                if not _is_pid_running(pid):
                    break
                time.sleep(0.1)
            if _is_pid_running(pid):
                os.kill(pid, signal.SIGKILL)

    if paths["watch_pid_file"].exists():
        paths["watch_pid_file"].unlink()

    return _response(True, CODE_OK, "Watch stopped.", data={"pid": pid})


def _run_watch_status(vault: Path) -> dict[str, Any]:
    paths = _paths(vault)
    meta = _read_watch_meta(paths)
    if not meta:
        return _response(True, CODE_OK, "Watch is stopped.", data={"running": False})

    pid = int(meta.get("pid", -1))
    running = _is_pid_running(pid)
    if not running and paths["watch_pid_file"].exists():
        paths["watch_pid_file"].unlink()
    return _response(
        True,
        CODE_OK,
        "Watch is running." if running else "Watch is stopped.",
        data={
            "running": running,
            "pid": pid if running else None,
            "log_file": meta.get("log_file"),
            "started_at": meta.get("started_at"),
            "debounce": meta.get("debounce"),
        },
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="graphify obsidian")
    sub = parser.add_subparsers(dest="subcommand")

    p_index = sub.add_parser("index", help="Build a graph index for an Obsidian vault")
    p_index.add_argument("--vault", required=True, help="Obsidian vault path")

    p_update = sub.add_parser("update", help="Incrementally update a vault graph index")
    p_update.add_argument("--vault", required=True, help="Obsidian vault path")

    p_query = sub.add_parser("query", help="Query vault graph")
    p_query.add_argument("--vault", required=True, help="Obsidian vault path")
    p_query.add_argument("--question", required=True, help="Natural language question")
    p_query.add_argument("--mode", choices=("bfs", "dfs"), default="bfs")
    p_query.add_argument("--depth", type=int, default=2)
    p_query.add_argument("--budget", type=int, default=2000)

    p_report = sub.add_parser("report", help="Regenerate Graphify report note")
    p_report.add_argument("--vault", required=True, help="Obsidian vault path")

    p_ingest = sub.add_parser("ingest", help="Ingest URL into vault and update graph")
    p_ingest.add_argument("--vault", required=True, help="Obsidian vault path")
    p_ingest.add_argument("--url", required=True, help="URL to ingest")
    p_ingest.add_argument("--author")
    p_ingest.add_argument("--contributor")

    p_watch = sub.add_parser("watch", help="Manage background watcher")
    p_watch.add_argument("--vault", required=True, help="Obsidian vault path")
    p_watch.add_argument("action", nargs="?", choices=("start", "stop", "status"), default="status")
    p_watch.add_argument("--debounce", type=float, default=3.0)

    return parser


def run_obsidian_cli(argv: list[str]) -> int:
    parser = _build_parser()
    if not argv:
        return _emit(_response(False, CODE_INVALID_ARGS, "Missing obsidian subcommand."))

    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return _emit(_response(False, CODE_INVALID_ARGS, "Invalid arguments for obsidian command."))

    try:
        if args.subcommand in ("index", "update", "query", "report", "ingest", "watch"):
            vault = _resolve_vault(args.vault)
        else:
            return _emit(_response(False, CODE_INVALID_ARGS, "Unknown obsidian subcommand."))

        if args.subcommand == "index":
            return _emit(_run_index(vault))
        if args.subcommand == "update":
            return _emit(_run_update(vault))
        if args.subcommand == "query":
            depth = max(1, min(args.depth, 6))
            budget = max(200, args.budget)
            return _emit(_run_query(vault, args.question, mode=args.mode, depth=depth, budget=budget))
        if args.subcommand == "report":
            return _emit(_run_report(vault))
        if args.subcommand == "ingest":
            return _emit(_run_ingest(vault, args.url, author=args.author, contributor=args.contributor))
        if args.subcommand == "watch":
            if args.action == "start":
                return _emit(_run_watch_start(vault, debounce=args.debounce))
            if args.action == "stop":
                return _emit(_run_watch_stop(vault))
            return _emit(_run_watch_status(vault))

        return _emit(_response(False, CODE_INVALID_ARGS, "Unknown obsidian subcommand."))
    except ValueError as exc:
        return _emit(_response(False, CODE_PATH_INVALID, str(exc)))
    except FileNotFoundError as exc:
        return _emit(_response(False, CODE_GRAPH_NOT_FOUND, str(exc)))
    except Exception as exc:
        return _emit(_response(False, CODE_INTERNAL_ERROR, str(exc)))


if __name__ == "__main__":
    raise SystemExit(run_obsidian_cli(sys.argv[1:]))
