# -*- coding: utf-8 -*-
"""
build_interactive_html.py -- v17 インタラクティブ HTML（原本デザイン）に
リポジトリの最新データを統合してグラフネットワーク確認用 HTML を再生成する。

モード:
  --extract <path>  v17 原本 HTML から埋め込み DATA を抽出し
                    derived/v17_html_embedded_data.json に保存（出所 SHA-256 を記録）
  （既定）          derived/v17_html_embedded_data.json（原本グラフ 297 ノード / 597 エッジ）に
                    以下を統合して docs/interactive/graph_network_atlas.html を生成:
                      * data/frozen/nodes_297.csv        ノード種別（eurasia/kojiki/anchor）
                      * derived/html_embedded_v17_audit.json  表示出所・乖離台帳（ADR 0003）
                      * annotations/*.jsonl              第 2 層 R01-R15 評定・L1 再評定（証拠つき）

デザインは v17 原本（src/interactive_atlas.template.html.tmpl）をそのまま使い、
追加は「v18 追記」カード（表示監査・評定）とツールチップ注記に限る。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "derived/html_embedded_v17_audit.json"
NODES_PATH = ROOT / "data/frozen/nodes_297.csv"
EMBEDDED_PATH = ROOT / "derived/v17_html_embedded_data.json"
WORLD_LAND_PATH = ROOT / "derived/world_land.json"
TRADE_ROUTES_PATH = ROOT / "data/trade_routes.json"
TEMPLATE_PATH = ROOT / "src/interactive_atlas.template.html.tmpl"
OUT_PATH = ROOT / "docs/interactive/graph_network_atlas.html"
ANNOTATION_DIR = ROOT / "annotations"

ZERO = 0.0


def r4(x):
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v:
        return None
    return round(v, 4)


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


def extract_mode(src_path: Path) -> int:
    """v17 原本 HTML から埋め込み DATA を抽出して derived/ に保存する。"""
    text = src_path.read_text(encoding="utf-8", errors="replace")
    marker = "const DATA = "
    idx = text.index(marker) + len(marker)
    data, _ = json.JSONDecoder().raw_decode(text[idx:])
    digest = hashlib.sha256(src_path.read_bytes()).hexdigest()
    out = {
        "__source": {
            "file": src_path.name,
            "sha256": digest,
            "note": "v17 原本 HTML（ZIP_INFO.txt 検証必須 15 件の目録ハッシュと照合済みであること）",
        },
        "data": data,
    }
    EMBEDDED_PATH.parent.mkdir(parents=True, exist_ok=True)
    EMBEDDED_PATH.write_text(
        json.dumps(out, ensure_ascii=False, sort_keys=True, indent=1) + "\n",
        encoding="utf-8")
    print(f"wrote {EMBEDDED_PATH.relative_to(ROOT)}")
    print(f"  source={src_path.name} sha256={digest}")
    print(f"  nodes={len(data['nodes'])} edges={len(data['edges'])} lanes={len(data['lanes'])}")
    return 0


def build_mode() -> int:
    embedded = json.loads(EMBEDDED_PATH.read_text(encoding="utf-8"))
    payload = embedded["data"]

    kind_by_id = {}
    with open(NODES_PATH, encoding="utf-8") as stream:
        import csv
        for row in csv.DictReader(stream):
            kind_by_id[row["id"]] = row["kind"]

    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    prov_by_id = {p["id"]: p for p in audit["nodes_provenance"]}
    gap_by_id = {g["id"]: g for g in audit["gap_nodes"]}
    l2_ann, l1_ann = collect_annotations()

    for node in payload["nodes"]:
        nid = node["id"]
        prov = prov_by_id.get(nid, {})
        gap = gap_by_id.get(nid)
        node["kind"] = kind_by_id.get(nid, "")
        node["provenance"] = prov.get("provenance", "")
        node["exp_replay"] = r4(prov.get("explained_replay_l1"))
        node["gap"] = None if gap is None else {
            "displayed_pct": r4(gap.get("displayed_pct")),
            "replay_l1_from_edges": r4(gap.get("replay_l1_from_edges")),
            "gap_l1": r4(gap.get("gap_l1")),
            "v16_l1_pct": r4(gap.get("v16_l1_pct")),
            "decomp_l1_only_pct": r4(gap.get("decomp_l1_only_pct")),
            "decomp_l2_ext_gain_pct": r4(gap.get("decomp_l2_ext_gain_pct")),
            "decomp_l2_dom_gain_pct": r4(gap.get("decomp_l2_dom_gain_pct")),
            "decomp_total_final_pct": r4(gap.get("decomp_total_final_pct")),
            "display_note": gap.get("display_note", ""),
        }
        node["l2"] = l2_ann.get(nid, [])
        node["l1audit"] = l1_ann.get(nid, [])

    gap_count = sum(1 for n in payload["nodes"] if n.get("gap"))
    world_land = None
    if WORLD_LAND_PATH.exists():
        world_land = json.loads(WORLD_LAND_PATH.read_text(encoding="utf-8"))
    payload["world_land"] = world_land
    trade_routes = None
    if TRADE_ROUTES_PATH.exists():
        trade_routes = json.loads(TRADE_ROUTES_PATH.read_text(encoding="utf-8"))
    payload["trade_routes"] = trade_routes
    payload["v18meta"] = {
        "source_html_sha256": embedded.get("__source", {}).get("sha256", ""),
        "generator": "src/build_interactive_html.py",
        "template": "src/interactive_atlas.template.html.tmpl",
        "display_policy": json.loads(AUDIT_PATH.read_text(encoding="utf-8")).get("policy", ""),
        "counts": {
            "nodes": len(payload["nodes"]),
            "edges": len(payload["edges"]),
            "lanes": len(payload["lanes"]),
            "gap_nodes": gap_count,
            "l2_annotation_records": sum(len(v) for v in l2_ann.values()),
            "l1_audit_records": sum(len(v) for v in l1_ann.values()),
        },
        "sources": [
            "derived/v17_html_embedded_data.json（v17 原本グラフ: 297 ノード / 597 エッジ）",
            "data/frozen/nodes_297.csv（ノード種別）",
            "derived/html_embedded_v17_audit.json（表示出所・乖離台帳 / ADR 0003）",
            "annotations/*.jsonl（第 2 層 R01-R15 評定・L1 再評定、証拠つき）",
            "derived/world_land.json（Natural Earth 1:110m 陸域・国境 / パブリックドメイン）",
            "data/trade_routes.json（交易史・考古学遺物に基づく中継交易ルート / 表示専用の近似）",
        ],
        "notes": [
            "表示値（explained_pct 等）は v17 原本どおり。ADR 0003 に従い改変せず、乖離は注記で示す。",
            "純 L2 接続辺を含む原本 597 エッジをそのまま表示する。",
        ],
    }

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    data_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    data_json = data_json.replace("</", "<\\/")
    html_text = template.replace("__DATA_JSON__", data_json)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html_text, encoding="utf-8")

    print(f"wrote {OUT_PATH.relative_to(ROOT)}")
    print(f"  nodes={payload['v18meta']['counts']['nodes']} edges={payload['v18meta']['counts']['edges']}")
    print(f"  gap_nodes={gap_count} l2_records={payload['v18meta']['counts']['l2_annotation_records']} "
          f"l1audit_records={payload['v18meta']['counts']['l1_audit_records']}")
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--extract":
        if len(sys.argv) < 3:
            print("usage: build_interactive_html.py --extract <path-to-v17-html>", file=sys.stderr)
            return 2
        return extract_mode(Path(sys.argv[2]))
    return build_mode()


if __name__ == "__main__":
    raise SystemExit(main())
