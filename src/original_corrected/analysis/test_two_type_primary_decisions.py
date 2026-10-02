from __future__ import annotations

import unittest

import pandas as pd

from analysis.two_type_primary import (
    TYPES,
    boundary_degenerate_types,
    map_global_status,
    r3_bootstrap_is_defined,
)


ENDPOINT_IDS = (
    "R1-BGE",
    "R1-E5",
    "R2-BGE-reranker",
    "R2-legacy-cross-encoder",
    "R3-BGE_to_BGE-reranker",
    "R3-BGE_to_legacy-cross-encoder",
    "R3-E5_to_BGE-reranker",
)


def endpoint(name: str, status: str = "INCONCLUSIVE", upper: float = 0.50) -> dict:
    tau = 0.10 if name.startswith("R2") else 0.05
    return {
        "endpoint": name,
        "status": status,
        "tau": tau,
        "type_simultaneous": {typ: [0.0, upper] for typ in TYPES},
    }


class DecisionRuleTests(unittest.TestCase):
    def test_boundary_collapse_is_detected(self) -> None:
        contributions = {
            TYPES[0]: pd.Series([1.0, 1.0, 1.0]),
            TYPES[1]: pd.Series([0.1, 0.2, 0.3]),
        }
        intervals = {TYPES[0]: [1.0, 1.0], TYPES[1]: [0.1, 0.3]}
        self.assertEqual(boundary_degenerate_types(contributions, intervals), [TYPES[0]])

    def test_supported_mapping(self) -> None:
        rows = [endpoint(name) for name in ENDPOINT_IDS]
        for row in rows[:4]:
            row["status"] = "SUPPORTED"
        self.assertEqual(map_global_status(rows), "SUPPORTED")

    def test_not_supported_mapping(self) -> None:
        rows = [endpoint(name, upper=0.01) for name in ENDPOINT_IDS]
        self.assertEqual(map_global_status(rows), "NOT_SUPPORTED")

    def test_boundary_blocks_not_supported(self) -> None:
        rows = [endpoint(name, upper=0.01) for name in ENDPOINT_IDS]
        rows[0]["status"] = "BOUNDARY_DEGENERATE"
        self.assertEqual(map_global_status(rows), "INCONCLUSIVE")

    def test_insufficient_eligibility_blocks_not_supported(self) -> None:
        rows = [endpoint(name, upper=0.01) for name in ENDPOINT_IDS]
        rows[-1]["status"] = "INSUFFICIENT_ELIGIBILITY"
        self.assertEqual(map_global_status(rows), "INCONCLUSIVE")

    def test_mixed_outcome_is_inconclusive(self) -> None:
        rows = [endpoint(name, upper=0.01) for name in ENDPOINT_IDS]
        rows[-1]["type_simultaneous"][TYPES[1]][1] = 0.20
        self.assertEqual(map_global_status(rows), "INCONCLUSIVE")

    def test_r3_undefined_bootstrap_threshold(self) -> None:
        self.assertTrue(r3_bootstrap_is_defined(0.0099, 0.01))
        self.assertTrue(r3_bootstrap_is_defined(0.01, 0.01))
        self.assertFalse(r3_bootstrap_is_defined(0.0101, 0.01))


if __name__ == "__main__":
    unittest.main()
