"""生成物の鮮度（check_generated）とマージ前ゲート（merge_gate）の回帰テスト（枝 #13）。

`AIselfMySelf` の `--check-map`（生成物は手でマージせず再生成で解決する）と
`.arena/resolve_merge.py`（main を取り込んでから検証する）に相当する仕組みを、
本リポジトリで壊さないためのテスト。
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

import check_generated as CG  # noqa: E402
import merge_gate as MG  # noqa: E402

try:  # pragma: no cover - 環境依存
    import pandas  # noqa: F401

    _HAS_PANDAS = True
except ModuleNotFoundError:  # make all はシステム python で走ることがある
    _HAS_PANDAS = False

_needs_pandas = unittest.skipUnless(
    _HAS_PANDAS, "pandas が無い環境では --full の再生成を実行できない（make all の既定）")


class ManifestTests(unittest.TestCase):
    @_needs_pandas
    def test_manifest_exists_and_is_current(self) -> None:
        self.assertTrue(CG.MANIFEST.exists(), "derived/generated_manifest.json が無い")
        run = subprocess.run([sys.executable, str(ROOT / "src/check_generated.py")],
                             cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_every_target_is_covered_by_the_manifest(self) -> None:
        manifest = json.loads(CG.MANIFEST.read_text(encoding="utf-8"))
        for rel in CG.TARGETS:
            if (ROOT / rel).exists():
                self.assertIn(rel, manifest["artifacts"])

    def test_manifest_records_the_generating_code(self) -> None:
        manifest = json.loads(CG.MANIFEST.read_text(encoding="utf-8"))
        for rel, entry in manifest["artifacts"].items():
            self.assertTrue(entry["sources"], f"{rel} に生成コードが記録されていない")
            for src in entry["sources"]:
                self.assertTrue((ROOT / src).exists(), f"{rel}: {src} が無い")


class DriftDetectionTests(unittest.TestCase):
    """改ざん・再生成忘れ・申告の 3 経路を実際に踏む。"""

    def setUp(self) -> None:
        self.rel = "derived/display_reproducibility.json"
        self.path = ROOT / self.rel
        self.backup = tempfile.mktemp(suffix=".json")
        shutil.copy2(self.path, self.backup)

    def tearDown(self) -> None:
        shutil.copy2(self.backup, self.path)
        Path(self.backup).unlink(missing_ok=True)

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "src/check_generated.py"), *args],
                              cwd=ROOT, capture_output=True, text=True)

    @_needs_pandas
    def test_hand_edit_is_rejected(self) -> None:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload["overall"]["replayable"] = 999
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        self.assertEqual(self._run().returncode, 1)
        self.assertEqual(self._run("--full").returncode, 1)

    def test_declared_manual_edit_is_allowed(self) -> None:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload["overall"]["replayable"] = 999
        payload["manual_edits"] = {"reason": "テスト用の申告"}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        self.assertEqual(self._run().returncode, 0, "申告があれば通すべき")

    @_needs_pandas
    def test_regenerated_value_mismatch_is_caught_by_full(self) -> None:
        """生成物もコードも変わらないのに、再生成した値だけが違う場合を検出する。

        TARGETS の書き換えは同一プロセスでしか効かないので、subprocess ではなく
        `CG.main()` を直接呼ぶ（最初は subprocess で書いて落ちた）。
        """
        self.assertEqual(self._run("--write").returncode, 0)
        original = CG.TARGETS[self.rel]["build"]
        try:
            CG.TARGETS[self.rel]["build"] = lambda: {"tampered": True}
            self.assertEqual(CG.main(["--full"]), 1)
        finally:
            CG.TARGETS[self.rel]["build"] = original
            self.assertEqual(CG.main(["--full"]), 0)


class SummaryPickerTests(unittest.TestCase):
    def test_ran_line_is_read_from_stderr(self) -> None:
        """unittest は `Ran N tests` を stderr に書く（実測）。"""
        fake = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="noise\n\n",
            stderr="some log\n\nRan 78 tests in 2.4s\n\nOK\n",
        )
        self.assertEqual(MG.summarise(fake), "Ran 78 tests in 2.4s OK")

    def test_tagged_line_is_used_when_no_unittest_output(self) -> None:
        fake = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[UNAVAILABLE] x\n[OK] 文書数値: 違反 0 件\n", stderr="")
        self.assertEqual(MG.summarise(fake), "[OK] 文書数値: 違反 0 件")

    def test_failed_unittest_is_reported(self) -> None:
        fake = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="Ran 3 tests in 0.1s\n\nFAILED (failures=1)\n")
        self.assertIn("FAILED", MG.summarise(fake))


class MergeGateSafetyTests(unittest.TestCase):
    def test_dirty_tree_is_refused(self) -> None:
        """作業ツリーが汚れていたら、取り込まずに止まること。"""
        if not MG.is_dirty():
            probe = ROOT / "docs/_dirty_probe.md"
            probe.write_text("probe\n", encoding="utf-8")
            try:
                self.assertTrue(MG.is_dirty())
                self.assertEqual(MG.main(["--dry-run"]), 2)
            finally:
                probe.unlink(missing_ok=True)
        else:
            self.assertEqual(MG.main(["--dry-run"]), 2)

    def test_running_inside_a_merge_is_refused(self) -> None:
        """`make gate` は自分自身の unittest の中で走る。

        そのとき `.git/MERGE_HEAD` は**既に存在する**（外側のゲートが
        `git merge --no-commit` しているため）。ここで何も考えずに
        `MERGE_HEAD is None` を主張すると、外側のゲートが必ず落ちる。
        正しい契約は「マージ進行中なら取り込まずに exit 2 で止まる」こと。
        """
        if not (ROOT / ".git" / "MERGE_HEAD").exists():
            self.skipTest("マージ進行中ではない（単独実行）: 外側のゲートで検証される")
        before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                capture_output=True, text=True).stdout.strip()
        head = MG.main(["--dry-run"])
        after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                               capture_output=True, text=True).stdout.strip()
        self.assertEqual(head, 2, "マージ進行中は exit 2 で止まること")
        self.assertEqual(before, after, "HEAD を動かさないこと")
        self.assertTrue((ROOT / ".git" / "MERGE_HEAD").exists(),
                        "外側のゲートの state を壊さないこと")

    def test_merge_in_progress_guard_is_first(self) -> None:
        """マージ進行中のガードが dirty 判定より先に効いていること。

        `is_dirty()` をスタブして「clean」に見せても、ガードが先なら exit 2。
        ここが逆順だと、外側のゲートの中では dirty 扱いで止まるのか
        マージ進行で止まるのかが曖昧になる。
        """
        orig = MG.is_dirty
        MG.is_dirty = lambda: False
        try:
            if (ROOT / ".git" / "MERGE_HEAD").exists():
                self.assertEqual(MG.main(["--dry-run"]), 2)
            else:
                # マージ進行中でなければ、clean 扱いなので素通りする（0 か 3）
                self.assertIn(MG.main(["--dry-run"]), (0, 3))
        finally:
            MG.is_dirty = orig


if __name__ == "__main__":
    unittest.main()
