from __future__ import annotations

import tempfile
import unittest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cs2_review.access import UsageLimitError, analysis_slot


class AccessLimitTest(unittest.TestCase):
    def test_concurrent_limit_is_enforced_and_released(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "usage.sqlite"
            with analysis_slot(
                enabled=True,
                database_path=database,
                max_concurrent=1,
                max_daily_matches=50,
            ):
                with self.assertRaises(UsageLimitError):
                    with analysis_slot(
                        enabled=True,
                        database_path=database,
                        max_concurrent=1,
                        max_daily_matches=50,
                    ):
                        pass
            with analysis_slot(
                enabled=True,
                database_path=database,
                max_concurrent=1,
                max_daily_matches=50,
            ):
                pass

    def test_daily_match_limit_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "usage.sqlite"
            for _ in range(3):
                with analysis_slot(
                    enabled=True,
                    database_path=database,
                    max_concurrent=5,
                    max_daily_matches=3,
                ):
                    pass
            with self.assertRaises(UsageLimitError):
                with analysis_slot(
                    enabled=True,
                    database_path=database,
                    max_concurrent=5,
                    max_daily_matches=3,
                ):
                    pass


if __name__ == "__main__":
    unittest.main()

