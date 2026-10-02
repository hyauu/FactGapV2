from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from neutralize_model_visible_text import transform


class NeutralizationReplayTest(unittest.TestCase):
    def test_full_frozen_view_replays_to_locked_hashes(self) -> None:
        here = Path(__file__).resolve().parent
        source = here.parent / "historical_run" / "original_model_visible_view"
        lock = here.parent / "locks" / "corrected_scoring_view_lock.json"
        with tempfile.TemporaryDirectory() as tmp:
            report = transform(source, Path(tmp) / "corrected", lock)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["authorized_transform_counts"], {
            "remove_role_bearing_internal_identifier": 1029,
            "neutralize_role_bearing_entry_label": 735,
            "remove_unrelated_archive_identifier": 3675,
        })
        self.assertTrue(all(report["checks"].values()))


if __name__ == "__main__":
    unittest.main()
