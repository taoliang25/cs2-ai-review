from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cs2_review.map_callouts import (
    localize_fact_bundle_places,
    localize_place_name,
    localize_text,
    map_display_name,
)


class MapCalloutTest(unittest.TestCase):
    def test_dust2_names_are_localized(self) -> None:
        self.assertEqual(localize_place_name("de_dust2", "MidDoors"), "中门")
        text = localize_text(
            "de_dust2",
            "OutsideTunnel → UpperTunnel → BombsiteA",
        )
        self.assertEqual(text, "B洞外 → B洞 → A包")

    def test_callouts_do_not_leak_between_maps(self) -> None:
        self.assertEqual(localize_place_name("de_dust2", "Truck"), "Truck")
        self.assertEqual(localize_place_name("de_mirage", "Truck"), "白车")
        self.assertEqual(map_display_name("de_anubis"), "阿努比斯")

    def test_fact_bundle_localization_keeps_keys(self) -> None:
        value = {
            "early_route": ["TopofMid", "BDoors"],
            "nested": {"place": "BombsiteB"},
        }
        localized = localize_fact_bundle_places(value, "de_dust2")
        self.assertEqual(localized["early_route"], ["中路", "B门"])
        self.assertEqual(localized["nested"]["place"], "B包")


if __name__ == "__main__":
    unittest.main()
