"""Background worker process for `graphify obsidian watch start`."""
from __future__ import annotations

import argparse
from pathlib import Path

from graphify.watch import watch


def main() -> None:
    parser = argparse.ArgumentParser(description="Run graphify Obsidian watch worker")
    parser.add_argument("--vault", required=True, help="Obsidian vault path")
    parser.add_argument("--debounce", type=float, default=3.0)
    args = parser.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    state_dir = vault / ".graphify"
    report_path = vault / "Graphify" / "GRAPH_REPORT.md"
    update_hint = f"Run `graphify obsidian update --vault {vault}` to sync semantic changes."

    watch(
        vault,
        debounce=args.debounce,
        state_dir=state_dir,
        report_path=report_path,
        update_hint=update_hint,
    )


if __name__ == "__main__":
    main()
