"""出力の分離・原子的書き込み・排他ロックの回帰テスト（枝 #12 NET-OUTPUT-ISOLATION）。

レビュー §11 で実測した破損（部分読み・CSV の短い行・二重起動）を、
`src/analysis_io.py` の適用後に再発させないためのテスト。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import analysis_io as IO  # noqa: E402


class OutputDirTests(unittest.TestCase):
    def test_env_var_wins_over_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get(IO.ENV_VAR)
            os.environ[IO.ENV_VAR] = tmp
            try:
                self.assertEqual(IO.output_dir(), Path(tmp))
            finally:
                if old is None:
                    os.environ.pop(IO.ENV_VAR, None)
                else:
                    os.environ[IO.ENV_VAR] = old

    def test_default_is_config_dir_under_root(self) -> None:
        old = os.environ.pop(IO.ENV_VAR, None)
        try:
            self.assertEqual(IO.output_dir(), ROOT / "outputs")
        finally:
            if old is not None:
                os.environ[IO.ENV_VAR] = old

    def test_two_workers_get_different_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            old = os.environ.get(IO.ENV_VAR)
            try:
                os.environ[IO.ENV_VAR] = str(a)
                got_a = IO.output_dir()
                os.environ[IO.ENV_VAR] = str(b)
                got_b = IO.output_dir()
            finally:
                if old is None:
                    os.environ.pop(IO.ENV_VAR, None)
                else:
                    os.environ[IO.ENV_VAR] = old
            self.assertNotEqual(got_a, got_b)
            self.assertTrue(got_a.is_dir() and got_b.is_dir())


class AtomicWriteTests(unittest.TestCase):
    def test_no_partial_json_is_ever_visible(self) -> None:
        """書き込み中の読み手が壊れた JSON を掴まないこと（§11 の 6810 回の再発防止）。"""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "x.json"
            IO.write_json_atomic(target, {"n": 0})
            stop = threading.Event()
            bad = {"n": 0}

            def writer() -> None:
                i = 0
                while not stop.is_set():
                    IO.write_json_atomic(target, {"n": i, "pad": "x" * 5000})
                    i += 1

            def reader() -> None:
                while not stop.is_set():
                    try:
                        json.loads(target.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        bad["n"] += 1
                    except FileNotFoundError:
                        bad["n"] += 1

            threads = [threading.Thread(target=writer)] + \
                      [threading.Thread(target=reader) for _ in range(3)]
            for t in threads:
                t.start()
            stop.wait(2.0)
            stop.set()
            for t in threads:
                t.join()
            self.assertEqual(bad["n"], 0)

    def test_no_temp_files_are_left_behind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(20):
                IO.write_text_atomic(Path(tmp) / "a.txt", f"v{i}")
            leftovers = [p.name for p in Path(tmp).iterdir() if p.name.startswith(".")]
            self.assertEqual(leftovers, [])

    def test_failed_write_does_not_clobber_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "keep.json"
            IO.write_json_atomic(target, {"ok": True})

            class Boom:
                def __str__(self) -> str:
                    raise RuntimeError("boom")

            with self.assertRaises(Exception):
                IO.write_json_atomic(target, {"ok": Boom()})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"ok": True})


class DirectoryLockTests(unittest.TestCase):
    def test_second_lock_in_same_process_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with IO.directory_lock(out, wait=0):
                with self.assertRaises(IO.OutputLocked):
                    with IO.directory_lock(out, wait=0):
                        pass
            # 解放後は取れる
            with IO.directory_lock(out, wait=0):
                pass

    def test_lock_released_after_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with self.assertRaises(ValueError):
                with IO.directory_lock(out, wait=0):
                    raise ValueError("boom")
            with IO.directory_lock(out, wait=0):
                pass

    def test_other_process_is_locked_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            # 注意: `IO.directory_lock(...).__enter__()` と書くと、コンテキスト
            # マネージャの一時オブジェクトが GC されて flock が解放される（実測）。
            # 実運用と同じ `with` 文で保持すること。
            script = "\n".join([
                "import sys, time",
                "sys.path.insert(0, %r)" % str(ROOT / "src"),
                "import analysis_io as IO",
                "from pathlib import Path",
                "with IO.directory_lock(Path(%r), wait=0):" % str(out),
                "    print('held', flush=True)",
                "    time.sleep(2.0)",
            ])
            proc = subprocess.Popen([sys.executable, "-c", script],
                                    stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(proc.stdout.readline().strip(), "held")
                with self.assertRaises(IO.OutputLocked):
                    with IO.directory_lock(out, wait=0):
                        pass
            finally:
                proc.kill()
                proc.wait(timeout=10)
                if proc.stdout:
                    proc.stdout.close()


class ProbeReportTests(unittest.TestCase):
    def test_probe_report_matches_preregistration(self) -> None:
        path = ROOT / "outputs/concurrency_probe.json"
        if not path.exists():
            raise unittest.SkipTest("outputs/concurrency_probe.json が無い（make probe 未実行）")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(data["ok"], data["checks"])
        self.assertEqual(data["results"]["double_start"]["acquired"], 1)
        self.assertEqual(data["results"]["isolated"]["acquired"], 2)


if __name__ == "__main__":
    unittest.main()
