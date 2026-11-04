"""Inspect basic CS2 demo metadata without retaining player data.

Usage:
    .\\.venv\\Scripts\\python.exe scripts\\inspect_demo.py path\\to\\match.dem
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import awpy
from awpy import Demo


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_demo(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Demo not found: {path}")
    if path.suffix.lower() != ".dem":
        raise ValueError(f"Expected a .dem file, got: {path.name}")

    demo = Demo(str(path))
    header = dict(demo.header)
    demo.load("players")
    players = list(demo.players.iter_rows(named=True))
    raw_players = [
        {
            **row,
            "steamid": str(row["steamid"]),
        }
        for row in players
    ]
    participant_rows = [
        row for row in raw_players
        if row.get("side") in {"terrorist", "counter-terrorist"}
    ]

    player_fields = sorted(
        {key for player in raw_players for key in player.keys()}
    )
    return {
        "parser": {
            "name": "awpy",
            "version": awpy.__version__,
        },
        "file": {
            "name": path.name,
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        },
        "header": header,
        "raw_player_count": len(raw_players),
        "participant_count_initial": len(participant_rows),
        "player_fields": player_fields,
        "players": raw_players,
    }


def main() -> int:
    arg_parser = argparse.ArgumentParser(
        description="Inspect map, player list, and parser fields in one CS2 demo."
    )
    arg_parser.add_argument("demo", type=Path, help="Path to a .dem file")
    arg_parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path; otherwise print to stdout.",
    )
    args = arg_parser.parse_args()

    try:
        result = inspect_demo(args.demo)
    except Exception as exc:
        print(f"Inspection failed: {exc}", file=sys.stderr)
        return 1

    rendered = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

