# -*- coding: utf-8 -*-
"""
repo_rules.py -- 「コードでは直せない設定」を毎日可視化する（枝 #14、§13.4 の 7）。

背景:
  枝 #12・#13 で分かったのは、**マージの強制力はコードではなく GitHub の ruleset が握っている**
  ということだった（§12.2 の実測: ruleset は `git push origin main` を直接拒否する）。
  先方 `AIselfMySelf` も同じ壁に当たっていて、`.github/workflows/main-guard.yml` から
  `tools/main_guard.py --strict` を毎日走らせ、**直せない設定を赤くし続けて忘れない**運用にしている。

  本リポジトリは既に ruleset が `strict` なので「守るべき設定」を機械可読な形で持ち、
  毎回突き合わせる。設定はコードで直せないが、**変わったことに気づかないのは防げる**。

  先方との違い（先方の欠陥を繰り返さない）:
    先方は文書に「main は required check 未通過のマージを受け入れる」と書きながら、
    それを直せずに `--strict` で毎日赤くしている。ここでは期待値を
    `config/analysis.json` に置き、**actual が期待から外れたときだけ**落とす。
    「毎日赤い」状態を正常にしない（赤が常態化すると誰も見なくなる）。

使い方:
  python3 src/repo_rules.py              # ローカルの期待値と現状の突合（オフライン）
  python3 src/repo_rules.py --live       # `gh api` で実際の ruleset を取得して突合
  python3 src/repo_rules.py --dump       # 現在の設定を JSON で表示（記録用）

終了コード: 0 一致 / 1 不一致 / 2 取得できない（--live で gh が失敗）
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/analysis.json"

# 実際に成立していなければならない設定（2026-11-28 に rulesets API で実測した値）
EXPECTED = {
    "ruleset_name": "main",
    "target": "branch",
    "enforcement": "active",
    "deletion": True,              # main の削除を禁止
    "non_fast_forward": True,      # force push を禁止
    "pull_request": True,          # PR を必須
    "required_status_checks": True,
    "strict_required_status_checks_policy": True,   # BEHIND ならマージ不可（§12.2 で実測）
    "required_check": "gates",
}


def config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8")).get("repo_rules", {})
    except (OSError, json.JSONDecodeError):
        return {}


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, text=True)


def live_ruleset() -> dict | None:
    """GitHub の ruleset を取得して、比較しやすい形に落とす。"""
    listing = gh("api", "repos/{owner}/{repo}/rulesets")
    if listing.returncode != 0:
        print(f"[NG] ruleset を取得できない: {listing.stderr.strip()[:200]}")
        return None
    try:
        items = json.loads(listing.stdout)
    except json.JSONDecodeError:
        print("[NG] ruleset の応答が JSON ではない")
        return None
    target = next((r for r in items if r.get("name") == EXPECTED["ruleset_name"]), None)
    if target is None:
        return {}
    detail = gh("api", f"repos/{{owner}}/{{repo}}/rulesets/{target['id']}")
    if detail.returncode != 0:
        print(f"[NG] ruleset の詳細を取得できない: {detail.stderr.strip()[:200]}")
        return None
    try:
        data = json.loads(detail.stdout)
    except json.JSONDecodeError:
        return None

    rules = {r.get("type"): r.get("parameters", {}) for r in data.get("rules", [])}
    checks = rules.get("required_status_checks", {})
    names = [c.get("context") for c in checks.get("required_status_checks", [])]
    return {
        "ruleset_name": data.get("name"),
        "target": data.get("target"),
        "enforcement": data.get("enforcement"),
        "deletion": "deletion" in rules,
        "non_fast_forward": "non_fast_forward" in rules,
        "pull_request": "pull_request" in rules,
        "required_status_checks": "required_status_checks" in rules,
        "strict_required_status_checks_policy": checks.get("strict_required_status_checks_policy"),
        "required_check": names[0] if names else None,
        "all_required_checks": names,
    }


def compare(actual: dict, expected: dict) -> list[str]:
    bad: list[str] = []
    for key, want in expected.items():
        if key == "required_check":
            got = actual.get("all_required_checks") or []
            if want not in got:
                bad.append(f"required check: 期待 {want!r} が無い（実際: {got}）")
            continue
        got = actual.get(key)
        if got != want:
            bad.append(f"{key}: 期待 {want!r} / 実際 {got!r}")
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ruleset（コードで直せない設定）を期待値と突合する")
    ap.add_argument("--live", action="store_true", help="gh api で実際の設定を取得して突合する")
    ap.add_argument("--dump", action="store_true", help="期待値を JSON で表示する")
    args = ap.parse_args(argv)

    expected = {**EXPECTED, **config().get("expected", {})}

    if args.dump:
        print(json.dumps(expected, ensure_ascii=False, indent=2))
        return 0

    if not args.live:
        # オフラインでは「何を守るべきか」を表示するだけ。落とさない（CI では --live）。
        print("[OK] 期待する ruleset 設定（オフラインのため突合はしない。--live で照合）")
        for key, want in expected.items():
            print(f"  - {key}: {want!r}")
        print("\n  実測の記録: 2026-11-28 ruleset `main`（id 28235182）")
        print("  deletion / non_fast_forward / pull_request / required_status_checks が active、")
        print("  strict_required_status_checks_policy: true、required check は `gates` 1 本。")
        return 0

    actual = live_ruleset()
    if actual is None:
        return 2
    bad = compare(actual, expected)
    for line in bad:
        print(f"[NG] {line}")
    if bad:
        print(f"\n[NG] ruleset が期待から外れている: {len(bad)} 件")
        return 1
    print("[OK] ruleset は期待どおり"
          f"（{actual['ruleset_name']} / enforcement={actual['enforcement']} / "
          f"strict={actual['strict_required_status_checks_policy']} / "
          f"required={actual.get('all_required_checks')}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
