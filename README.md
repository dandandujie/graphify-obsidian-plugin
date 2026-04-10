# Graphify Obsidian Plugin

Obsidian-first Graphify project.

This repository is now organized around an Obsidian plugin (TypeScript) with a Python analysis engine in `engine/`.

## Features

- Obsidian sidebar panel with provider switch: `Claude Code` / `Codex`
- Assistant prompt streaming in-panel
- Vault action commands:
  - `Index Vault`
  - `Incremental Update`
  - `Query Graph`
  - `Generate Report`
  - `Ingest URL`
  - `Start Watch` / `Stop Watch`
- Report dual-write:
  - Real-time panel feedback
  - Persistent note: `Graphify/GRAPH_REPORT.md`
- Vault-local machine data under `.graphify/` (no `graphify-out/`)

## Repository Layout

```text
.
├── main.ts / manifest.json / src/         # Obsidian plugin (primary product)
├── engine/                                # Python analysis engine
│   ├── graphify/
│   ├── tests/
│   └── pyproject.toml
└── .github/workflows/ci.yml
```

## Requirements

- Obsidian Desktop
- Local `graphify` CLI available in `PATH` (or configured in plugin settings)
- Local `claude` and/or `codex` CLI if using assistant bridge
- Python 3.10+ (for engine development)

## Plugin Development

```bash
npm install
npm run check
npm test
npm run build
```

## Engine Development

```bash
cd engine
uv run --with pytest -m pytest -q tests
```

## Stable CLI Contract (Plugin -> Engine)

- `graphify obsidian index --vault <path>`
- `graphify obsidian update --vault <path>`
- `graphify obsidian query --vault <path> --question "..."`
- `graphify obsidian report --vault <path>`
- `graphify obsidian ingest --vault <path> --url <url>`
- `graphify obsidian watch --vault <path> [start|stop|status]`

All commands return JSON:

```json
{ "ok": true, "code": "OK", "message": "...", "data": {}, "metrics": {} }
```

## Transition Notes

- Legacy `graphify install` / platform skill flows are kept for one transition release and print deprecation warnings.
- Legacy default CLI surface (`query`, `benchmark`, `hook`) is removed in Obsidian-first mode.
