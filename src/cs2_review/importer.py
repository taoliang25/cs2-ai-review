"""Import one CS2 demo into the local normalized SQLite fact store."""

from __future__ import annotations

import bisect
import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import awpy
from awpy import Demo

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = PROJECT_ROOT / "database" / "schema.sql"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"


@dataclass(frozen=True)
class ImportResult:
    analysis_id: str
    database_path: str
    demo_sha256: str
    map_name: str
    player_count: int
    round_count: int
    has_match_end: bool
    regulation_complete: bool
    tick_sample_count: int
    event_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):
        return _json_safe(value.item())
    return str(value)


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _side(value: Any) -> str | None:
    return str(value) if value is not None else None


def _steamid(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text not in {"", "0", "None", "null"} else None


def _bool_int(value: Any) -> int | None:
    return None if value is None else int(bool(value))


class RoundLookup:
    def __init__(self, round_rows: Iterable[Mapping[str, Any]]) -> None:
        self._rounds = sorted(
            (
                int(row["round_num"]),
                int(row["start_tick"]),
                int(row["end_tick"]),
            )
            for row in round_rows
        )
        self._starts = [row[1] for row in self._rounds]

    def find(self, tick: int) -> int | None:
        """Return the preceding round for an event tick.

        A few post-round kills can appear after ``round.end_tick`` and before
        the next round begins. They are still attributed to the preceding
        round so the evidence store does not silently lose real events.
        """
        index = bisect.bisect_right(self._starts, int(tick)) - 1
        if index < 0:
            return None
        return self._rounds[index][0]

    def find_live(self, tick: int) -> int | None:
        """Return a round only while that round is still active."""
        index = bisect.bisect_right(self._starts, int(tick)) - 1
        if index < 0:
            return None
        round_num, start_tick, end_tick = self._rounds[index]
        return round_num if start_tick <= tick <= end_tick else None

    def is_post_round(self, tick: int, round_num: int) -> bool:
        for item_round, _, end_tick in self._rounds:
            if item_round == round_num:
                return tick > end_tick
        return False


def _insert_reference_data(
    connection: sqlite3.Connection,
    *,
    analysis_id: str,
    demo_path: Path,
    demo_sha256: str,
    header: Mapping[str, Any],
    demo: Demo,
    has_match_end: bool,
    regulation_complete: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    demo.load("players", "rounds", "round_economy")
    all_players = list(demo.players.iter_rows(named=True))
    coach_frame = demo.ticks(["m_iCoachingTeam"], players_only=True)
    coach_steamids = {
        steamid
        for row in coach_frame.iter_rows(named=True)
        if (steamid := _steamid(row.get("steamid"))) is not None
        and row.get("m_iCoachingTeam") not in {None, 0, "0"}
    }
    players = [
        row
        for row in all_players
        if row.get("side") in {"terrorist", "counter-terrorist"}
        and (steamid := _steamid(row.get("steamid"))) is not None
        and steamid not in coach_steamids
        and not str(row.get("name") or "").lower().startswith("coach|")
    ]
    rounds = list(demo.rounds.iter_rows(named=True))

    now = datetime.now(timezone.utc).isoformat()
    connection.execute(
        """
        INSERT INTO analysis (
            analysis_id, demo_sha256, demo_path, demo_size_bytes, map_name,
            demo_version, parser_name, parser_version, status, total_rounds,
            tick_rate, playback_ticks, has_match_end, regulation_complete,
            imported_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'parsed', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            analysis_id,
            demo_sha256,
            str(demo_path.resolve()),
            demo_path.stat().st_size,
            header.get("map_name"),
            header.get("demo_version_name"),
            "awpy",
            awpy.__version__,
            len(rounds),
            float(demo.tick_rate),
            header.get("playback_ticks"),
            int(has_match_end),
            int(regulation_complete),
            now,
            now,
        ),
    )

    player_rows = []
    for row in players:
        steamid = _steamid(row["steamid"])
        assert steamid is not None
        current_name = str(row.get("name") or steamid)
        player_rows.append(
            (
                analysis_id,
                steamid,
                current_name,
                _side(row.get("side")),
                0,
            )
        )
    connection.executemany(
        """
        INSERT INTO player (
            analysis_id, steamid, current_name, starting_side, is_recorder
        ) VALUES (?, ?, ?, ?, ?)
        """,
        player_rows,
    )

    round_rows = []
    for row in rounds:
        round_rows.append(
            (
                analysis_id,
                int(row["round_num"]),
                int(row["start_tick"]),
                int(row["freeze_end_tick"])
                if row.get("freeze_end_tick") is not None
                else None,
                int(row["end_tick"]),
                str(row["winner_side"]),
                int(row["reason"]) if row.get("reason") is not None else None,
                str(row["reason_name"]) if row.get("reason_name") is not None else None,
                int(bool(row.get("is_knife_round", False))),
            )
        )
    connection.executemany(
        """
        INSERT INTO round (
            analysis_id, round_num, start_tick, freeze_end_tick, end_tick,
            winner_side, reason_code, reason_name, is_knife_round
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        round_rows,
    )

    economy_rows = []
    for row in demo.round_economy.iter_rows(named=True):
        economy_rows.append(
            (
                analysis_id,
                int(row["round_num"]),
                str(row["side"]),
                int(row["equipment_value"]),
                str(row["buy_type"]) if row.get("buy_type") is not None else None,
                int(row["n_players"]),
            )
        )
    connection.executemany(
        """
        INSERT INTO round_team_economy (
            analysis_id, round_num, side, equipment_value, buy_type, n_players
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        economy_rows,
    )
    return players, rounds


def _insert_ticks(
    connection: sqlite3.Connection,
    *,
    analysis_id: str,
    demo: Demo,
    round_lookup: RoundLookup,
    valid_steamids: set[str],
) -> int:
    snapshots = demo.snapshots(seconds=1)
    place_frame = demo.ticks(["m_szLastPlaceName"], players_only=True)
    places = {
        (int(row["tick"]), _steamid(row["steamid"])): row.get(
            "m_szLastPlaceName"
        )
        for row in place_frame.iter_rows(named=True)
        if _steamid(row.get("steamid")) is not None
    }
    rows = []
    for row in snapshots.iter_rows(named=True):
        tick = int(row["tick"])
        round_num = round_lookup.find_live(tick)
        steamid = _steamid(row.get("steamid"))
        if round_num is None or steamid is None or steamid not in valid_steamids:
            continue
        rows.append(
            (
                analysis_id,
                round_num,
                tick,
                steamid,
                _side(row.get("side")),
                row.get("x"),
                row.get("y"),
                row.get("z"),
                row.get("pitch"),
                row.get("yaw"),
                row.get("health"),
                row.get("armor"),
                row.get("money"),
                row.get("equipment_value"),
                row.get("active_weapon"),
                places.get((tick, steamid)),
                _bool_int(row.get("has_bomb")),
                _bool_int(row.get("is_crouched")),
                _bool_int(row.get("is_walking")),
                _bool_int(row.get("is_jumping")),
                _bool_int(row.get("is_scoped")),
                _bool_int(row.get("is_blinded")),
            )
        )
    connection.executemany(
        """
        INSERT INTO tick_sample (
            analysis_id, round_num, tick, steamid, side, x, y, z, pitch, yaw,
            health, armor, money, equipment_value, active_weapon, place_name,
            has_bomb, is_crouched, is_walking, is_jumping, is_scoped, is_blinded
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def _insert_events(
    connection: sqlite3.Connection,
    *,
    analysis_id: str,
    demo: Demo,
    round_lookup: RoundLookup,
) -> int:
    # Awpy event tables have different names for the same concepts. Each
    # adapter below maps one source row to the shared evidence schema.
    specs: list[dict[str, Any]] = [
        {
            "dataset": "kills",
            "event_type": "kill",
            "actor": "attacker_steamid",
            "target": "victim_steamid",
            "assister": "assister_steamid",
            "weapon": "weapon",
            "x": "attacker_x",
            "y": "attacker_y",
            "z": "attacker_z",
        },
        {
            "dataset": "damages",
            "event_type": "damage",
            "actor": "attacker_steamid",
            "target": "victim_steamid",
            "weapon": "weapon",
            "x": "attacker_x",
            "y": "attacker_y",
            "z": "attacker_z",
        },
        {
            "dataset": "bomb",
            "event_type": "bomb",
            "actor": "steamid",
            "x": "x",
            "y": "y",
            "z": "z",
        },
        {
            "dataset": "shots",
            "event_type": "shot",
            "actor": "steamid",
            "weapon": "weapon",
            "x": "x",
            "y": "y",
            "z": "z",
        },
        {
            "dataset": "smokes",
            "event_type": "smoke",
            "actor": "thrower_steamid",
            "x": "x",
            "y": "y",
            "z": "z",
            "tick": "start_tick",
        },
        {
            "dataset": "fires",
            "event_type": "fire",
            "actor": "thrower_steamid",
            "x": "x",
            "y": "y",
            "z": "z",
            "tick": "start_tick",
        },
        {
            "dataset": "blinds",
            "event_type": "flash_blind",
            "actor": "attacker_steamid",
            "target": "victim_steamid",
            "x": "attacker_x",
            "y": "attacker_y",
            "z": "attacker_z",
        },
        {
            "dataset": "item_events",
            "event_type": "item",
            "event_field": "action",
            "actor": "steamid",
            "weapon": "item",
            "x": "x",
            "y": "y",
            "z": "z",
        },
    ]
    datasets = [spec["dataset"] for spec in specs]
    demo.load(*datasets)

    rows = []
    sequences: dict[tuple[int, str], int] = defaultdict(int)
    dropped = 0
    short_analysis = analysis_id[:8].upper()
    for spec in specs:
        dataframe = getattr(demo, spec["dataset"])
        tick_field = spec.get("tick", "tick")
        for source in dataframe.iter_rows(named=True):
            tick_value = source.get(tick_field)
            if tick_value is None:
                dropped += 1
                continue
            tick = int(tick_value)
            round_num = round_lookup.find(tick)
            if round_num is None:
                dropped += 1
                continue

            if spec["dataset"] == "bomb":
                base_type = str(source.get("event"))
            elif spec.get("event_field"):
                base_type = f"{spec['event_type']}_{source.get(spec['event_field'])}"
            else:
                base_type = str(spec["event_type"])
            sequences[(round_num, base_type)] += 1
            evidence_id = (
                f"E-{short_analysis}-R{round_num:02d}-"
                f"{tick:07d}-{base_type[:10].upper()}-"
                f"{sequences[(round_num, base_type)]:04d}"
            )
            payload = {key: _json_safe(value) for key, value in source.items()}
            payload["is_post_round"] = round_lookup.is_post_round(
                tick, round_num
            )
            rows.append(
                (
                    evidence_id,
                    analysis_id,
                    round_num,
                    tick,
                    base_type,
                    _steamid(source.get(spec.get("actor", ""))),
                    _steamid(source.get(spec.get("target", ""))),
                    _steamid(source.get(spec.get("assister", ""))),
                    str(source.get(spec.get("weapon", "")))
                    if source.get(spec.get("weapon", "")) is not None
                    else None,
                    source.get(spec.get("x", "")),
                    source.get(spec.get("y", "")),
                    source.get(spec.get("z", "")),
                    _json_dump(payload),
                )
            )

    connection.executemany(
        """
        INSERT INTO game_event (
            evidence_id, analysis_id, round_num, tick, event_type,
            actor_steamid, target_steamid, assister_steamid, weapon,
            x, y, z, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def import_demo(
    demo_path: Path | str,
    *,
    output_path: Path | str | None = None,
    schema_path: Path | str = DEFAULT_SCHEMA,
) -> ImportResult:
    """Parse one demo and atomically create its SQLite fact store."""
    path = Path(demo_path)
    if not path.is_file():
        raise FileNotFoundError(f"Demo not found: {path}")
    if path.suffix.lower() != ".dem":
        raise ValueError(f"Expected a .dem file, got: {path.name}")

    demo_sha256 = sha256_file(path)
    analysis_id = demo_sha256
    output = (
        Path(output_path)
        if output_path is not None
        else DEFAULT_OUTPUT_DIR / f"{demo_sha256[:12]}.sqlite"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(
            f"Output already exists: {output}. Use a new output path "
            "or remove the old local database explicitly."
        )

    demo = Demo(str(path))
    header = dict(demo.header)
    demo.load("rounds")
    winner_counts = Counter(
        str(row["winner_side"])
        for row in demo.rounds.iter_rows(named=True)
    )
    has_match_end = bool(demo.events.counts.get("cs_win_panel_match", 0))
    regulation_complete = has_match_end and max(
        winner_counts.get("terrorist", 0),
        winner_counts.get("counter-terrorist", 0),
    ) >= 13
    connection = sqlite3.connect(output)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        schema_sql = Path(schema_path).read_text(encoding="utf-8")
        connection.executescript(schema_sql)
        with connection:
            players, rounds = _insert_reference_data(
                connection,
                analysis_id=analysis_id,
                demo_path=path,
                demo_sha256=demo_sha256,
                header=header,
                demo=demo,
                has_match_end=has_match_end,
                regulation_complete=regulation_complete,
            )
            valid_steamids = {
                steamid
                for row in players
                if (steamid := _steamid(row.get("steamid"))) is not None
            }
            round_lookup = RoundLookup(rounds)
            tick_sample_count = _insert_ticks(
                connection,
                analysis_id=analysis_id,
                demo=demo,
                round_lookup=round_lookup,
                valid_steamids=valid_steamids,
            )
            event_count = _insert_events(
                connection,
                analysis_id=analysis_id,
                demo=demo,
                round_lookup=round_lookup,
            )
    except Exception:
        connection.close()
        # Keep failed attempts out of the processed directory. The original
        # demo is never modified and a caller can safely retry.
        if output.exists():
            output.unlink()
        raise
    else:
        connection.close()

    return ImportResult(
        analysis_id=analysis_id,
        database_path=str(output.resolve()),
        demo_sha256=demo_sha256,
        map_name=str(header.get("map_name")),
        player_count=len(players),
        round_count=len(rounds),
        has_match_end=has_match_end,
        regulation_complete=regulation_complete,
        tick_sample_count=tick_sample_count,
        event_count=event_count,
    )

