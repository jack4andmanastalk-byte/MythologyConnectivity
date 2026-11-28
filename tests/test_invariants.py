"""不変性・ID 採番・ruleset 突合の回帰テスト（枝 #14）。

`AIselfMySelf` の `append_only_check.py` / `new_id.py` / `main_guard.py` に相当する仕組みを、
本リポジトリの**実測に合わせた規則**で壊さないためのテスト。

このファイルが守っている最大の教訓は「先方の規則をそのまま移植すると誤検出する」こと。
本リポジトリの登録簿は **結果セルを後から書く**規則なので、行のバイト不変を要求すると
正しい運用が落ちる（実測: c106f98 で行 5–7 の結果が pending -> 実測値に変わっている）。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import append_only as AO  # noqa: E402
import check_registry as CR  # noqa: E402
import new_id as NI  # noqa: E402
import repo_rules as RR  # noqa: E402

CFG = {**AO.DEFAULTS, **AO.config()}


# ------------------------------------------------------------------ 台帳の解析
class ParseTableTests(unittest.TestCase):
    def test_columns_are_matched_by_name_not_position(self) -> None:
        """列が増えても、内容が無傷なら違反にしない（cb39f8e の実例）。

        cb39f8e で 9 列 -> 10 列になり、既存 4 行は 1 セルずつずれた。
        バイト列で比べると全行が違反になるが、列名で対応づけると無傷。
        """
        old = ("| # | 枝 ID | 仮説 | 結果 |\n| ---: | :--- | :--- | :--- |\n"
               "| 1 | L2-15D | 王権モチーフ | pending |\n")
        new = ("| # | 日付 | 枝 ID | 仮説 | 結果 |\n| ---: | :--- | :--- | :--- | :--- |\n"
               "| 1 | 2026-11-27 | L2-15D | 王権モチーフ | pending |\n")
        self.assertEqual(AO.check_registry_between(old, new, CFG), [])

    def test_ragged_row_is_ignored_not_crashed(self) -> None:
        text = "| # | 枝 ID |\n| ---: | :--- |\n| 1 | A |\n| 2 |\n"
        header, rows = AO.parse_table(text, "#")
        self.assertEqual(header, ["#", "枝 ID"])
        self.assertEqual(list(rows), ["1"])


# ------------------------------------------------------------------ 不変性の規則
class AppendOnlyRulesTests(unittest.TestCase):
    OLD = ("| # | 日付 | 枝 ID | 種別 | 仮説 | 主エンドポイント | 結果 | p | 効果量 | 判定 |\n"
           "| ---: | :--- | :--- | :--- | :--- | :--- | :--- | ---: | ---: | :--- |\n"
           "| 1 | 2026-11-27 | L2-15D | 仮説検定 | 王権モチーフ | z の平均 | pending | pending | pending | 事前登録済み |\n")

    def _row(self, **cells: str) -> str:
        base = {"#": "1", "日付": "2026-11-27", "枝 ID": "L2-15D", "種別": "仮説検定",
                "仮説": "王権モチーフ", "主エンドポイント": "z の平均",
                "結果": "pending", "p": "pending", "効果量": "pending", "判定": "事前登録済み"}
        base.update(cells)
        order = ["#", "日付", "枝 ID", "種別", "仮説", "主エンドポイント", "結果", "p", "効果量", "判定"]
        return "| " + " | ".join(base[c] for c in order) + " |\n"

    def _check(self, new_row: str) -> list[str]:
        header = self.OLD.split("\n")[0] + "\n" + self.OLD.split("\n")[1] + "\n"
        return AO.check_registry_between(self.OLD, header + new_row, CFG)

    def test_result_cell_filled_from_pending_is_allowed(self) -> None:
        """結果は pending から 1 回だけ書ける（登録簿の規則そのもの）。"""
        self.assertEqual(self._check(self._row(結果="3.020", p="0.498")), [])

    def test_pending_marker_counts_as_pending(self) -> None:
        """`事前登録済み` は「結果前」の印。確定値ではないので前進してよい。

        実測: c106f98 で 判定 が `事前登録済み` -> 確定文言に変わっている。
        これを違反にすると、正しい運用が落ちる（最初そう書いて 3 件誤検出した）。
        """
        self.assertEqual(self._check(self._row(判定="情報を認めない")), [])

    def test_confirmed_result_cannot_be_rewritten(self) -> None:
        old = self.OLD.replace("| pending | pending | pending | 事前登録済み |",
                               "| 3.020 | 0.498 | −0.04 | 情報を認めない |")
        header = old.split("\n")[0] + "\n" + old.split("\n")[1] + "\n"
        new = header + self._row(結果="3.020", p="0.498", 効果量="−0.04", 判定="情報を認めない") + ""
        self.assertEqual(AO.check_registry_between(old, new, CFG), [])   # 無変化は無傷
        new = header + self._row(結果="9.999", p="0.498", 効果量="−0.04", 判定="情報を認めない")
        bad = AO.check_registry_between(old, new, CFG)
        self.assertTrue(bad and "確定済み" in bad[0], bad)

    def test_preregistered_hypothesis_cell_cannot_change(self) -> None:
        """仮説・主エンドポイントは登録後に 1 文字も変えられない。"""
        bad = self._check(self._row(仮説="王権モチーフ（緩和）"))
        self.assertTrue(bad and "事前登録セル" in bad[0], bad)

    def test_row_deletion_is_rejected(self) -> None:
        header = self.OLD.split("\n")[0] + "\n"
        self.assertTrue(AO.check_registry_between(self.OLD, header, CFG))

    def test_whitespace_emphasis_difference_is_ignored(self) -> None:
        self.assertEqual(self._check(self._row(仮説="**王権** モチーフ")), [])


# ------------------------------------------------------------------ git を要する検査
def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


@unittest.skipUnless(_git("rev-parse", "--is-inside-work-tree").returncode == 0, "git 管理下でない")
class RepositoryInvariantTests(unittest.TestCase):
    def test_registry_history_has_no_violation(self) -> None:
        """全履歴を走査して、事前登録セルの書き換えが 1 件も無いこと。"""
        bad = AO.history_violations(CFG["registry"], CFG)
        self.assertEqual(bad, [], "履歴に不変性違反がある: " + "\n".join(bad[:3]))

    def test_frozen_blobs_are_found(self) -> None:
        """凍結データの一覧が空にならないこと（`ls-tree` の pathspec で空振りした実例）。"""
        blobs = AO.base_blobs("HEAD", CFG["frozen_glob"])
        self.assertGreaterEqual(len(blobs), 3, f"凍結データが見つからない: {blobs}")

    def test_frozen_override_is_detected(self) -> None:
        """凍結 CSV を 1 バイト変えたら検出すること（インデックスではなく作業ツリーを見る）。"""
        target = ROOT / "data/frozen/nodes_297.csv"
        backup = tempfile.mktemp(suffix=".csv")
        shutil.copy2(target, backup)
        try:
            raw = target.read_bytes()
            target.write_bytes(raw.replace(b"id,", b"ID,", 1))
            bad = AO.check_frozen("HEAD", CFG["frozen_glob"])
            self.assertTrue(bad, "作業ツリーの変更を検出できていない")
            self.assertIn("nodes_297.csv", bad[0])
        finally:
            shutil.copy2(backup, target)
            Path(backup).unlink(missing_ok=True)


# ------------------------------------------------------------------ 登録簿の構造
class RegistryStructureTests(unittest.TestCase):
    def _rows(self, *numbers: str):
        return [{"#": n, "枝 ID": f"B{n}", "日付": f"2026-11-{i + 1:02d}"}
                for i, n in enumerate(numbers)]

    def test_current_registry_is_well_formed(self) -> None:
        rows = CR.parse_registry((ROOT / "docs/registry.md").read_text(encoding="utf-8"))
        self.assertEqual(CR.check_structure(rows), [])

    def test_gap_in_numbers_is_rejected(self) -> None:
        self.assertTrue(CR.check_structure(self._rows("1", "3")))

    def test_duplicate_branch_id_is_rejected(self) -> None:
        rows = self._rows("1", "2")
        rows[1]["枝 ID"] = rows[0]["枝 ID"]
        self.assertTrue(CR.check_structure(rows))

    def test_non_monotonic_date_is_rejected(self) -> None:
        rows = self._rows("1", "2")
        rows[1]["日付"] = "2026-10-01"
        self.assertTrue(CR.check_structure(rows))


# ------------------------------------------------------------------ ID 採番
class NewIdTests(unittest.TestCase):
    def test_format_and_prefix(self) -> None:
        taken = NI.existing_ids(NI.DEFAULTS["shards"])
        generated = NI.make_id("TASK", 6, taken, "20261128")
        self.assertRegex(generated, r"^TASK-20261128-[a-z0-9]{6}$")
        self.assertNotIn(generated, taken)

    def test_exhausted_space_raises_instead_of_looping_forever(self) -> None:
        with self.assertRaises(RuntimeError):
            # 1 桁で 36 通り全部埋めた状態
            NI.make_id("X", 1, {f"X-20261128-{c}" for c in NI._ALPHABET}, "20261128")

    def test_check_mode_detects_existing_branch_id(self) -> None:
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(NI.main(["--check", "NET-597"]), 1)
            self.assertEqual(NI.main(["--check", "TASK-20991231-nothere"]), 0)

    def test_ids_are_collected_from_both_shard_kinds(self) -> None:
        """JSON（work_queue）と Markdown（registry）の両方から拾えていること。"""
        ids = NI.existing_ids(NI.DEFAULTS["shards"])
        self.assertIn("NET-597", ids)                 # registry.md から
        queue = json.loads((ROOT / "config/work_queue.json").read_text(encoding="utf-8"))
        tasks = queue.get("tasks", queue) if isinstance(queue, dict) else queue
        self.assertTrue(tasks, "work_queue にタスクが無いと検査にならない")
        for task in tasks:
            self.assertIn(task["id"], ids)            # work_queue.json から


# ------------------------------------------------------------------ ruleset
class RepoRulesTests(unittest.TestCase):
    def test_expected_setting_is_complete(self) -> None:
        for key in ("enforcement", "strict_required_status_checks_policy", "required_check"):
            self.assertIn(key, RR.EXPECTED)

    def test_compare_detects_a_relaxed_policy(self) -> None:
        """`strict` が false に戻ったら落ちること（先方の既知の欠陥と同じ状態）。"""
        actual = dict(RR.EXPECTED, all_required_checks=["gates"],
                      strict_required_status_checks_policy=False)
        bad = RR.compare(actual, RR.EXPECTED)
        self.assertTrue(any("strict" in b for b in bad), bad)

    def test_compare_detects_missing_required_check(self) -> None:
        actual = dict(RR.EXPECTED, all_required_checks=["validate"])
        bad = RR.compare(actual, RR.EXPECTED)
        self.assertTrue(any("required check" in b for b in bad), bad)

    def test_offline_mode_never_fails(self) -> None:
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(RR.main([]), 0)


if __name__ == "__main__":
    unittest.main()
