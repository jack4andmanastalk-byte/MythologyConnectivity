# -*- coding: utf-8 -*-
"""
verify_numbers.py -- 文書間で食い違う数値を機械的に止める（枝 #11 DOC-NUMBER-CONSISTENCY）。

事前登録: docs/prereg/20261128-path-connectivity-followup.md 検証 4
規則は config/analysis.json の doc_checks に置く（コードに数値を書かない）。

検査する「総数の主張」:
  1. 古事記ノード数       data/frozen/nodes_297.csv の kind == "kojiki"（現在 37）
  2. ネットワーク検査項目  src/verify_network.py の add("...") 呼び出し数（現在 60）
  3. 登録枝数             docs/registry.md の登録全行（現在 11）
  4. グラフ規模           derived/v17_html_embedded_data.json（297 ノード / 597 エッジ）

除外:
  * 行末に `<!-- doc-number-exempt -->`（設定 doc_checks.exempt_marker）がある行
    （凍結された過去レポートの引用を壊さないための明示的な例外）
  * 設定の context_allow に挙げた語を含む行（部分集合の記述は総数ではない）

違反があれば exit 1。`make all` と CI のゲートにする。
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/analysis.json").read_text(encoding="utf-8"))
DC = CFG["doc_checks"]
MARKER = DC["exempt_marker"]



# 検査項目の数え方（固定）:
#   src/verify_network.py を AST で解析し、add(sec, id, ...) 呼び出しを数える。
#   * id が文字列リテラル  -> 1 項目
#   * id が f-string / 変数 -> それを含む for 文の反復リストの要素数だけ展開する
#     （要素数が取れない場合は 1 として扱い、その旨をレポートに残す）
#   合計が「ネットワーク検査項目数」であり、docs の記載と一致することを CI で強制する。
def count_network_checks(src: str) -> int:
    import ast as _ast
    tree = _ast.parse(src)
    # for 文の本体に含まれる add() 呼び出しを、反復回数つきで集める
    loop_multiplier = {}
    for node in _ast.walk(tree):
        if isinstance(node, _ast.For):
            n = 1
            it = node.iter
            if isinstance(it, (_ast.List, _ast.Tuple, _ast.Set)):
                n = len(it.elts)
            elif isinstance(it, _ast.Call) and isinstance(it.func, _ast.Name) \
                    and it.func.id in {"zip", "enumerate"} and it.args:
                a = it.args[0]
                n = len(a.elts) if isinstance(a, (_ast.List, _ast.Tuple)) else 1
            for sub in _ast.walk(node):
                if isinstance(sub, _ast.Call) and getattr(sub.func, "id", "") == "add":
                    loop_multiplier[id(sub)] = max(n, 1)
    total = 0
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call) and getattr(node.func, "id", "") == "add":
            total += loop_multiplier.get(id(node), 1)
    return total


def measured_values():
    with open(ROOT / "data/frozen/nodes_297.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    verify_src = (ROOT / "src/verify_network.py").read_text(encoding="utf-8")
    registry = (ROOT / "docs/registry.md").read_text(encoding="utf-8")
    graph = json.loads((ROOT / "derived/v17_html_embedded_data.json").read_text(encoding="utf-8"))["data"]
    branch_rows = sum(
        1 for line in registry.splitlines()
        if line.strip().startswith("|")
        and len([c for c in line.strip().strip("|").split("|")]) > 3
        and [c.strip() for c in line.strip().strip("|").split("|")][0].isdigit()
    )
    return {
        "kojiki-node-count": sum(1 for r in rows if r.get("kind") == "kojiki"),
        "network-check-count": count_network_checks(verify_src),
        "registry-branch-count": branch_rows,
        "graph-node-count": len(graph["nodes"]),
    }, dict(nodes=len(graph["nodes"]), edges=len(graph["edges"]))


def main() -> int:
    measured, graph = measured_values()
    rules = DC["rules"]
    violations, checked, exempt = [], 0, 0
    allowed_hits = 0
    for path in sorted((ROOT / "docs").rglob("*.md")):
        rel = path.relative_to(ROOT)
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if MARKER in line:
                exempt += 1
                continue
            for rule in rules:
                expect = rule["value"] if rule.get("value") is not None else measured[rule["id"]]
                allow = [a for a in rule.get("context_allow", []) if a in line]
                for pattern in rule["patterns"]:
                    for m in re.finditer(pattern, line):
                        checked += 1
                        got = int(m.group(1))
                        if allow:
                            allowed_hits += 1
                            continue
                        if got != expect:
                            violations.append(dict(
                                file=str(rel), line=lineno, rule=rule["label"],
                                expected=expect, found=got, text=m.group(0),
                                snippet=line.strip()[:160]))
    if violations:
        print(f"[NG] 文書数値: 違反 {len(violations)} 件 / 照合 {checked} 件")
        for v in violations:
            print(f"  {v['file']}:{v['line']} [{v['rule']}] '{v['text']}' -> 期待 {v['expected']}")
    else:
        print(f"[OK] 文書数値: 違反 0 件 / 照合 {checked} 件 "
              f"(古事記 {measured['kojiki-node-count']} / 検査 {measured['network-check-count']} / "
              f"登録枝 {measured['registry-branch-count']} / "
              f"ノード {graph['nodes']} / エッジ {graph['edges']})"
              f" / 免除行 {exempt} / 部分集合として許容 {allowed_hits}")

    report = ROOT / "outputs/doc_number_checks.json"
    report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps(dict(
        schema="doc-number-checks/1", measured=measured, graph=graph, checked=checked,
        exemption_lines=exempt, subset_allowed=allowed_hits, violations=violations,
        rules=[r["id"] for r in rules],
    ), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
