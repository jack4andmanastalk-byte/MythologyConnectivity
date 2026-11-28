"""Regression tests for the §10 follow-up analyses (branches #8-#11).

These guard the invariants the preregistration fixed *before* the numbers were
known (docs/prereg/20261128-path-connectivity-followup.md):

* the edge-reproduction classifier partitions the 597 displayed edges,
* the path-dependency ablation enumerates single points of failure instead of a
  count that depends on node iteration order,
* the display-reproducibility ledger agrees with the pre-existing F10 check,
* the doc-number gate is not silently disabled, and the network-check count is
  derived from the AST so the documented number and the code cannot drift.
"""
from __future__ import annotations

import ast
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import verify_numbers as numbers  # noqa: E402

CFG = json.loads((ROOT / "config/analysis.json").read_text(encoding="utf-8"))


def load(rel: str) -> dict:
    path = ROOT / rel
    if not path.exists():
        raise unittest.SkipTest(f"{rel} が無い（対応する make ターゲット未実行）")
    return json.loads(path.read_text(encoding="utf-8"))


class EdgeClassifierTests(unittest.TestCase):
    """枝 #8: 597 本を 4 クラスに全件分類する。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load("outputs/edge_reproduction.json")
        cls.rows = cls.data["edge_rows"]

    def test_every_edge_is_classified_once(self) -> None:
        self.assertEqual(self.data["total_edges"], 597)
        self.assertEqual(len(self.rows), 597)
        self.assertEqual(len({(r["source"], r["target"]) for r in self.rows}), 597)

    def test_class_totals_reproduce_the_headline_counts(self) -> None:
        totals: dict[str, int] = {}
        for row in self.rows:
            totals[row["classification"]] = totals.get(row["classification"], 0) + 1
        self.assertEqual(totals, self.data["classes"])
        self.assertEqual(sum(totals.values()), self.data["total_edges"])

    def test_class_names_are_the_preregistered_four(self) -> None:
        self.assertEqual(
            set(self.data["classes"]),
            {"l1_cosine", "l1_mismatch", "l2_construction_rule", "unverifiable"},
        )

    def test_ratios_are_derived_from_the_totals(self) -> None:
        total = self.data["total_edges"]
        for name, count in self.data["classes"].items():
            self.assertAlmostEqual(self.data["class_ratio"][name], count / total, places=4)

    def test_kojiki_inflow_matches_the_full_edge_table(self) -> None:
        inflow = [r for r in self.rows if r["target_is_kojiki"]]
        summary = self.data["kojiki_inflow"]
        self.assertEqual(summary["edges"], len(inflow))
        self.assertEqual(summary["edges"], 126)
        parts = sum(summary[k] for k in
                    ("l1_cosine", "l1_mismatch", "l2_construction_rule", "unverifiable"))
        self.assertEqual(parts, summary["edges"])

    def test_rank_breakdown_covers_every_edge_once(self) -> None:
        ranks = self.data["by_weight_rank"]
        self.assertEqual(sum(v["edges"] for v in ranks.values()), self.data["total_edges"])


class PathDependencyTests(unittest.TestCase):
    """枝 #9: 中継ノードを 1 つずつ外す感度分析。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load("outputs/path_dependency.json")

    def test_candidate_set_excludes_kojiki_targets(self) -> None:
        rows = self.data["ablation"]["candidates"]
        self.assertEqual(rows, self.data["baseline"]["ancestor_union"])
        self.assertEqual(self.data["baseline"]["ancestor_union"], 141)

    def test_spof_reported_for_both_definitions(self) -> None:
        ab = self.data["ablation"]
        self.assertEqual(ab["single_points_of_failure_disconnect"], ["SE01", "SE02", "SI12"])
        self.assertEqual(len(ab["single_points_of_failure_west"]), 5)

    def test_no_single_node_cuts_more_than_one_episode(self) -> None:
        self.assertEqual(self.data["ablation"]["max_kojiki_disconnected"], 1)

    def test_bridge_count_matches_the_network_check(self) -> None:
        self.assertEqual(self.data["bridges"]["count"], 26)
        self.assertEqual(len(self.data["bridges"]["only_one_side_has_kojiki"]), 23)

    def test_fraction_of_affected_candidates_is_reported(self) -> None:
        affected = self.data["ablation"]["n_nodes_with_any_effect"]
        self.assertLessEqual(affected, self.data["ablation"]["candidates"])


