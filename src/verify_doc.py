# -*- coding: utf-8 -*-
"""
verify_doc.py -- 手書き文書（docs/v18_method_and_results.md、ADR 0002/0003、
registry.md、査読用サマリ日英版）に書かれた数値が実測 JSON と一致することを機械照合する。

文書中の表記（小数点以下の桁数・記号）に合わせて値を整形し、文字列として存在するかを見る。
不一致があれば exit 1。
"""
from __future__ import annotations
import json, math, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/v18_method_and_results.md"
CFG = json.loads((ROOT / "config/analysis.json").read_text(encoding="utf-8"))
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
a1_parts = G["A1"]["value"].split(" / ")
c1_cnt = num("C1", r"(\d+) 本")
c5_common = num("C5", r"共通 (\d+)")
c5_only90 = num("C5", r"90D のみ (\d+)")
c5_onlymp = num("C5", r"表示のみ (\d+)")
e_cos_d = float(num("E-cosine-all", r"d=([0-9.]+)"))
e_cal_d = float(num("E-calibrated-all", r"d=([0-9.]+)"))
e_jac_cnt = num("E-jac", r"共通 (\d+)")
b15_refs = num("B15", r"(\d+) 参照")
net_checks = [
    ("ネットワーク ノード数", f"{a1_parts[0]} ノード"),
    ("ネットワーク エッジ数", f"{a1_parts[1]} エッジ"),
    ("層構成の再現本数", f"{c1_cnt} 本"),
    ("90D との共通", f"共通 {c5_common}"),
    ("90D のみ", f"90D のみ {c5_only90}"),
    ("表示のみ", f"表示のみ {c5_onlymp}"),
    ("L1 重み再現", num("D1", r"([0-9.]+e-0?5)")),
    ("L1 被説明率再現率", num("D2", r"0.01 以内 ([0-9.]+)")),
    ("古事記乖離の最大値", f"{NJ['kojiki_gap'][0]['displayed']:.3f}"),
    ("古事記乖離の再計算値", f"{NJ['kojiki_gap'][0]['replay']:.3f}"),
    ("乖離ノード数", "21 / 248"),
    ("全ノード検定 d(コサイン)", f"{e_cos_d:.1f}"),
    ("全ノード検定 d(校正済み)", f"{e_cal_d:.1f}"),
    ("独立実装との共通辺", e_jac_cnt),
    ("Jaccard", num("E-jac", r"Jaccard ([0-9.]+)")),
    ("モチーフ参照数", b15_refs),
]
miss_net = [(n, s_) for n, s_ in net_checks if not s_ or s_ not in TEXT]
net_checks = [(n, s_) for n, s_ in net_checks if s_ and s_ in TEXT]

# --- ADR 0002（運用シミュレーション）との照合 ---
ADR2 = (ROOT / "docs/adr/0002-long-run-independent-review.md")
T2 = ADR2.read_text(encoding="utf-8") if ADR2.exists() else ""
SW = json.loads((ROOT / "outputs/swarm_sim.json").read_text(encoding="utf-8"))
bv = {r["shared_bias"]: r for r in SW["bias_variance"]}
sel = {r["branches"]: r for r in SW["selection"]}
herd = {r["anchor_prob"]: r for r in SW["herding"]}
adr_checks = [
    ("Q1 b=0.10 R=10", f"{bv[0.1]['R=10']:.3f}"),
    ("Q1 b=0.10 R=1", f"{bv[0.1]['R=1']:.3f}"),
    ("Q1 b=0.20 R=10", f"{bv[0.2]['R=10']:.3f}"),
    ("Q2 144 枝の族錯誤率", f"{sel[144]['fwer']:.4f}"),
    ("Q2 144 枝の最小 p 中央値", f"{sel[144]['median_min_p']:.4f}"),
    ("Q2 144 枝の必要置換回数", f"{sel[144]['perm_needed']}"),
    ("Q2 12 枝の Holm しきい値", f"{sel[12]['holm_thr']:.2e}"),
    ("Q3 q=0.9 の誤り残存", f"{herd[0.9]['error_persistence']:.3f}"),
    ("Q3 独立多数決", f"{herd[0.9]['independent_majority']:.3f}"),
    ("Q3 鎖の正答率", f"{herd[0.9]['chain_accuracy']:.3f}"),
]
miss_adr = [(n, s_) for n, s_ in adr_checks if s_ not in T2]

