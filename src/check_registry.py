# -*- coding: utf-8 -*-
"""
check_registry.py -- docs/registry.md の登録枝数から Holm しきい値と必要置換回数を自動算出し、
config/analysis.json の inference.n_perm と本文記載値が要件を満たしているかを検証する。

規則 (ADR 0002 / R1, R2):
  * 種別が「仮説検定」である登録枝数 N を数える。
  * Holm 第1しきい値 = alpha / N
  * 最小到達可能 p = 1 / (n_perm + 1) <= alpha / N を満たす必要置換回数
      n_needed = ceil(N / alpha) - 1
  * config/analysis.json の inference.n_perm < n_needed の場合は exit 1（CI を落とす）。
  * --update-config を明示した場合は、不足分の n_perm を n_needed へ自動引き上げする。
"""
from __future__ import annotations
import argparse, json, math, re, sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HYPOTHESIS_KIND = "仮説検定"
NON_HYP_HINTS = ("仮説検定ではなく", "データ仮説ではない", "整合性検査", "方法論", "信頼性測定")


def parse_registry(md_text: str) -> list[dict]:
    """Markdown テーブルの行を抽出して辞書リストを返す。"""
    lines = md_text.splitlines()
    headers = None
    rows = []
    for line in lines:
        s = line.strip()
        if not s.startswith("|"):
            if headers is not None and rows:
                break
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if headers is None:
            headers = cells
            continue
        if all(re.fullmatch(r":?-+:?", c) for c in cells):
            continue
        if len(cells) != len(headers):
            continue
        rows.append(dict(zip(headers, cells)))
    return rows


def is_hypothesis_row(row: dict) -> bool:
    if "種別" in row:
        return row["種別"] == HYPOTHESIS_KIND
    hyp = row.get("仮説", "")
    return not any(h in hyp for h in NON_HYP_HINTS)


def compute_holm_requirements(n_branches: int, alpha: float) -> tuple[float, int]:
    """Holm 第1しきい値と必要最小置換回数 ceil(N / alpha) - 1 を厳密に計算する。"""
    thr = float(Decimal(str(alpha)) / Decimal(n_branches))
    ratio = Decimal(n_branches) / Decimal(str(alpha))
    need_perm = int(math.ceil(ratio)) - 1
    return thr, need_perm


def check_doc_declarations(md_text: str, n_branches: int, thr: float, need_perm: int) -> list[str]:
    errs = []
    m_cnt = re.search(r"登録枝数（仮説検定のみ）\s*:\s*\*\*(\d+)\*\*", md_text)
    if m_cnt:
        doc_n = int(m_cnt.group(1))
        if doc_n != n_branches:
            errs.append(
                f"docs/registry.md の登録枝数宣言 ({doc_n}) が実測 ({n_branches}) と一致しない"
            )
    m_thr = re.search(
        r"Holm\s*補正後の第1しきい値\s*:[^=\n]*=\s*([0-9]+(?:\.[0-9]+)?(?:e[+-]?\d+)?)",
        md_text,
        re.IGNORECASE,
    )
    if m_thr:
        raw_str = m_thr.group(1)
        doc_thr = float(raw_str)
        if "." in raw_str and "e" not in raw_str.lower():
            decimals = len(raw_str.split(".")[1])
            tol = 0.5 * (10.0 ** (-decimals)) + 1e-12
        else:
            tol = max(abs(thr) * 0.05, 1e-9)
        if abs(doc_thr - thr) > tol:
            errs.append(
                f"docs/registry.md の Holm しきい値表記 ({raw_str}) が実測 ({thr:.6g}) と一致しない"
            )
    m_perm = re.search(r"必要(?:最小)?置換回数\s*:\s*\*\*(\d+)\*\*", md_text)
    if m_perm:
        doc_perm = int(m_perm.group(1))
        if doc_perm != need_perm:
            errs.append(
                f"docs/registry.md の必要置換回数表記 ({doc_perm}) が実測 ({need_perm}) と一致しない"
            )
    return errs


