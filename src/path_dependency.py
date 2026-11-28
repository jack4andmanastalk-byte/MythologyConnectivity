# -*- coding: utf-8 -*-
"""
path_dependency.py -- 古事記 37 話のパスが「どの 1 ノードの除去で壊れるか」を測る（枝 #9 NET-PATH-DEP）。

事前登録: docs/prereg/20261128-path-connectivity-followup.md 検証 2
入力: derived/v17_html_embedded_data.json、data/frozen/nodes_297.csv、config/analysis.json

手続き:
  1. 基準状態で古事記 37 話の祖先集合を求める。
  2. 古事記の祖先集合に含まれる各ノード u を 1 つずつ除去し、
     (a) 祖先集合が空になるか（接続喪失）
     (b) 祖先数が基準の ancestor_loss_ratio 未満に落ちるか
     (c) 厳格な西ユーラシア祖先（設定 west_regions）を失うか
     を再計算する。
  3. 無向グラフの橋（bridge）と関節点（articulation point）も併記する。

出力: outputs/path_dependency.csv / outputs/path_dependency.json

方針: 除去試験は「辺の妥当性」を問わない構造だけの試験である。したがって結果は
「このノードの辺が正しいか」ではなく「このノードを外すと経路が残るか」を意味する。
`K1-18` は基準状態でも西ユーラシア祖先を持たない既知の例外として明示する。
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import analysis_io as IO  # noqa: E402  出力先の解決・原子的書き込み
CFG = json.loads((ROOT / "config/analysis.json").read_text(encoding="utf-8"))
PC = CFG["path_connectivity"]
WEST = set(PC["west_regions"])
RATIO = float(PC["ancestor_loss_ratio"])
OUT = IO.output_dir()
EMBEDDED = ROOT / "derived/v17_html_embedded_data.json"


def build_graph(data):
    region = {n["id"]: n["region"] for n in data["nodes"]}
    kojiki = [n["id"] for n in data["nodes"] if n["region"] == "古事記（日本）"]
    pred = collections.defaultdict(list)
    undirected = collections.defaultdict(set)
    for e in data["edges"]:
        pred[e["target"]].append(e["source"])
        undirected[e["source"]].add(e["target"])
        undirected[e["target"]].add(e["source"])
    return region, kojiki, pred, undirected


def ancestors(start, pred, removed=None):
    seen = set()
    stack = [p for p in pred[start] if p != removed]
    while stack:
        x = stack.pop()
        if x in seen or x == removed:
            continue
        seen.add(x)
        stack.extend(p for p in pred[x] if p not in seen and p != removed)
    return seen


def west_count(nodes, region):
    return sum(1 for n in nodes if region.get(n) in WEST)


def bridges_and_articulation(undirected):
    """Tarjan の橋・関節点（再帰を使わずに明示スタックで回す）。"""
    disc, low, parent = {}, {}, {}
    bridges, arts = [], set()
    t = 0
    for root in sorted(undirected):
        if root in disc:
            continue
        stack = [(root, iter(sorted(undirected[root])))]
        disc[root] = low[root] = t
        t += 1
        parent[root] = None
        children = collections.Counter()
        while stack:
            u, it = stack[-1]
            advanced = False
            for v in it:
                if v not in disc:
                    parent[v] = u
                    disc[v] = low[v] = t
                    t += 1
                    children[u] += 1
                    stack.append((v, iter(sorted(undirected[v]))))
                    advanced = True
                    break
                if v != parent[u]:
                    low[u] = min(low[u], disc[v])
            if advanced:
                continue
            stack.pop()
            if parent[u] is not None:
                p = parent[u]
                low[p] = min(low[p], low[u])
                if low[u] > disc[p]:
                    bridges.append((p, u))
                if parent[p] is not None and low[u] >= disc[p]:
                    arts.add(p)
        if children[root] > 1:
            arts.add(root)
    return bridges, sorted(arts)


def main() -> int:
    data = json.loads(EMBEDDED.read_text(encoding="utf-8"))["data"]
    region, kojiki, pred, undirected = build_graph(data)

    base = {k: ancestors(k, pred) for k in kojiki}
    base_size = {k: len(base[k]) for k in kojiki}
    base_west = {k: west_count(base[k], region) for k in kojiki}
    candidates = sorted(set().union(*base.values()))

    rows, affected_nodes = [], []
    for u in candidates:
        lost, shrunk, west_lost = [], [], []
        for k in kojiki:
            a = ancestors(k, pred, removed=u)
            if not a:
                lost.append(k)
            elif len(a) < RATIO * base_size[k]:
                shrunk.append(k)
            if base_west[k] > 0 and west_count(a, region) == 0:
                west_lost.append(k)
        rows.append(dict(
            removed=u,
            region=region.get(u, ""),
            in_base_ancestor_union=True,
            n_kojiki_disconnected=len(lost),
            n_kojiki_ancestors_shrunk=len(shrunk),
            n_kojiki_west_ancestor_lost=len(west_lost),
            kojiki_disconnected=";".join(lost),
            kojiki_west_ancestor_lost=";".join(west_lost),
        ))
        if lost or shrunk or west_lost:
            affected_nodes.append(rows[-1])

    bridges, arts = bridges_and_articulation(undirected)
    koj_set = set(kojiki)
    bridge_rows = []
    for a, b in bridges:
        # どちら側に古事記があるか
        def side(x, y):
            seen, stack, out = {x, y}, [y], set()
            while stack:
                n = stack.pop()
                if n in koj_set:
                    out.add(n)
                for m in undirected[n]:
                    if m not in seen:
                        seen.add(m)
                        stack.append(m)
            return out
        s1, s2 = side(a, b), side(b, a)
        bridge_rows.append(dict(source=a, target=b, region_source=region.get(a, ""),
                                region_target=region.get(b, ""),
                                kojiki_downstream=(len(s1) if s1 else len(s2)),
                                kojiki_only_one_side=bool(s1) != bool(s2)))

    result = dict(
        schema="path-dependency/1",
        preregistration=PC["preregistration"],
        west_regions=sorted(WEST),
        ancestor_loss_ratio=RATIO,
        n_kojiki=len(kojiki),
        baseline=dict(
            ancestor_union=len(set().union(*base.values())),
            ancestor_size_median=float(sorted(base_size.values())[len(kojiki) // 2]),
            kojiki_with_west_ancestor=sum(1 for k in kojiki if base_west[k] > 0),
            kojiki_without_west_ancestor=[k for k in kojiki if base_west[k] == 0],
        ),
        ablation=dict(
            candidates=len(candidates),
            single_points_of_failure_disconnect=[r["removed"] for r in affected_nodes
                                                if r["n_kojiki_disconnected"] > 0],
            single_points_of_failure_west=[r["removed"] for r in affected_nodes
                                           if r["n_kojiki_west_ancestor_lost"] > 0],
            n_nodes_with_any_effect=len(affected_nodes),
            max_kojiki_disconnected=max((r["n_kojiki_disconnected"] for r in rows), default=0),
        ),
        bridges=dict(
            count=len(bridges),
            only_one_side_has_kojiki=[f"{r['source']}-{r['target']}" for r in bridge_rows
                                      if r["kojiki_only_one_side"]],
            articulation_points=arts,
        ),
        note=("単一障害点 (single_points_of_failure_*) は『そのノードを除くと経路が壊れる』ことを示す。"
              "辺の妥当性そのものの証拠ではない。"),
    )

    OUT.mkdir(exist_ok=True)
    csv_name, json_name = PC["outputs"][2], PC["outputs"][3]
    import pandas as pd
    ordered = pd.DataFrame(rows).sort_values(
        by=["n_kojiki_disconnected", "n_kojiki_west_ancestor_lost", "n_kojiki_ancestors_shrunk"],
        ascending=False)
    IO.write_dataframe_atomic(ordered, OUT / csv_name, index=False)
    IO.write_dataframe_atomic(pd.DataFrame(bridge_rows), OUT / "path_dependency_bridges.csv",
                              index=False)
    IO.write_json_atomic(OUT / json_name, result)

    a = result["ablation"]
    print(f"中継依存: 候補 {a['candidates']} ノード / 除去で何かが壊れる {a['n_nodes_with_any_effect']} 件")
    print(f"  接続喪失を起こす単一障害点: {len(a['single_points_of_failure_disconnect'])} 件"
          f" {a['single_points_of_failure_disconnect'][:6]}")
    print(f"  西ユーラシア祖先喪失: {len(a['single_points_of_failure_west'])} 件 / "
          f"橋 {result['bridges']['count']} 本 / 片側のみ古事記 {len(result['bridges']['only_one_side_has_kojiki'])} 本")
    print(f"  基準で西祖先なし: {result['baseline']['kojiki_without_west_ancestor']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