# --- v18.1 追補（§11）・ADR 0003・registry・日英査読サマリとの照合 ---
AUD = json.loads((ROOT / CFG["display_policy"]["derived_audit_path"]).read_text(encoding="utf-8"))
PC = L2["v18_passC_calibrated"]
max_gap_row = max(AUD["gap_nodes"], key=lambda r: abs(r["gap_l1"]))
REG_P = ROOT / "docs/registry.md"
REG_T = REG_P.read_text(encoding="utf-8").replace("\u2212", "-") if REG_P.exists() else ""
n_hyp = 0
for ln in REG_T.splitlines():
    if ln.startswith("|"):
        cols = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cols) > 3 and cols[0].isdigit() and cols[3] == "仮説検定":
            n_hyp += 1
holm1 = CFG["inference"]["alpha"] / n_hyp if n_hyp else CFG["inference"]["alpha"]
min_perm = math.ceil(1.0 / holm1) - 1

v181_items = [
    ("v18.1 評価可能ノード", str(AUD["evaluable_l1_nodes"])),
    ("v18.1 表示乖離話数", str(AUD["gap_count"])),
    ("v18.1 v16.L1 出所数", str(AUD["provenance_counts"]["v16.L1"])),
    ("v18.1 decomp 出所数", str(AUD["provenance_counts"]["decomp.total_final"])),
    ("v18.1 pureL2 出所数", str(AUD["provenance_counts"]["pureL2_dom"])),
    ("v18.1 K1-05 表示", f3(max_gap_row["displayed_pct"])),
    ("v18.1 K1-05 再計算", f"{max_gap_row['replay_l1_from_edges']:.4f}"),
    ("v18.1 K1-05 乖離", f"{max_gap_row['gap_l1']:.4f}"),
    ("v18.1 α A-B(13)", f3(AG["passA_vs_passB_13"]["alpha"])),
    ("v18.1 α A-C(13)", f3(AG["passA_vs_passC_13"]["alpha"])),
    ("v18.1 α B-C(13)", f3(AG["passB_vs_passC_13"]["alpha"])),
    ("v18.1 完全一致 A-C", pc(AG["passA_vs_passC_13"]["exact_agreement"])),
    ("v18.1 完全一致 B-C", pc(AG["passB_vs_passC_13"]["exact_agreement"])),
    ("v18.1 Δα 低下量", f3(AG["delta_alpha_same13_to_passC"])),
    ("v18.1 passC 実測", f3(PC["observed"])),
    ("v18.1 passC 帰無", f"{f3(PC['null_mean'])} ± {f3(PC['null_sd'])}"),
    ("v18.1 passC p", f3(PC["p_value"])),
    ("v18.1 passC d", sg(PC["effect_d"])),
    ("v18.1 passC 説明率", pc(PC["explained"])),
    ("v18.1 passC エッジ数", str(PC["n_edges"])),
    ("v18.1 Holm 第1しきい値", f"{holm1:.4f}"),
    ("v18.1 必要最小置換", str(min_perm)),
]

ADR3_P = ROOT / "docs/adr/0003-display-mix-policy.md"
T3 = ADR3_P.read_text(encoding="utf-8").replace("\u2212", "-") if ADR3_P.exists() else ""
adr3_checks = [
    ("ノード数", str(AUD["total_nodes"])),
    ("エッジ数", a1_parts[1]),
    ("評価可能ノード", str(AUD["evaluable_l1_nodes"])),
    ("乖離話数", str(AUD["gap_count"])),
    ("K1-05 表示", f3(max_gap_row["displayed_pct"])),
    ("K1-05 再計算", f3(max_gap_row["replay_l1_from_edges"])),
    ("v16.L1 件数", str(AUD["provenance_counts"]["v16.L1"])),
    ("decomp 件数", str(AUD["provenance_counts"]["decomp.total_final"])),
    ("pureL2 件数", str(AUD["provenance_counts"]["pureL2_dom"])),
]

reg_checks = [
    ("Holm 第1しきい値", f"{holm1:.4f}"),
    ("必要最小置換", str(min_perm)),
    ("NET-DISPLAY-21 一致数", f"{AUD['gap_count']} / {AUD['gap_count']}"),
    ("L2-PASSC-INDEP α", f3(AG["passA_vs_passC_13"]["alpha"])),
    ("L2-PASSC-INDEP Δα", f3(AG["delta_alpha_same13_to_passC"])),
    ("L2-PASSC-SENS 実測", f3(PC["observed"])),
    ("L2-PASSC-SENS p", f3(PC["p_value"])),
    ("L2-PASSC-SENS d", sg(PC["effect_d"])),
]