def check_structure(rows: list[dict]) -> list[str]:
    """番号が 1 から連番で、枝 ID が重複せず、日付が単調であることを検査する（枝 #14）。

    登録簿は「枝を追加する」だけで育つ。番号の飛び・重複・ID の使い回しは、
    追記の事故（行の取り違え・マージでの重複）の兆候なので機械で止める。
    """
    errs: list[str] = []
    numbers = [r.get("#", "") for r in rows]
    if not all(re.fullmatch(r"\d+", n) for n in numbers):
        bad = [n for n in numbers if not re.fullmatch(r"\d+", n)]
        return [f"番号が整数でない行がある: {bad[:5]}"]
    nums = [int(n) for n in numbers]
    if nums != list(range(1, len(nums) + 1)):
        expected = list(range(1, len(nums) + 1))
        diff = [(i, a, b) for i, (a, b) in enumerate(zip(nums, expected)) if a != b]
        errs.append(f"番号が 1..{len(nums)} の連番になっていない（最初のずれ: {diff[:3]}）")

    seen: dict[str, int] = {}
    for r in rows:
        branch_id = r.get("枝 ID", "")
        if branch_id in seen:
            errs.append(f"枝 ID {branch_id!r} が重複している（行 {seen[branch_id]} と {r.get('#')}）")
        else:
            seen[branch_id] = int(r["#"])

    dates = [r.get("日付", "") for r in rows]
    if all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in dates):
        if dates != sorted(dates):
            bad = [(nums[i], dates[i], dates[i + 1])
                   for i in range(len(dates) - 1) if dates[i] > dates[i + 1]]
            errs.append(f"日付が昇順でない（後から登録した枝ほど日付が古い）: {bad[:3]}")
    else:
        bad = [r.get("#") for r in rows if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r.get("日付", ""))]
        errs.append(f"日付が YYYY-MM-DD でない行: {bad[:5]}")
    return errs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="登録簿の Holm しきい値と n_perm 要件を検証する")
    ap.add_argument("--registry", type=Path, default=ROOT / "docs/registry.md")
    ap.add_argument("--config", type=Path, default=ROOT / "config/analysis.json")
    ap.add_argument("--update-config", action="store_true",
                    help="n_perm が不足している場合、config/analysis.json を必要回数へ引き上げる")
    args = ap.parse_args(argv)

    md_text = args.registry.read_text(encoding="utf-8")
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    alpha = float(cfg["inference"]["alpha"])
    n_perm = int(cfg["inference"]["n_perm"])

    rows = parse_registry(md_text)
    if not rows:
        print("[NG] docs/registry.md に登録テーブルの行が見つかりません")
        return 1

    hyp_rows = [r for r in rows if is_hypothesis_row(r)]
    n_branches = len(hyp_rows)
    if n_branches < 1:
        print("[NG] 仮説検定の登録枝数が 0 です")
        return 1

    thr, need_perm = compute_holm_requirements(n_branches, alpha)
    errors = check_doc_declarations(md_text, n_branches, thr, need_perm)
    errors += check_structure(rows)

    if n_perm < need_perm:
        if args.update_config:
            cfg["inference"]["n_perm"] = need_perm
            args.config.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"[updated] inference.n_perm を {n_perm} -> {need_perm} に自動引き上げしました")
            n_perm = need_perm
        else:
            errors.append(
                f"config/analysis.json の inference.n_perm ({n_perm}) が必要置換回数 ({need_perm}) 未満です"
            )

    ids = ", ".join(r.get("枝 ID", "?") for r in hyp_rows)
    print(
        f"登録枝（全 {len(rows)} 件 / 仮説検定 {n_branches} 件: {ids}）: "
        f"alpha={alpha}, Holm 第1しきい値={thr:.6g}, 必要置換回数={need_perm}, 設定 n_perm={n_perm}"
    )
    if errors:
        for e in errors:
            print(f"[NG] {e}")
        return 1
    print("[OK] registry 要件・Holm しきい値・置換回数は整合しています")
    return 0


if __name__ == "__main__":
    sys.exit(main())