class DisplayReproducibilityTests(unittest.TestCase):
    """枝 #10: 表示被説明率の再計算可否。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load("derived/display_reproducibility.json")

    def test_node_census_adds_up(self) -> None:
        overall = self.data["overall"]
        self.assertEqual(self.data["total_nodes"], 297)
        self.assertEqual(overall["replayable"] + overall["not_replayable"], overall["nodes"])

    def test_gap_count_agrees_with_f10(self) -> None:
        self.assertEqual(self.data["overall"]["over_threshold"], 21)
        self.assertTrue(self.data["cross_check"]["gap_matches_expected"])

    def test_evaluable_set_matches_the_ledger(self) -> None:
        self.assertEqual(self.data["overall"]["replayable"], 248)
        self.assertTrue(self.data["cross_check"]["evaluable_matches_expected"])

    def test_gaps_are_concentrated_in_kojiki_nodes(self) -> None:
        by_kind = self.data["by_kind"]
        self.assertEqual(by_kind["kojiki"]["over_threshold"],
                         self.data["overall"]["over_threshold"])
        self.assertEqual(by_kind["eurasia"]["over_threshold"], 0)


class DocNumberGateTests(unittest.TestCase):
    """枝 #11: 総数表現のゲートと、その計数定義。"""

    def test_rules_are_configured_with_sources(self) -> None:
        rules = CFG["doc_checks"]["rules"]
        self.assertEqual(
            {r["id"] for r in rules},
            {"kojiki-node-count", "network-check-count",
             "registry-branch-count", "graph-node-count"},
        )
        for rule in rules:
            self.assertTrue(rule["source"])
            self.assertTrue(rule["patterns"])

    def test_exemption_marker_stays_sparing(self) -> None:
        marker = CFG["doc_checks"]["exempt_marker"]
        self.assertEqual(marker, "doc-number-exempt")
        hits = sum(
            1
            for path in (ROOT / "docs").rglob("*.md")
            for line in path.read_text(encoding="utf-8").splitlines()
            if marker in line
        )
        # 免除は「凍結済み過去レポートの引用」と「実験で注入した誤値の引用」に限る。
        # 予算を超えたら、規約違反か単なる増加かを人が判断する（黙って緩めない）。
        budget = CFG["doc_checks"].get("exemption_budget", 8)
        self.assertLessEqual(hits, budget,
                             "免除行が予算を超えた。引用か規約違反かを確認し、"
                             "正当なら config の exemption_budget を上げて記録する。")

    def test_network_check_counter_expands_loops(self) -> None:
        src = (ROOT / "src/verify_network.py").read_text(encoding="utf-8")
        static = sum(
            1
            for node in ast.walk(ast.parse(src))
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "add"
        )
        counted = numbers.count_network_checks(src)
        self.assertGreaterEqual(counted, static)
        self.assertEqual(counted, 60)

    def test_kojiki_node_count_comes_from_frozen_data(self) -> None:
        measured, graph = numbers.measured_values()
        self.assertEqual(measured["kojiki-node-count"], 37)
        self.assertEqual((graph["nodes"], graph["edges"]), (297, 597))

    def test_total_count_claim_is_caught_even_with_common_words(self) -> None:
        """行全体を免除する語彙リストに戻ると、このテストが落ちる（実際に起きたバグ）。"""
        rule = next(r for r in CFG["doc_checks"]["rules"]
                    if r["id"] == "kojiki-node-count")
        self.assertNotIn("対象", rule["context_allow"])
        self.assertNotIn("うち", rule["context_allow"])
        # 総数の主張は拾い、部分集合の記述は拾わない
        pattern = rule["patterns"][0]
        self.assertTrue(re.search(pattern, "ユーラシア神話群 297 ノード（古事記 40 話＋比較地域）"))
        self.assertFalse(re.search(pattern, "古事記 30 話への流入エッジは 58 本"))
        self.assertFalse(re.search(pattern, "二重評定対象の古事記 13 話（195 セル）"))

    def test_injected_wrong_total_is_rejected(self) -> None:
        """文書を改ざんしたらゲートが落ちること（ゲートが空回りしていないことの確認）。"""
        import subprocess
        target = ROOT / "docs/peer_review_summary_ja.md"
        original = target.read_text(encoding="utf-8")
        needle = "古事記 37 話＋比較地域・時代群"
        if needle not in original:
            self.skipTest("対象の文が変わっている")
        try:
            target.write_text(original.replace(needle, "古事記 40 話＋比較地域・時代群"),
                              encoding="utf-8")
            run = subprocess.run([sys.executable, str(ROOT / "src/verify_numbers.py")],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 1, run.stdout)
        finally:
            target.write_text(original, encoding="utf-8")

    def test_gate_reports_zero_violations(self) -> None:
        self.assertGreaterEqual(len(CFG["doc_checks"]["rules"]), 4)
        self.assertEqual(numbers.main(), 0)


if __name__ == "__main__":
    unittest.main()
