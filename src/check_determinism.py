# -*- coding: utf-8 -*-
"""
check_determinism.py -- 同じ入力を 2 回流して生成物が一致することを確認する。

比較対象: outputs/ 内の全ファイル。results.json は時刻・実行時間の項目だけを除いて比較する。
"""
from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
VOLATILE = ("generated_at", "runtime_sec")
SKIP = ("manifest.sha256",)          # 他ファイルのハッシュなので上位で決まる
STAMP_PREFIX = "生成:"               # レポート冒頭の生成時刻行は結果ではない


def snapshot():
    snap = {}
    for p in sorted(OUT.glob("*")):
        if not p.is_file():
            continue
        if p.name in SKIP:
            continue
        if p.suffix == ".md":
            txt = "\n".join(l for l in p.read_text(encoding="utf-8").splitlines()
                             if not l.lstrip().startswith(STAMP_PREFIX))
            snap[p.name] = hashlib.sha256(txt.encode()).hexdigest()
            continue
        if p.name == "results.json":
            d = json.loads(p.read_text(encoding="utf-8"))
            for k in VOLATILE:
                d.get("meta", {}).pop(k, None)
            snap[p.name] = hashlib.sha256(
                json.dumps(d, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        else:
            snap[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return snap


def run():
    r = subprocess.run([sys.executable, str(ROOT / "src/run_all.py")],
                       cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:])
        print(r.stderr[-2000:])
        raise SystemExit("run_all.py が失敗した")


def main():
    run()
    a = snapshot()
    run()
    b = snapshot()
    diff = [k for k in a if a.get(k) != b.get(k)]
    print(f"比較ファイル {len(a)} 件 / 不一致 {len(diff)} 件")
    for k in diff:
        print(f"  [NG] {k}")
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main())
