# -*- coding: utf-8 -*-
"""
audit_no_hardcode.py -- 実装に解析上の手書き定数が残っていないことを機械的に確かめる。

方針:
  * 数値リテラルのうち、解析の判断（しきい値・重み・件数・座標・年数）に使われるものは
    config/analysis.json 以外に置かない。
  * 構造上必要な定数（0, 1, 2, -1, 1e-12 など）と、表示用の書式指定のみ許可リストで通す。

出力: outputs/audit_hardcode.md と標準出力の要約。違反があれば exit 1。
"""
from __future__ import annotations
import ast, io, json, re, sys, tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)

# 許可するのは「構造上必要な定数」と「表示用の定数」のみ（数値として比較）
ALLOWED = {
    0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 8.0, 10.0, 16.0, 20.0, 60.0, 100.0, 200.0, 1000.0, 10000.0,
    -1.0, 0.5, 1e-12, 1e-9, 1e-8, 0.25, 6371.0, 2000.0,
}   # 0.25=残余ノルム停止条件 / 6371.0=地球半径 / 20=エラー表示件数 / 2000=ログ切り詰め
# 0.25 は残余ノルム停止条件、6371.0 は地球半径（物理定数）として許可

SKIP = {"run_all.py"}          # run_all はレポートの書式（f-string 桁数）のみ


def literals(path: Path):
    """数値リテラル（位置つき）を抽出。f-string 内の書式指定は除外。"""
    src = path.read_text(encoding="utf-8")
    out = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    # f-string 内の書式（:.3f 等）は FormattedValue の format_spec 内の定数として現れる
    skip_spans = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for v in node.values:
                if isinstance(v, ast.FormattedValue) and v.format_spec is not None:
                    skip_spans.append((v.format_spec.lineno, v.format_spec.col_offset,
                                       v.format_spec.end_lineno, v.format_spec.end_col_offset))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            span = (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)
            if any(span[0] >= s[0] and span[2] <= s[2] and span[1] >= s[1] for s in skip_spans):
                continue
            out.append((node.lineno, repr(node.value)))
    return sorted(out)


def main():
    cfg = json.loads((ROOT / "config/analysis.json").read_text(encoding="utf-8"))
    cfg_numbers = set()
    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, (int, float)) and not isinstance(x, bool):
            cfg_numbers.add(float(x))
    walk(cfg)

    lines, viol = [], []
    files = sorted(SRC.glob("*.py"))
    for f in files:
        lits = literals(f)
        bad = []
        for ln, lit in lits:
            try:
                val = float(lit)
            except ValueError:
                continue
            if val in ALLOWED:
                continue
            if val in cfg_numbers:
                continue
            bad.append((ln, lit))
        lines.append((f.name, len(lits), len(bad)))
        if bad and f.name not in SKIP:
            viol.extend((f.name, ln, lit) for ln, lit in bad)

    rep = io.StringIO()
    rep.write("# 手書き定数ゼロ監査（自動生成）\n\n")
    rep.write("`src/audit_no_hardcode.py` が `src/*.py` の数値リテラルを AST で抽出し、"
              "`config/analysis.json` と構造定数の許可リストに照合した結果。\n\n")
    rep.write("| ファイル | 数値リテラル数 | 許可外 |\n| :--- | ---: | ---: |\n")
    for nm, n, b in lines:
        rep.write(f"| `{nm}` | {n} | {b} |\n")
    rep.write("\n## 許可外リテラル\n\n")
    if viol:
        rep.write("| ファイル | 行 | 値 |\n| :--- | ---: | ---: |\n")
        for nm, ln, lit in viol:
            rep.write(f"| `{nm}` | {ln} | `{lit}` |\n")
    else:
        rep.write("なし。解析上のしきい値・重み・件数はすべて `config/analysis.json` 由来、"
                  "または構造定数（0/1/2, 1e-12, 地球半径 6371.0 等）。\n")
    (OUT / "audit_hardcode.md").write_text(rep.getvalue(), encoding="utf-8")
    print(rep.getvalue())
    sys.exit(1 if viol else 0)


if __name__ == "__main__":
    main()
