from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cs2_review.importer import import_demo
from cs2_review.metrics import analyze_player, list_players
from cs2_review.reporting import TemplateReportProvider
from cs2_review.sensitivity import run_threshold_sensitivity

DEMO = (
    PROJECT_ROOT
    / "data"
    / "demo"
    / "research_demoparser_test_demo.dem"
)
PRO_COACH_DEMO = (
    PROJECT_ROOT
    / "data"
    / "demo"
    / "g2-vs-aurora-m2-anubis.dem"
)


@unittest.skipUnless(DEMO.is_file(), "Local validation demo is not present")
class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.database = Path(cls.temp_dir.name) / "analysis.sqlite"
        cls.import_result = import_demo(DEMO, output_path=cls.database)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def test_reference_data_and_integrity(self) -> None:
        connection = sqlite3.connect(self.database)
        try:
            self.assertEqual(
                connection.execute("PRAGMA integrity_check").fetchone()[0],
                "ok",
            )
            self.assertEqual(
                connection.execute("PRAGMA foreign_key_check").fetchall(),
                [],
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM player").fetchone()[0],
                10,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM round").fetchone()[0],
                10,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM game_event WHERE event_type = 'kill'"
                ).fetchone()[0],
                73,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM game_event WHERE event_type = 'damage'"
                ).fetchone()[0],
                264,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT SUM(place_name IS NULL) FROM tick_sample"
                ).fetchone()[0],
                0,
            )
        finally:
            connection.close()

    def test_all_players_produce_evidence_backed_facts(self) -> None:
        players = list_players(self.database)
        self.assertEqual(len(players), 10)
        all_death_contexts = []
        for player in players:
            with self.subTest(player=player.steamid):
                bundle = analyze_player(
                    self.database,
                    steamid=player.steamid,
                )
                self.assertEqual(bundle["schema_version"], "1.0")
                self.assertTrue(bundle["metrics"])
                self.assertEqual(len(bundle["rounds"]), 10)
                self.assertIn("tactical_patterns", bundle)
                self.assertEqual(
                    bundle["tactical_patterns"]["rule_version"],
                    "tactical-rules-v0.2",
                )
                for round_fact in bundle["rounds"]:
                    self.assertTrue(round_fact["narrative"]["summary"])
                    self.assertTrue(round_fact["narrative"]["alternatives"])
                    all_death_contexts.extend(
                        round_fact.get("teammate_death_contexts", [])
                    )
                self.assertIn("excellent", bundle["key_rounds"])
                self.assertIn("problem", bundle["key_rounds"])

                evidence_ids = {
                    item["evidence_id"] for item in bundle["evidence"]
                }
                referenced_ids: set[str] = set()
                for metric in bundle["metrics"]:
                    referenced_ids.update(metric["evidence_ids"])
                for round_fact in bundle["rounds"]:
                    referenced_ids.update(round_fact["evidence_ids"])
                self.assertTrue(
                    referenced_ids <= evidence_ids,
                    msg=(
                        f"Missing evidence for {player.steamid}: "
                        f"{sorted(referenced_ids - evidence_ids)}"
                    ),
                )
        self.assertTrue(all_death_contexts)
        self.assertTrue(
            any(item["suggestions"] for item in all_death_contexts)
        )

    def test_template_report_has_required_sections(self) -> None:
        player = list_players(self.database)[0]
        bundle = analyze_player(self.database, steamid=player.steamid)
        report = TemplateReportProvider().generate(bundle)
        for heading in [
            "本场玩家画像",
            "回合时间线",
            "关键决策分析",
            "单回合复盘",
            "全场总结与训练建议",
            "证据展示",
        ]:
            self.assertIn(heading, report.markdown)
        self.assertNotIn("百分百还原玩家心理", report.markdown)
        self.assertNotIn(player.steamid, report.markdown)

    def test_threshold_sensitivity_output(self) -> None:
        response = run_threshold_sensitivity(
            self.database,
            output_dir=Path(self.temp_dir.name) / "sensitivity",
        )
        result = response["result"]
        self.assertEqual(result["player_count"], 10)
        self.assertEqual(len(result["distance_aggregate"]["near"]), 6)
        self.assertEqual(len(result["early_window_aggregate"]), 6)
        self.assertTrue(Path(response["result_path"]).is_file())


@unittest.skipUnless(
    PRO_COACH_DEMO.is_file(),
    "Professional coach-filter validation demo is not present",
)
class ProfessionalPlayerFilterTest(unittest.TestCase):
    def test_coaches_and_spectators_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database_path = Path(temp) / "analysis.sqlite"
            result = import_demo(PRO_COACH_DEMO, output_path=database_path)
            self.assertEqual(result.player_count, 10)
            self.assertEqual(result.round_count, 4)
            self.assertTrue(result.has_match_end)
            self.assertFalse(result.regulation_complete)
            connection = sqlite3.connect(database_path)
            try:
                sides = dict(
                    connection.execute(
                        """
                        SELECT starting_side, COUNT(*)
                        FROM player
                        WHERE is_recorder = 0
                        GROUP BY starting_side
                        """
                    ).fetchall()
                )
            finally:
                connection.close()
            self.assertEqual(sides["terrorist"], 5)
            self.assertEqual(sides["counter-terrorist"], 5)


if __name__ == "__main__":
    unittest.main()

