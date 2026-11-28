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


class ManifestTests(unittest.TestCase):
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

    def test_dry_run_does_not_merge(self) -> None:
        before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                capture_output=True, text=True).stdout.strip()
        MG.main(["--dry-run"])
        after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                               capture_output=True, text=True).stdout.strip()
        self.assertEqual(before, after)
        self.assertFalse((ROOT / ".git" / "MERGE_HEAD").exists())


if __name__ == "__main__":
    unittest.main()
