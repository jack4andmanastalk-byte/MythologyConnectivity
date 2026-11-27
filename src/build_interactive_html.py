# -*- coding: utf-8 -*-
"""
build_interactive_html.py -- リポジトリの凍結データからグラフネットワーク確認用
インタラクティブ HTML を決定論的に再生成する。

入力（すべて Git 追跡済みの最新データ）:
  * data/frozen/nodes_297.csv               297 ノードのメタデータ
  * data/frozen/l1_75d_legacy_matrix.csv    第 1 層 75 次元・凍結 legacy 行列
  * data/frozen/v16_eurasia_281nodes_75d.csv 凍結 v16 ノード統計
  * derived/html_embedded_v17_audit.json    凍結 HTML 表示値の出所・乖離台帳（ADR 0003）
  * annotations/*.jsonl                     第 2 層 R01-R15 評定・L1 再評定（証拠つき）
  * config/analysis.json                    エンジン設定（唯一の定数源）

出力:
  * docs/interactive/graph_network_atlas.html   自己完結のインタラクティブ HTML

エッジは v18 エンジン（src/engine.py）で凍結行列から再構築する。
  * primary 層   : config/analysis.json engine.primary（校正済み類似度）
  * reference 層 : config/analysis.json engine.reference_v17_compatible（v17 互換コサイン）
v17 埋め込みグラフの純 L2 接続辺はリポジトリに追跡されていないため再構築しない。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import engine as E  # noqa: E402

CFG_PATH = ROOT / "config/analysis.json"
AUDIT_PATH = ROOT / "derived/html_embedded_v17_audit.json"
NODES_PATH = ROOT / "data/frozen/nodes_297.csv"
MATRIX_PATH = ROOT / "data/frozen/l1_75d_legacy_matrix.csv"
V16_PATH = ROOT / "data/frozen/v16_eurasia_281nodes_75d.csv"
TEMPLATE_PATH = ROOT / "src/interactive_atlas.template.html.tmpl"
OUT_PATH = ROOT / "docs/interactive/graph_network_atlas.html"
ANNOTATION_DIR = ROOT / "annotations"
ROUND_NDIGITS = 4
ZERO = 0.0


def r4(x):
    """表示用に既定桁で丸める（欠損は None）。"""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    return round(v, ROUND_NDIGITS)


def load_jsonl(path: Path):
    recs = []
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def collect_annotations():
    """annotations/ からターゲットごとの評定レコード（L2 / L1 再評定）を集める。"""
    l2 = {}
    l1 = {}
    for path in sorted(ANNOTATION_DIR.glob("*.jsonl")):
        for rec in load_jsonl(path):
            entry = {
                "file": path.name,
                "grid": rec.get("grid", ""),
                "annotator": rec.get("annotator", ""),
                "pass": rec.get("pass", ""),
                "coded_at": rec.get("coded_at", ""),
                "blinded_to": rec.get("blinded_to", []),
                "levels": rec.get("levels", {}),
                "evidence": rec.get("evidence", {}),
                "notes": rec.get("notes", ""),
            }
            target = rec.get("target", "")
            bucket = l1 if entry["grid"].startswith("L1") else l2
            bucket.setdefault(target, []).append(entry)
    for bucket in (l2, l1):
        for key in bucket:
            bucket[key].sort(key=lambda e: (e["pass"], e["file"]))
    return l2, l1


def run_layer(nodes_df: pd.DataFrame, V: np.ndarray, cfg_dict: dict):
    """engine.peel を 1 層実行し、エッジ台帳とノード統計を返す。"""
    cfg = E.EngineConfig(**cfg_dict)
    edges_df, explained, parents, top = E.peel(nodes_df, V, cfg)
    ids = nodes_df["id"].tolist()
    edges = []
    for row in edges_df.itertuples(index=False):
        edges.append({
            "s": row.source,
            "t": row.target,
            "dt": int(row.dt_years),
            "km": r4(row.dist_km),
            "z": r4(row.similarity),
            "cos": r4(row.cosine),
            "step": int(row.step),
        })
    stats = {}
    for i, nid in enumerate(ids):
        stats[nid] = {
            "explained": r4(explained[i]),
            "top_z": r4(top[i]),
            "n_parents": len(parents[i]),
        }
    return edges, stats


def main() -> int:
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    nodes_df = pd.read_csv(NODES_PATH)
    matrix_df = pd.read_csv(MATRIX_PATH)
    v16_df = pd.read_csv(V16_PATH).set_index("id")

    ids_matrix = matrix_df["id"].tolist()
    feats = [c for c in matrix_df.columns if c != "id"]
    V = matrix_df[feats].to_numpy(float)

    l1_nodes_df = nodes_df[nodes_df["id"].isin(set(ids_matrix))].copy()
    l1_nodes_df = l1_nodes_df.set_index("id").loc[ids_matrix].reset_index()

    primary_edges, primary_stats = run_layer(
        l1_nodes_df, V, cfg["engine"]["primary"])
    reference_edges, reference_stats = run_layer(
        l1_nodes_df, V, cfg["engine"]["reference_v17_compatible"])

    l2_ann, l1_ann = collect_annotations()
    prov_by_id = {p["id"]: p for p in audit["nodes_provenance"]}
    gap_by_id = {g["id"]: g for g in audit["gap_nodes"]}

    nodes_payload = []
    for row in nodes_df.itertuples(index=False):
        nid = row.id
        prov = prov_by_id.get(nid, {})
        gap = gap_by_id.get(nid)
        v16 = None
        motifs = []
        if nid in v16_df.index:
            v = v16_df.loc[nid]
            v16 = {
                "explained_frac": r4(v["explained_frac"]),
                "best_p": r4(v["best_p"]),
                "best_z": r4(v["best_z"]),
                "in_deg": r4(v["in_deg"]),
                "out_deg": r4(v["out_deg"]),
                "cat_tag": v["cat_tag"],
                "is_extra": bool(v["is_extra"]),
                "inherited_motifs": v["inherited_motifs"] if isinstance(v["inherited_motifs"], str) else "",
                "residual_motifs": v["residual_motifs"] if isinstance(v["residual_motifs"], str) else "",
            }
        mrow = matrix_df[matrix_df["id"] == nid]
        if len(mrow):
            rec = mrow.iloc[0]
            for f in feats:
                val = float(rec[f])
                if val > ZERO:
                    motifs.append([f, r4(val)])
        nodes_payload.append({
            "id": nid,
            "kind": row.kind,
            "region": row.region,
            "name": row.name,
            "lat": r4(row.lat),
            "lon": r4(row.lon),
            "t_eff": int(row.t_eff),
            "provenance": prov.get("provenance", ""),
            "exp_display": r4(prov.get("explained_display")),
            "exp_replay": r4(prov.get("explained_replay_l1")),
            "gap": None if gap is None else {
                "displayed_pct": r4(gap.get("displayed_pct")),
                "replay_l1_from_edges": r4(gap.get("replay_l1_from_edges")),
                "gap_l1": r4(gap.get("gap_l1")),
                "v16_l1_pct": r4(gap.get("v16_l1_pct")),
                "decomp_l1_only_pct": r4(gap.get("decomp_l1_only_pct")),
                "decomp_l2_ext_gain_pct": r4(gap.get("decomp_l2_ext_gain_pct")),
                "decomp_l2_dom_gain_pct": r4(gap.get("decomp_l2_dom_gain_pct")),
                "decomp_total_final_pct": r4(gap.get("decomp_total_final_pct")),
                "display_note": gap.get("display_note", ""),
            },
            "v16": v16,
            "motifs": motifs,
            "l2": l2_ann.get(nid, []),
            "l1audit": l1_ann.get(nid, []),
            "primary": primary_stats.get(nid),
            "reference": reference_stats.get(nid),
        })

    regions = []
    for reg in nodes_df["region"].tolist():
        if reg not in regions:
            regions.append(reg)
    kojiki_regions = set(nodes_df[nodes_df["kind"] == "kojiki"]["region"].tolist())
    med_t = {}
    for reg in regions:
        vals = sorted(float(t) for t in nodes_df[nodes_df["region"] == reg]["t_eff"].tolist())
        med_t[reg] = vals[len(vals) // 2]
    regions.sort(key=lambda reg: (reg in kojiki_regions, med_t[reg], reg))

    def layer_summary(edges, stats):
        targets = {e["t"] for e in edges}
        sources = {e["s"] for e in edges}
        deg = {}
        for e in edges:
            deg[e["t"]] = deg.get(e["t"], 0) + 1
        mismatch = 0
        if stats:
            for nid, st in stats.items():
                if nid in v16_df.index:
                    want = float(v16_df.loc[nid, "in_deg"])
                    if abs(want - float(deg.get(nid, 0))) > ZERO:
                        mismatch += 1
        weights = [e["z"] for e in edges] or [0.0]
        return {
            "edges": len(edges),
            "targets": len(targets),
            "sources": len(sources),
            "isolates": len([n for n in nodes_payload
                             if n["id"] in stats and n["id"] not in deg
                             and n["id"] not in sources]),
            "weight_min": r4(min(weights)),
            "weight_max": r4(max(weights)),
            "in_deg_mismatch_vs_v16": mismatch,
        }

    l1_cols = feats
    payload = {
        "meta": {
            "generator": "src/build_interactive_html.py",
            "template": "src/interactive_atlas.template.html.tmpl",
            "config_version": cfg.get("version", ""),
            "display_policy": cfg.get("display_policy", {}),
            "engine": cfg["engine"],
            "expected_embedded": cfg["network"]["expected"],
            "sources": [
                {"path": "data/frozen/nodes_297.csv", "role": "297 ノードのメタデータ"},
                {"path": "data/frozen/l1_75d_legacy_matrix.csv", "role": "第 1 層 75 次元・凍結 legacy 行列"},
                {"path": "data/frozen/v16_eurasia_281nodes_75d.csv", "role": "凍結 v16 ノード統計"},
                {"path": "derived/html_embedded_v17_audit.json", "role": "表示値の出所・乖離台帳（ADR 0003）"},
                {"path": "annotations/*.jsonl", "role": "第 2 層 R01-R15 評定・L1 再評定（証拠つき）"},
                {"path": "config/analysis.json", "role": "エンジン設定（唯一の定数源）"},
                {"path": "src/engine.py", "role": "決定論的剥離エンジン（エッジ再構築に使用）"},
            ],
            "region_order": regions,
            "l1_features": l1_cols,
            "counts": {
                "nodes": len(nodes_payload),
                "regions": len(regions),
                "matrix_nodes": len(ids_matrix),
                "motif_dims": len(feats),
                "gap_nodes": len(gap_by_id),
                "gap_expected": cfg.get("display_policy", {}).get("expected_gap_nodes"),
                "frozen_v16_in_deg_sum": int(sum(float(v16_df.loc[n, "in_deg"]) for n in v16_df.index)),
                "l2_annotation_records": sum(len(v) for v in l2_ann.values()),
                "l1_audit_records": sum(len(v) for v in l1_ann.values()),
            },
            "layers": {
                "primary": layer_summary(primary_edges, primary_stats),
                "reference": layer_summary(reference_edges, reference_stats),
            },
        },
        "nodes": nodes_payload,
        "edges": {"primary": primary_edges, "reference": reference_edges},
    }

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    data_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    # <script> 内埋め込みなので終了タグの断片をエスケープする
    data_json = data_json.replace("</", "<\\/")
    html_text = template.replace("__DATA_JSON__", data_json)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html_text, encoding="utf-8")

    print(f"wrote {OUT_PATH.relative_to(ROOT)}")
    print(f"  nodes={len(nodes_payload)} regions={len(regions)}")
    print(f"  edges primary={len(primary_edges)} reference={len(reference_edges)}")
    print(f"  gap_nodes={len(gap_by_id)} l2_records={payload['meta']['counts']['l2_annotation_records']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
