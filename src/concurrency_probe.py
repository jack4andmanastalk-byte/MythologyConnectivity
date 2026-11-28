# -*- coding: utf-8 -*-
"""
concurrency_probe.py -- 出力の並行安全性を実測する（枝 #12 NET-OUTPUT-ISOLATION）。

`docs/path_connectivity_validity_review_20261128_ja.md` §11 で測った 4 つの破損を、
`src/analysis_io.py` を適用した後に再測する。数値は実測して出力するだけで、
しきい値は設定に置く（`config/analysis.json` の `concurrency_probe`）。

検査:
  1. 読み手が壊れた JSON を掴むか      -> 期待 0 回
  2. 読み手が行数の足りない CSV を掴むか -> 期待 0 回
  3. 同一出力先の二重起動を止めるか     -> 期待 1 本だけ取得・他は OutputLocked
  4. 出力先を分けたら同時に走れるか     -> 期待 2 本とも成功

実行: python3 src/concurrency_probe.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import analysis_io as IO  # noqa: E402

CFG = json.loads((ROOT / "config/analysis.json").read_text(encoding="utf-8"))
PROBE = CFG.get("concurrency_probe", {})
DURATION = float(PROBE.get("duration_seconds", 4.0))
ROWS = int(PROBE.get("csv_rows", 40000))
PAYLOAD_FIELDS = int(PROBE.get("json_payload_fields", 4000))
FIELD_CHAR = int(PROBE.get("char_per_field", 200))


def _payload(size: int | None = None) -> str:
    size = PAYLOAD_FIELDS if size is None else size
    return json.dumps({"schema": "probe", "payload": ["x" * FIELD_CHAR] * size},
                      ensure_ascii=False, indent=2)


def probe_torn_reads(workdir: Path) -> dict:
    """1 書き手 + 3 読み手。原子的書き込みなら部分読みは 0 回になる。"""
    target = workdir / "probe.json"
    IO.write_json_atomic(target, {"schema": "probe", "payload": ["x" * FIELD_CHAR] * PAYLOAD_FIELDS})
    stop = threading.Event()
    writes = {"n": 0}
    reads = {"ok": 0, "torn": 0, "missing": 0}

    def writer() -> None:
        while not stop.is_set():
            IO.write_text_atomic(target, _payload())
            writes["n"] += 1

    def reader() -> None:
        while not stop.is_set():
            try:
                json.loads(target.read_text(encoding="utf-8"))
                reads["ok"] += 1
            except json.JSONDecodeError:
                reads["torn"] += 1
            except FileNotFoundError:
                reads["missing"] += 1

    threads = [threading.Thread(target=writer)]
    threads += [threading.Thread(target=reader) for _ in range(3)]
    for t in threads:
        t.start()
    stop.wait(DURATION)
    stop.set()
    for t in threads:
        t.join()
    return dict(written=writes["n"], **reads)


def probe_csv_reads(workdir: Path) -> dict:
    """CSV を書きながら pandas で読む。原子的書き込みなら短い行は 0 回。"""
    import pandas as pd

    target = workdir / "probe.csv"
    frame = pd.DataFrame({"id": [f"n{i}" for i in range(ROWS)], "value": range(ROWS)})
    IO.write_dataframe_atomic(frame, target, index=False)
    stop = threading.Event()
    stats = {"ok": 0, "short": 0, "error": 0}

    def writer() -> None:
        while not stop.is_set():
            IO.write_dataframe_atomic(frame, target, index=False)

    def reader() -> None:
        while not stop.is_set():
            try:
                got = pd.read_csv(target)
                if len(got) == ROWS:
                    stats["ok"] += 1
                else:
                    stats["short"] += 1
            except Exception:  # noqa: BLE001 - 破損の検出が目的
                stats["error"] += 1

    threads = [threading.Thread(target=writer)]
    threads += [threading.Thread(target=reader) for _ in range(2)]
    for t in threads:
        t.start()
    stop.wait(DURATION)
    stop.set()
    for t in threads:
        t.join()
    return stats


LOCK_CHILD = """
import json, sys, time
from pathlib import Path
sys.path.insert(0, {src!r})
import analysis_io as IO
try:
    with IO.directory_lock(Path({out!r}), wait=0):
        print("acquired", flush=True)
        time.sleep(1.5)
except IO.OutputLocked:
    print("locked", flush=True)
"""


def probe_double_start(base: Path) -> dict:
    """同じ出力先を 2 プロセスが同時に掴もうとしたとき、片方だけが通るか。"""
    out = base / "shared"
    out.mkdir(parents=True, exist_ok=True)
    script = LOCK_CHILD.format(src=str(ROOT / "src"), out=str(out))
    env = dict(os.environ)
    env.pop(IO.ENV_VAR, None)
    procs = [subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, env=env)
             for _ in range(2)]
    results = []
    for p in procs:
        stdout, _ = p.communicate(timeout=60)
        results.append(stdout.strip().splitlines()[-1] if stdout.strip() else "no-output")
    return {"acquired": results.count("acquired"), "locked": results.count("locked"),
            "results": results}


def probe_isolated(base: Path) -> dict:
    """出力先を分ければ、同じ瞬間に 2 本とも通るか。"""
    script = LOCK_CHILD.replace("time.sleep(1.5)", "pass")
    got = []
    for name in ("w1", "w2"):
        out = base / name
        out.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env[IO.ENV_VAR] = str(out)
        p = subprocess.run([sys.executable, "-c",
                            script.format(src=str(ROOT / "src"), out=str(out))],
                           capture_output=True, text=True, env=env, timeout=60)
        got.append((p.stdout.strip().splitlines() or ["no-output"])[-1])
    return {"acquired": got.count("acquired"), "locked": got.count("locked")}


def main() -> int:
    results: dict = {}
    with tempfile.TemporaryDirectory(prefix="concurrency-probe-") as tmp:
        base = Path(tmp)
        print("1) 原子的な JSON 書き込み ...")
        results["json"] = probe_torn_reads(base)
        print("2) 原子的な CSV 書き込み ...")
        results["csv"] = probe_csv_reads(base)
        print("3) 同一出力先の二重起動 ...")
        results["double_start"] = probe_double_start(base)
        print("4) 出力先の分離 ...")
        results["isolated"] = probe_isolated(base)

    checks = {
        "no_torn_json": results["json"]["torn"] == 0,
        "no_missing_json": results["json"]["missing"] == 0,
        "no_short_csv": results["csv"]["short"] == 0,
        "no_csv_error": results["csv"]["error"] == 0,
        "double_start_blocked": (results["double_start"]["acquired"] == 1
                                 and results["double_start"]["locked"] == 1),
        "isolated_both_run": results["isolated"]["acquired"] == 2,
    }
    ok = all(checks.values())
    out = IO.output_dir()
    IO.write_json_atomic(out / "concurrency_probe.json",
                         {"schema": "concurrency-probe/1", "results": results, "checks": checks,
                          "ok": ok, "duration_seconds": DURATION,
                          "output_dir": str(out.relative_to(ROOT) if out.is_relative_to(ROOT) else out)})
    print(json.dumps({"results": results, "checks": checks}, ensure_ascii=False, indent=2))
    print(("[OK] " if ok else "[NG] ") + "並行安全性: " +
          ", ".join(f"{k}={'OK' if v else 'NG'}" for k, v in checks.items()))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
