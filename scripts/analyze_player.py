"""Build transparent behavior metrics for one player in a local analysis DB."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cs2_review.metrics import analyze_player, list_players  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute and persist player facts from an imported demo."
    )
    parser.add_argument("database", type=Path, help="Imported SQLite database")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--steamid", help="Player Steam ID")
    selection.add_argument("--name", help="Exact player display name")
    parser.add_argument("--list-players", action="store_true")
    parser.add_argument("--output", type=Path, help="Optional FactBundle JSON")
    args = parser.parse_args()

    if args.list_players:
        for player in list_players(args.database):
            print(
                json.dumps(
                    {
                        "steamid": player.steamid,
                        "name": player.name,
                        "starting_side": player.starting_side,
                    },
                    ensure_ascii=False,
                )
            )
        return 0

    if not args.steamid and not args.name:
        print("Choose --steamid or --name; use --list-players to inspect.", file=sys.stderr)
        return 2

    try:
        bundle = analyze_player(
            args.database,
            steamid=args.steamid,
            player_name=args.name,
        )
    except Exception as exc:
        print(f"Analysis failed: {exc}", file=sys.stderr)
        return 1

    rendered = json.dumps(bundle, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

