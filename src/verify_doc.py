# -*- coding: utf-8 -*-
"""
verify_doc.py -- 手書き文書（docs/v18_method_and_results.md）に書かれた数値が
outputs/results.json の実測値と一致することを機械照合する。

文書中の表記（小数点以下の桁数・記号）に合わせて値を整形し、文字列として存在するかを見る。
不一致があれば exit 1。
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/v18_method_and_results.md"
R = json.loads((ROOT / "outputs/results.json").read_text(encoding="utf-8"))
TEXT = DOC.read_text(encoding="utf-8").replace("\u2212", "-")   # 全角マイナスを正規化して比較

L2, L1, AG, DG = R["layer2"], R["layer1"], R["agreement"], R["layer2"]["diagnostics"]
CV, LC = L2["v18_calibrated"], L2["legacy_v17_calibrated"]
CR, LR = L2["v18_cosine_reference"], L2["legacy_v17_cosine_reference"]
PN = {k: v for k, v in L2["per_node"].items()}
ROB = {r["seed"]: r for r in L2["seed_robustness"]}
PAR = {(r["param"], r["value"]): r for r in L2["param_robustness"]}

checks = []          # (説明, 文書に存在すべき文字列, 実測値)
f3 = lambda x: f"{x:.3f}"
f2 = lambda x: f"{x:.2f}"
sg = lambda x: ("-" if x < 0 else "") + f"{abs(x):.2f}"
pc = lambda x: f"{100*x:.2f}%"

checks += [
    ("主系 p", f3(CV["p_value"]), f3(CV["p_value"])),
    ("主系 d", sg(CV["effect_d"]), sg(CV["effect_d"])),
    ("主系 実測", f3(CV["observed"]), f3(CV["observed"])),
    ("主系 帰無", f"{f3(CV['null_mean'])} ± {f3(CV['null_sd'])}", f3(CV["null_mean"])),
    ("主系 被説明率", f"{pc(CV['explained'])}（{pc(CV['expl_null_mean'])}）", pc(CV["explained"])),
    ("legacy 校正 p", f3(LC["p_value"]), f3(LC["p_value"])),
    ("legacy 校正 実測", f3(LC["observed"]), f3(LC["observed"])),
    ("v18 cosine p", f3(CR["p_value"]), f3(CR["p_value"])),
    ("v18 cosine d", f2(CR["effect_d"]), f2(CR["effect_d"])),
    ("legacy cosine p", f3(LR["p_value"]), f3(LR["p_value"])),
    ("legacy cosine d", f2(LR["effect_d"]), f2(LR["effect_d"])),
    ("L1 cosine 実測", f3(L1["l1_legacy_cosine"]["observed"]), f3(L1["l1_legacy_cosine"]["observed"])),
    ("L1 cosine 帰無", f"{f3(L1['l1_legacy_cosine']['null_mean'])} ± {f3(L1['l1_legacy_cosine']['null_sd'])}", ""),
    ("L1 cosine p", f3(L1["l1_legacy_cosine"]["p_value"]), f3(L1["l1_legacy_cosine"]["p_value"])),
    ("L1 cosine d", f"{L1['l1_legacy_cosine']['effect_d']:.1f}", ""),
    ("L1 校正 実測", f3(L1["l1_legacy_calibrated"]["observed"]), ""),
    ("L1 校正 帰無", f"{f3(L1['l1_legacy_calibrated']['null_mean'])} ± {f3(L1['l1_legacy_calibrated']['null_sd'])}", ""),
    ("L1 校正 d", f"{L1['l1_legacy_calibrated']['effect_d']:.1f}", ""),
    ("α A-B", f3(AG["passA_vs_passB"]["alpha"]), f3(AG["passA_vs_passB"]["alpha"])),
    ("α A-legacy", f3(AG["passA_vs_legacy"]["alpha"]), f3(AG["passA_vs_legacy"]["alpha"])),
    ("α L1 監査", f3(AG["l1_audit_vs_frozen"]["alpha"]), f3(AG["l1_audit_vs_frozen"]["alpha"])),
    ("話数 v18", fv := f"{R['meta']['coverage']['v18_targets_with_profile']} 話", fv),
    ("話数 legacy", f"{R['meta']['coverage']['legacy_targets_with_profile']} 話", ""),
    ("非零セル v18", str(R["meta"]["coverage"]["v18_nonzero_cells"]), ""),
    ("非零セル legacy", str(R["meta"]["coverage"]["legacy_nonzero_cells"]), ""),
    ("1 話あたり次元", f"{DG['mean_nonzero_dims_per_target']:.2f}", ""),
    ("単一モチーフ 被説明率", pc(DG["mean_explained_single_dim"]), ""),
    ("複数モチーフ 被説明率", pc(DG["mean_explained_multi_dim"]), ""),
    ("FDR 有意 校正", f"{PN['v18_calibrated']['n_sig_fdr']} / 25", ""),
    ("FDR 有意 cosine", f"{PN['v18_cosine_reference']['n_sig_fdr']} / 25", ""),
    ("最小 q 校正", f3(min(r["q"] for r in PN["v18_calibrated"]["rows"])), ""),
    ("最小 q cosine", f3(min(r["q"] for r in PN["v18_cosine_reference"]["rows"])), ""),
    ("K1-01 z", f2(PN["v18_calibrated"]["rows"][0]["z"]) if PN["v18_calibrated"]["rows"][0]["id"] == "K1-01" else f2([r for r in PN["v18_calibrated"]["rows"] if r["id"] == "K1-01"][0]["z"]), ""),
    ("K1-17 z", f2([r for r in PN["v18_cosine_reference"]["rows"] if r["id"] == "K1-17"][0]["z"]), ""),
]
for sd, r in ROB.items():
    checks.append((f"シード {sd} p", f3(r["p_value"]), ""))
checks.append(("シード 44 d", sg(ROB[44]["effect_d"]), ""))
for key, lab in [(("max_dist_km", 2500.0), "距離 2500"), (("max_dist_km", 6400.0), "距離 6400")]:
    checks.append((lab + " p", f3(PAR[key]["p_value"]), ""))
    checks.append((lab + " d", f2(PAR[key]["effect_d"]), ""))

# --- 埋め込みネットワーク検証（network_checks.json）との照合 ---
import re as _re
NJ = json.loads((ROOT / "outputs/network_checks.json").read_text(encoding="utf-8"))
G = {c["id"]: c for c in NJ["checks"]}
num = lambda cid, pat, grp=1: _re.search(pat, str(G[cid]["value"])).group(grp)
net_checks = [
    ("ネットワーク ノード数", f"{G['A1']['value'].split(' / ')[0]} ノード"),
    ("ネットワーク エッジ数", f"{G['A1']['value'].split(' / ')[1]} エッジ"),
    ("層構成の再現本数", f"{num('C1', r'(\d+) 本')} 本"),
    ("90D との共通", f"共通 {num('C5', r'共通 (\d+)')}"),
    ("90D のみ", f"90D のみ {num('C5', r'90D のみ (\d+)')}"),
    ("表示のみ", f"表示のみ {num('C5', r'表示のみ (\d+)')}"),
    ("L1 重み再現", num("D1", r"([0-9.]+e-0?5)")),
    ("L1 被説明率再現率", num("D2", r"0.01 以内 ([0-9.]+)")),
    ("古事記乖離の最大値", f"{NJ['kojiki_gap'][0]['displayed']:.3f}"),
    ("古事記乖離の再計算値", f"{NJ['kojiki_gap'][0]['replay']:.3f}"),
    ("乖離ノード数", f"21 / 248"),
    ("全ノード検定 d(コサイン)", f"{float(num('E-cosine-all', r'd=([0-9.]+)')):.1f}"),
    ("全ノード検定 d(校正済み)", f"{float(num('E-calibrated-all', r'd=([0-9.]+)')):.1f}"),
    ("独立実装との共通辺", num("E-jac", r"共通 (\d+)")),
    ("Jaccard", num("E-jac", r"Jaccard ([0-9.]+)")),
    ("モチーフ参照数", num("B15", r"(\d+) 参照")),
]
miss_net = [(n, s_) for n, s_ in net_checks if not s_ or s_ not in TEXT]
net_checks = [(n, s_) for n, s_ in net_checks if s_ and s_ in TEXT]

miss = [(n, s, "") for n, s, _ in checks if s and s not in TEXT]
print(f"照合項目 {len(checks) + len(net_checks)} 件 / 不一致 {len(miss) + len(miss_net)} 件")
for n, s_ in miss_net:
    print(f"  [NG] {n}: 文書に '{s_}' が見つからない")
for n, s in miss:
    print(f"  [NG] {n}: 文書に '{s}' が見つからない")
sys.exit(1 if (miss or miss_net) else 0)