summary_checks = [
    ("L2 主系 実測", f3(CV["observed"])),
    ("L2 主系 帰無", f"{f3(CV['null_mean'])} ± {f3(CV['null_sd'])}"),
    ("L2 主系 p", f3(CV["p_value"])),
    ("L2 主系 d", sg(CV["effect_d"])),
    ("L2 legacy 校正 実測", f3(LC["observed"])),
    ("L2 legacy 校正 p", f3(LC["p_value"])),
    ("L2 cosine p", f3(CR["p_value"])),
    ("L2 cosine d", f2(CR["effect_d"])),
    ("L2 passC 実測", f3(PC["observed"])),
    ("L2 passC 帰無", f"{f3(PC['null_mean'])} ± {f3(PC['null_sd'])}"),
    ("L2 passC p", f3(PC["p_value"])),
    ("L2 passC d", sg(PC["effect_d"])),
    ("L1 cosine p", f3(L1["l1_legacy_cosine"]["p_value"])),
    ("L1 cosine d", f"{L1['l1_legacy_cosine']['effect_d']:.2f}"),
    ("L1 校正 実測", f3(L1["l1_legacy_calibrated"]["observed"])),
    ("L1 校正 d", f"{L1['l1_legacy_calibrated']['effect_d']:.2f}"),
    ("α A-B(555)", f3(AG["passA_vs_passB"]["alpha"])),
    ("α A-legacy", f3(AG["passA_vs_legacy"]["alpha"])),
    ("α L1監査", f3(AG["l1_audit_vs_frozen"]["alpha"])),
    ("α A-B(13)", f3(AG["passA_vs_passB_13"]["alpha"])),
    ("α A-C(13)", f3(AG["passA_vs_passC_13"]["alpha"])),
    ("α B-C(13)", f3(AG["passB_vs_passC_13"]["alpha"])),
    ("Δα 低下量", f3(AG["delta_alpha_same13_to_passC"])),
    ("ネットワーク ノード", str(AUD["total_nodes"])),
    ("ネットワーク エッジ", a1_parts[1]),
    ("90D エッジ", c1_cnt),
    ("評価可能ノード", str(AUD["evaluable_l1_nodes"])),
    ("乖離話数", str(AUD["gap_count"])),
    ("K1-05 表示", f3(max_gap_row["displayed_pct"])),
    ("K1-05 再計算", f"{max_gap_row['replay_l1_from_edges']:.4f}"),
    ("単一モチーフ被説明率", pc(DG["mean_explained_single_dim"])),
    ("複数モチーフ被説明率", pc(DG["mean_explained_multi_dim"])),
    ("Q1 b=0.10 R=1", f"{bv[0.1]['R=1']:.3f}"),
    ("Q1 b=0.10 R=10", f"{bv[0.1]['R=10']:.3f}"),
    ("Q2 144 族錯誤率", f"{sel[144]['fwer']:.4f}"),
    ("Q2 144 最小p中央値", f"{sel[144]['median_min_p']:.4f}"),
    ("Holm 第1しきい値", f"{holm1:.4f}"),
    ("必要最小置換", str(min_perm)),
]

JA_P = ROOT / "docs/peer_review_summary_ja.md"
EN_P = ROOT / "docs/peer_review_summary_en.md"
T_JA = JA_P.read_text(encoding="utf-8").replace("\u2212", "-") if JA_P.exists() else ""
T_EN = EN_P.read_text(encoding="utf-8").replace("\u2212", "-") if EN_P.exists() else ""

miss_extra = []
for doc_label, txt, items in [
    ("v18§11", TEXT, v181_items),
    ("ADR0003", T3, adr3_checks),
    ("registry", REG_T, reg_checks),
    ("サマリJA", T_JA, summary_checks),
    ("サマリEN", T_EN, summary_checks),
]:
    if not txt:
        miss_extra.append((f"{doc_label} ファイル存在", doc_label))
    else:
        for n, s_ in items:
            if s_ not in txt:
                miss_extra.append((f"{doc_label} {n}", s_))

miss = [(n, s, "") for n, s, _ in checks if s and s not in TEXT]
total_checks = (len(checks) + len(net_checks) + len(adr_checks) + len(v181_items)
                + len(adr3_checks) + len(reg_checks) + len(summary_checks) * 2)
total_miss = len(miss) + len(miss_net) + len(miss_adr) + len(miss_extra)
print(f"照合項目 {total_checks} 件 / 不一致 {total_miss} 件")
for n, s_ in miss_adr:
    print(f"  [NG] ADR0002 {n}: '{s_}' が見つからない")
for n, s_ in miss_net:
    print(f"  [NG] {n}: 文書に '{s_}' が見つからない")
for n, s_ in miss_extra:
    print(f"  [NG] {n}: 文書に '{s_}' が見つからない")
for n, s in miss:
    print(f"  [NG] {n}: 文書に '{s}' が見つからない")
sys.exit(1 if total_miss else 0)
