# -*- coding: utf-8 -*-
"""
merge_gate.py -- `origin/main` を取り込んだ状態でゲートを回す（マージ前の再検証）。

背景（`docs/path_connectivity_validity_review_20261128_ja.md` §12.3・§13.4 #4）:
  PR の CI は head SHA を検査する。main とマージした結果は検査しない。
  「両方 green でも統合すると壊れる」意味的競合は、**main を取り込んだ状態で
  ゲートを回して初めて**見つかる。

  ただし main を取り込むと、作業ツリーと index が一時的に書き換わる。事故を避けるため
  このスクリプトは次の順で動き、**必ず元の状態に戻す**。

  1. 作業ツリーが汚れていたら中止する（`--allow-dirty` で強行できるが推奨しない）
  2. `git fetch origin main`
  3. `git merge --no-commit --no-ff origin/main`（取り込むだけでコミットしない）
  4. `make prereg registry validate audit test numbers generated` を実行
  5. `git merge --abort` で必ず元に戻す（成功・失敗どちらでも）

  `AIselfMySelf` の `.arena/resolve_merge.py` が既知の競合だけを機械解決するのに対し、
  こちらは**解決しない**。競合したら「人間が解決すべき」として停止する（未知の競合を
  黙って解決すると、追記専用の台帳を壊す側に倒れるため）。

使い方:
    python3 src/merge_gate.py              # main を取り込んでゲート
    python3 src/merge_gate.py --dry-run    # 取り込まずに、遅れているコミット数だけ出す
    python3 src/merge_gate.py --allow-dirty

終了コード: 0 通過 / 1 ゲート失敗 / 2 競合・中止 / 3 取り込むものが無い（通過扱い）
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 取り込んだ状態で回すゲート（重い `sim` と `run` は含めない。`make all` は呼び出し側で）
GATES = [
    ["python3", "src/check_prereg.py"],
    ["python3", "src/check_registry.py"],
    ["python3", "src/validate.py"],
    ["python3", "src/audit_no_hardcode.py"],
    ["python3", "-m", "unittest", "discover", "-s", "tests"],
    ["python3", "src/verify_numbers.py"],
    ["python3", "src/check_generated.py"],
]


def sh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=ROOT, capture_output=True, text=True, check=False)


def git(*args: str) -> subprocess.CompletedProcess:
    return sh("git", *args)


def is_dirty() -> bool:
    return bool(git("status", "--porcelain").stdout.strip())


def behind_count() -> int:
    out = git("rev-list", "--count", "HEAD..origin/main")
    return int(out.stdout.strip() or 0) if out.returncode == 0 else 0


def merge_in_progress() -> bool:
    return (ROOT / ".git" / "MERGE_HEAD").exists()


def summarise(run: subprocess.CompletedProcess) -> str:
    """ゲートの出力から 1 行だけ要約を選ぶ。

    unittest は `Ran N tests` と直後の `OK`/`FAILED` を使う。それ以外は
    「[OK]/[NG] で始まる行の最後」。テストが意図的に出す [UNAVAILABLE] は
    選ばない（実測でこれを要約に拾って誤読した）。
    """
    # unittest は `Ran N tests` と結果を **stderr** に書く（実測）。両方を結合して探す。
    lines = [ln.strip() for ln in (run.stdout + "\n" + run.stderr).splitlines() if ln.strip()]
    ran = [i for i, ln in enumerate(lines) if ln.startswith("Ran ")]
    if ran:
        i = ran[-1]
        # `Ran N tests` の直後は空行、その次が `OK` / `FAILED (...)`（実測）
        result = next((ln for ln in lines[i + 1:] if ln.startswith(("OK", "FAILED"))), "")
        return f"{lines[i]} {result}".strip()
    tagged = [ln for ln in lines if ln.startswith(("[OK]", "[ok]", "[NG]", "[write]"))]
    if tagged:
        return tagged[-1]
    return lines[-1] if lines else (run.stderr.strip().splitlines() or [""])[-1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="origin/main を取り込んだ状態でゲートを回す")
    ap.add_argument("--dry-run", action="store_true", help="取り込まずに遅れだけ表示")
    ap.add_argument("--allow-dirty", action="store_true", help="作業ツリーが汚れていても強行")
    args = ap.parse_args(argv)

    if merge_in_progress():
        print("[NG] マージが進行中。先に `git merge --abort` か `git commit` で片付ける")
        return 2

    if git("rev-parse", "--is-inside-work-tree").returncode != 0:
        print("[skip] git 管理下ではない")
        return 2

    if is_dirty() and not args.allow_dirty:
        print("[NG] 作業ツリーに未コミットの変更がある。commit / stash してから実行する")
        return 2

    fetch = git("fetch", "-q", "origin", "main")
    if fetch.returncode != 0:
        print("[NG] git fetch に失敗:\n" + (fetch.stderr or "").strip())
        return 2

    n = behind_count()
    if n == 0:
        print("[OK] origin/main は既に取り込み済み（遅れ 0 コミット）")
        return 3
    print(f"[info] origin/main より {n} コミット遅れている")

    if args.dry_run:
        print("[dry-run] 取り込みは行わない")
        return 0

    merged = git("-c", "user.name=merge-gate", "-c", "user.email=merge-gate@local",
                 "merge", "--no-commit", "--no-ff", "origin/main")
    if merged.returncode != 0:
        conflicted = git("diff", "--name-only", "--diff-filter=U").stdout.split()
        print("[NG] origin/main の取り込みで競合した。人間が解決すること（このツールは解決しない）")
        for name in conflicted:
            print("  競合: " + name)
        git("merge", "--abort")
        return 2

    failures = []
    try:
        for cmd in GATES:
            label = " ".join(cmd[1:]) if cmd[0].endswith("python3") else " ".join(cmd)
            run = subprocess.run([sys.executable if cmd[0] == "python3" else cmd[0], *cmd[1:]],
                                 cwd=ROOT, capture_output=True, text=True)
            ok = run.returncode == 0
            print(("[OK]  " if ok else "[NG]  ") + label + ": " + summarise(run))

            if not ok:
                failures.append((label, run))
    finally:
        # 成功しても失敗しても必ず元に戻す
        aborted = git("merge", "--abort")
        if aborted.returncode != 0:
            print("[warn] git merge --abort に失敗。手で `git merge --abort` を実行すること")
            print(aborted.stderr.strip())

    if failures:
        print(f"\n[NG] main 取り込み後のゲートで {len(failures)} 件失敗した")
        for label, run in failures:
            print(f"\n--- {label} ---")
            print((run.stdout or "")[-2000:])
            print((run.stderr or "")[-1000:])
        return 1

    print(f"\n[OK] origin/main（{n} コミット）を取り込んだ状態で全ゲート通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
