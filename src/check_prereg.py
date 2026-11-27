# -*- coding: utf-8 -*-
"""
check_prereg.py -- 事前登録が結果より先に固定されていたことを git 履歴で確認する。

規則:
  docs/prereg/*.md が存在する場合、その最初のコミット時刻は
  config/analysis.json の最終変更コミット時刻より前でなければならない。
  （判定基準を結果を見てから動かしていないことの客観証拠）

git 管理下でない場合、または事前登録ファイルが無い場合は警告のみで通す。
"""
from __future__ import annotations
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def first_commit_ts(path):
    out = git("log", "--diff-filter=A", "--format=%ct", "--", path).stdout.split()
    return int(out[-1]) if out else None


def last_commit_ts(path):
    out = git("log", "--format=%ct", "--", path).stdout.split()
    return int(out[0]) if out else None


def main():
    if git("rev-parse", "--is-inside-work-tree").returncode != 0:
        print("[skip] git 管理下ではないため、事前登録の順序は検査しない")
        return 0
    pre = sorted(Path(ROOT / "docs/prereg").glob("*.md"))
    pre = [p for p in pre if p.name.lower() != "template.md"]
    if not pre:
        print("[warn] docs/prereg/*.md が無い。初回コミット前なら問題ない")
        return 0
    cfg = last_commit_ts("config/analysis.json")
    bad = []
    for p in pre:
        t = first_commit_ts(str(p.relative_to(ROOT)))
        if t is None:
            print(f"[warn] {p.name}: 未コミット")
            continue
        if cfg is not None and t > cfg:
            bad.append((p.name, t, cfg))
        else:
            print(f"[ok] {p.name}: 事前登録 {t} <= 設定最終変更 {cfg}")
    for nm, t, c in bad:
        print(f"[NG] {nm}: 事前登録のコミット {t} が設定変更 {c} より後になっている")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
