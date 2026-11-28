# -*- coding: utf-8 -*-
"""
edge_reproduction.py -- 表示エッジ 597 本の「再現可能性」を全件分類する（枝 #8 NET-EDGE-REPRO）。

事前登録: docs/prereg/20261128-path-connectivity-followup.md 検証 1
入力:
  * derived/v17_html_embedded_data.json        画面に埋め込まれたグラフ（凍結原本の抽出物）
  * data/frozen/l1_75d_legacy_matrix.csv       凍結 L1 行列（281 x 75、非零 1,500 セル）
  * data/frozen/nodes_297.csv                  ノード属性（kind で古事記を判定）
  * config/analysis.json                       path_connectivity / network.tolerances

分類（上から順に評価し、最初に一致したクラスを採る）:
  l1_cosine          両端が L1 行列にあり |weight - 生コサイン| <= 許容差（主系 weight_rounding）
  l1_mismatch        両端が L1 行列にあるが上記を満たさない
  l2_construction_rule  source が設定の l2_source_prefix（LP）で始まる
  unverifiable       それ以外

出力:
  outputs/edge_reproduction.csv   597 行
  outputs/edge_reproduction.json  クラス別・層/対象別の集計と許容差

方針: このスクリプトは判定をしない（整合性検査）。再現しない辺は「未検証」であって
「誤り」ではない。数値はすべて設定から読む（数値リテラルを書かない）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import analysis_io as IO  # noqa: E402  出力先の解決・原子的書き込み

import numpy as np   # noqa: E402
import pandas as pd  # noqa: E402

CFG = json.loads((ROOT / "config/analysis.json").read_text(encoding="utf-8"))
PC = CFG["path_connectivity"]
TOL = CFG["network"]["tolerances"]
PRIMARY_TOL = float(TOL[PC["primary_tolerance_key"]])
SENS_TOL = float(PC["sensitivity_tolerance"])
L2_PREFIX = PC["l2_source_prefix"]
OUT = IO.output_dir()
EMBEDDED = ROOT / "derived/v17_html_embedded_data.json"
L1_MATRIX = ROOT / "data/frozen/l1_75d_legacy_matrix.csv"
NODES = ROOT / "data/frozen/nodes_297.csv"

CLASSES = ["l1_cosine", "l1_mismatch", "l2_construction_rule", "unverifiable"]


def load_inputs():
    data = json.loads(EMBEDDED.read_text(encoding="utf-8"))["data"]
    nodes = pd.read_csv(NODES)
    l1 = pd.read_csv(L1_MATRIX, index_col=0)
    return data, nodes, l1


def cosine_table(V: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(V, axis=1, keepdims=True)
    Vn = np.divide(V, np.maximum(n, 1e-12))
    return Vn @ Vn.T


def classify(edges, node_meta, l1_index, cos, pos):
    """1 エッジごとにクラス・重み差・層ラベル候補を返す。"""
    rows = []
    k_ids = {i for i, k in node_meta.items() if k == "kojiki"}
    for e in edges:
        s, t = e["source"], e["target"]
        both = (s in pos) and (t in pos)
        diff = None
        if both:
            diff = abs(float(cos[pos[s], pos[t]]) - float(e["weight"]))
        if both and diff <= PRIMARY_TOL:
            klass = "l1_cosine"
        elif both:
            klass = "l1_mismatch"
        elif str(s).startswith(L2_PREFIX):
            klass = "l2_construction_rule"
        else:
            klass = "unverifiable"
        rows.append(dict(
            source=s, target=t, weight=float(e["weight"]), cosine=(
                round(float(cos[pos[s], pos[t]]), 6) if both else ""),
            weight_minus_cosine=(round(float(e["weight"]) - float(cos[pos[s], pos[t]]), 6) if both else ""),
            primary_abs_diff=(round(diff, 6) if diff is not None else ""),
            tolerance_primary=PRIMARY_TOL,
            within_primary=(bool(diff is not None and diff <= PRIMARY_TOL)),
            within_sensitivity=(bool(diff is not None and diff <= SENS_TOL)),
            classification=klass,
            dt=int(e["dt"]), dist_km=float(e["dist_km"]), type=e["type"],
            source_region=node_meta.get(s, ""), target_region=node_meta.get(t, ""),
            source_is_l2=(str(s).startswith(L2_PREFIX)),
            target_is_kojiki=(t in k_ids), source_is_kojiki=(s in k_ids),
            shared_count=len([x for x in str(e.get("shared", "")).split(",") if x.strip()]),
        ))
    return rows


def rank_within_target(rows):
    """剥離ステップ番号は埋め込みデータに無いため、ターゲットごとの重み降順を代理指標にする。"""
    by_target = {}
    for r in rows:
        by_target.setdefault(r["target"], []).append(r)
    for group in by_target.values():
        group.sort(key=lambda r: -r["weight"])
        for i, r in enumerate(group, start=1):
            r["weight_rank_within_target"] = i
    return rows


def summarize(rows):
    total = len(rows)
    by_class = {c: sum(1 for r in rows if r["classification"] == c) for c in CLASSES}
    koj_in = [r for r in rows if r["target_is_kojiki"]]
    koj_out = [r for r in rows if r["source_is_kojiki"]]

    def block(group):
        comparable = [r for r in group if r["primary_abs_diff"] != ""]
        return dict(
            edges=len(group),
            comparable=len(comparable),
            l1_cosine=sum(1 for r in group if r["classification"] == "l1_cosine"),
            l1_mismatch=sum(1 for r in group if r["classification"] == "l1_mismatch"),
            l2_construction_rule=sum(1 for r in group if r["classification"] == "l2_construction_rule"),
            unverifiable=sum(1 for r in group if r["classification"] == "unverifiable"),
            reproducible_ratio=(round(sum(1 for r in group if r["classification"] in
                                          ("l1_cosine", "l2_construction_rule")) / len(group), 4)
                                if group else None),
            within_primary=sum(1 for r in group if r["within_primary"]),
            within_sensitivity=sum(1 for r in group if r["within_sensitivity"]),
            max_abs_diff=(round(max((r["primary_abs_diff"] for r in comparable), default=0.0), 6)),
        )

    rank_block = {}
    for k in sorted({r["weight_rank_within_target"] for r in rows}):
        grp = [r for r in rows if r["weight_rank_within_target"] == k]
        comparable = [r for r in grp if r["primary_abs_diff"] != ""]
        rank_block[str(k)] = dict(
            edges=len(grp),
            mismatch_over_sensitivity=sum(1 for r in comparable if r["primary_abs_diff"] > SENS_TOL),
            mismatch_ratio=(round(sum(1 for r in comparable if r["primary_abs_diff"] > SENS_TOL)
                                  / len(comparable), 4) if comparable else None),
        )

    return dict(
        schema="edge-reproduction/1",
        preregistration=PC["preregistration"],
        inputs={str(p.relative_to(ROOT)): str(p) for p in (EMBEDDED, L1_MATRIX, NODES)},
        total_edges=total,
        classes=by_class,
        class_ratio={k: (round(v / total, 4) if total else None) for k, v in by_class.items()},
        tolerances=dict(primary=PRIMARY_TOL, sensitivity=SENS_TOL),
        # 全 597 行の内訳（1 行 1 エッジ）。CSV は outputs/edge_reproduction.csv
        all_edges=block(rows),
        edge_rows=[dict(source=r["source"], target=r["target"], weight=r["weight"],
                        classification=r["classification"],
                        primary_abs_diff=r["primary_abs_diff"],
                        target_is_kojiki=r["target_is_kojiki"],
                        source_is_kojiki=r["source_is_kojiki"],
                        weight_rank_within_target=r["weight_rank_within_target"])
                   for r in rows],
        kojiki_inflow=block(koj_in),
        kojiki_outflow=block(koj_out),
        by_weight_rank=rank_block,
        note=("reproducible = l1_cosine + l2_construction_rule。"
              "l1_mismatch は剥離の 2 段目以降・変換重み・L2 合成の寄与を含むため、"
              "生コサイン一致を期待できない設計である（docs/v18_method_and_results.md §7）。"),
    )


def main() -> int:
    data, nodes, l1 = load_inputs()
    node_meta = dict(zip(nodes["id"], nodes["kind"]))
    region_meta = dict(zip(nodes["id"], nodes["region"]))
    edges = data["edges"]
    V = l1.values.astype(float)
    cos = cosine_table(V)
    pos = {k: i for i, k in enumerate(l1.index)}

    rows = classify(edges, node_meta, l1.index, cos, pos)
    for r in rows:
        r["source_region"] = region_meta.get(r["source"], r["source_region"])
        r["target_region"] = region_meta.get(r["target"], r["target_region"])
    rows = rank_within_target(rows)
    summary = summarize(rows)

    OUT.mkdir(exist_ok=True)
    csv_name, json_name = PC["outputs"][0], PC["outputs"][1]
    IO.write_dataframe_atomic(pd.DataFrame(rows), OUT / csv_name, index=False)
    IO.write_json_atomic(OUT / json_name, summary)

    c = summary["classes"]
    print(f"エッジ再現性: 全 {summary['total_edges']} 本 / "
          f"l1_cosine {c['l1_cosine']} / l1_mismatch {c['l1_mismatch']} / "
          f"l2_rule {c['l2_construction_rule']} / unverifiable {c['unverifiable']}")
    ki = summary["kojiki_inflow"]
    print(f"  古事記流入 {ki['edges']} 本: 再現可 {ki['l1_cosine'] + ki['l2_construction_rule']} "
          f"({ki['reproducible_ratio']:.0%}) / 不一致 {ki['l1_mismatch']} / 未検証 {ki['unverifiable']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
