# -*- coding: utf-8 -*-
"""
display_reproducibility.py -- 表示被説明率の「画面のエッジから再計算できるか」を全 297 ノードで列にする。

事前登録: docs/prereg/20261128-path-connectivity-followup.md 検証 3（枝 #10 NET-DISPLAY-REPRO）
入力: derived/html_embedded_v17_audit.json（ADR 0003 の出所台帳）、data/frozen/nodes_297.csv
出力: derived/display_reproducibility.json（追跡対象）、outputs/display_reproducibility.csv（生成物）

凍結 HTML は改変しない（ADR 0003 の不変条件）。ここで作るのは「表示値の出所と再計算可否」の
機械可読な列であり、既存の検査 F10 と同じ gap 数を独立に数え直して照合する。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CFG = json.loads((ROOT / "config/analysis.json").read_text(encoding="utf-8"))
DP = CFG["display_policy"]
AUDIT = ROOT / DP["derived_audit_path"]
NODES = ROOT / "data/frozen/nodes_297.csv"
JSON_OUT = ROOT / DP["reproducibility_json"]
CSV_OUT = ROOT / DP["reproducibility_csv"]
THRESHOLD = float(DP["gap_threshold"])

PROVENANCE_LABEL = {
    "v16.L1": "v16 単層の剥離値（画面の L1 エッジから再計算可能）",
    "decomp.total_final": "3 層分解（L1+L2ext+L2dom）の合成値（画面のエッジからは導けない）",
    "pureL2_dom": "純第 2 層（15D）の剥離値（画面の L1 エッジからは導けない）",
}


def main() -> int:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    import pandas as pd
    nodes = pd.read_csv(NODES)
    kind = dict(zip(nodes["id"], nodes["kind"]))
    region = dict(zip(nodes["id"], nodes["region"]))

    rows = []
    for n in audit["nodes_provenance"]:
        replay = n.get("explained_replay_l1")
        display = float(n["explained_display"])
        gap = (None if replay is None else round(display - float(replay), 6))
        rows.append(dict(
            id=n["id"], kind=kind.get(n["id"], ""), region=region.get(n["id"], ""),
            provenance=n["provenance"],
            provenance_label=PROVENANCE_LABEL.get(n["provenance"], ""),
            explained_display=display,
            explained_replay_l1=("" if replay is None else float(replay)),
            gap=("" if gap is None else gap),
            replayable=bool(replay is not None),
            exceeds_threshold=bool(gap is not None and abs(gap) > THRESHOLD),
        ))
    df = pd.DataFrame(rows)

    def agg(sub):
        return dict(
            nodes=len(sub),
            replayable=int(sub["replayable"].sum()),
            not_replayable=int((~sub["replayable"]).sum()),
            over_threshold=int(sub["exceeds_threshold"].sum()),
            provenance_counts={k: int(v) for k, v in sub["provenance"].value_counts().items()},
        )

    outp = dict(
        schema="display-reproducibility/1",
        source_ledger=str(AUDIT.relative_to(ROOT)),
        policy=audit.get("policy", ""),
        gap_threshold=THRESHOLD,
        total_nodes=len(df),
        overall=agg(df),
        by_kind={k: agg(g) for k, g in df.groupby("kind")},
        by_provenance={k: agg(g) for k, g in df.groupby("provenance")},
        kojiki_gap_ids=sorted(df[(df.kind == "kojiki") & df.exceeds_threshold]["id"].tolist()),
        cross_check=dict(
            expected_gap_nodes=int(DP["expected_gap_nodes"]),
            expected_evaluable_nodes=int(DP["expected_evaluable_nodes"]),
            gap_matches_expected=bool(int(df["exceeds_threshold"].sum()) == int(DP["expected_gap_nodes"])),
            evaluable_matches_expected=bool(int(df["replayable"].sum()) == int(DP["expected_evaluable_nodes"])),
        ),
        note=("replayable=False は『画面の L1 エッジから被説明率を再計算できない』ことのみを意味し、"
              "値の誤りではない。表示は 3 系統の混成（ADR 0003）。"),
    )

    JSON_OUT.write_text(json.dumps(outp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    CSV_OUT.parent.mkdir(exist_ok=True)
    df.to_csv(CSV_OUT, index=False)

    o = outp["overall"]
    print(f"表示再計算可否: {o['nodes']} ノード / 再計算可 {o['replayable']} / 不可 {o['not_replayable']} / "
          f"0.01 超の乖離 {o['over_threshold']}")
    print(f"  照合: gap {outp['cross_check']['gap_matches_expected']} / "
          f"evaluable {outp['cross_check']['evaluable_matches_expected']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
