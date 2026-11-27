"""Regression tests for the preregistered-branch registry checks."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import check_registry as registry  # noqa: E402


SAMPLE_REGISTRY = """\
| # | 枝 ID | 種別 | 仮説 |
| ---: | :--- | :--- | :--- |
| 1 | TEST-A | 仮説検定 | 主仮説を検査する |
| 2 | TEST-SIM | 方法論 | 多モデル運用を検討する |
"""


class RegistryParsingTests(unittest.TestCase):
    def test_parse_registry_extracts_rows_and_skips_separator(self) -> None:
        rows = registry.parse_registry(SAMPLE_REGISTRY)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["枝 ID"], "TEST-A")
        self.assertEqual(rows[1]["種別"], "方法論")

    def test_hypothesis_count_uses_explicit_kind(self) -> None:
        rows = registry.parse_registry(SAMPLE_REGISTRY)
        self.assertEqual(sum(registry.is_hypothesis_row(row) for row in rows), 1)

    def test_empty_registry_table_is_rejected_by_parser(self) -> None:
        self.assertEqual(registry.parse_registry("本文だけの文書です。\n"), [])


class HolmRequirementTests(unittest.TestCase):
    def test_three_registered_tests_require_59_permutations(self) -> None:
        threshold, required_permutations = registry.compute_holm_requirements(3, 0.05)
        self.assertAlmostEqual(threshold, 0.05 / 3)
        self.assertEqual(required_permutations, 59)

    def test_144_registered_tests_require_2879_permutations(self) -> None:
        threshold, required_permutations = registry.compute_holm_requirements(144, 0.05)
        self.assertAlmostEqual(threshold, 0.05 / 144)
        self.assertEqual(required_permutations, 2879)

    def test_registry_declarations_are_checked_against_computed_values(self) -> None:
        text = """\
登録枝数（仮説検定のみ）: **3**
Holm 補正後の第1しきい値: alpha / N = 0.0167
必要最小置換回数: **59**
"""
        threshold, required_permutations = registry.compute_holm_requirements(3, 0.05)
        self.assertEqual(
            registry.check_doc_declarations(text, 3, threshold, required_permutations),
            [],
        )

    def test_stale_registry_declarations_are_reported(self) -> None:
        text = """\
登録枝数（仮説検定のみ）: **4**
Holm 補正後の第1しきい値: alpha / N = 0.03
必要最小置換回数: **99**
"""
        threshold, required_permutations = registry.compute_holm_requirements(3, 0.05)
        errors = registry.check_doc_declarations(text, 3, threshold, required_permutations)
        self.assertEqual(len(errors), 3)
        self.assertTrue(any("登録枝数宣言" in error for error in errors))
        self.assertTrue(any("Holm しきい値表記" in error for error in errors))
        self.assertTrue(any("必要置換回数表記" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
