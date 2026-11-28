# -*- coding: utf-8 -*-
"""
v18 run_all.py -- 全解析を 1 コマンドで実行し、結果・レポート・マニフェストを出力する。

主エンドポイント = ターゲットごとの「最良親との校正済み類似度 (max z)」の平均
帰無モデル       = 親候補ベクトルの次元並べ替え（モチーフの意味的対応を破壊）

実行:  python3 src/run_all.py
"""
from __future__ import annotations
import json, hashlib, platform, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CFG = json.loads((ROOT / "config/analysis.json").read_text(encoding="utf-8"))
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def matrix_from(recs, vocab, ids):
    M = pd.DataFrame(0.0, index=ids, columns=vocab)
    for r in recs:
        if r["target"] in M.index:
            for k, v in r["levels"].items():
                if k in M.columns:
                    M.loc[r["target"], k] = float(v)
    return M


def summarize(run, metric_is_z):
    return dict(
        metric="mean_best_match_z" if metric_is_z else "mean_best_cosine",
        observed=run["observed"], null_mean=run["null_mean"], null_sd=run["null_sd"],
        p_value=run["p_value"], effect_d=run["effect_d"],
        node_ci=list(S.bootstrap_ci(run["top_node"][~np.isnan(run["top_node"])])),
        explained=run["explained"], expl_null_mean=run["expl_null_mean"],
        expl_null_sd=run["expl_null_sd"], expl_p_value=run["expl_p_value"],
        n_edges=run["n_edges"],
    )


def main():
    global np, pd, E, S
    t0 = time.time()
    net_status_path = OUT / "network_verification_status.json"
    net_status_path.write_text(json.dumps({
        "schema": "network-verification-status/1",
        "status": "running",
        "reason": "pipeline started; network verification has not run yet",
        "package_root": None,
        "expected": {"nodes": CFG["network"]["expected"]["nodes"],
                     "edges": CFG["network"]["expected"]["edges"]},
        "checks": None,
        "unverified_scope": ["network verification has not run yet"],
        "artifacts": [],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        import numpy as np
        import pandas as pd
        import engine as E          # noqa: E402
        import stats as S           # noqa: E402
    except ModuleNotFoundError as exc:
        dependency_status = {
            "schema": "network-verification-status/1",
            "status": "unavailable",
            "reason": f"pipeline dependencies are missing: {exc}",
            "package_root": None,
            "expected": {"nodes": CFG["network"]["expected"]["nodes"],
                         "edges": CFG["network"]["expected"]["edges"]},
            "checks": None,
            "unverified_scope": ["全解析が依存不足で未実行", "v17 ネットワーク全件検証も未実行"],
            "artifacts": [],
        }
        net_status_path.write_text(json.dumps(dependency_status, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
        print("[UNAVAILABLE] " + dependency_status["reason"])
        raise SystemExit(2)
    except Exception as exc:
        import_status = {
            "schema": "network-verification-status/1",
            "status": "failed",
            "reason": f"pipeline runtime import failed: {type(exc).__name__}: {exc}",
            "package_root": None,
            "expected": {"nodes": CFG["network"]["expected"]["nodes"],
                         "edges": CFG["network"]["expected"]["edges"]},
            "checks": None,
            "unverified_scope": ["全解析の初期化が失敗", "v17 ネットワーク全件検証も未実行"],
            "artifacts": [],
        }
        net_status_path.write_text(json.dumps(import_status, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
        print("[FAILED] " + import_status["reason"])
        raise SystemExit(1)
    import subprocess
    v = subprocess.run([sys.executable, str(ROOT / "src/validate.py")],
                       capture_output=True, text=True)
    print(v.stdout.strip().splitlines()[-1] if v.stdout.strip() else v.stderr.strip())
    if v.returncode != 0:
        raise SystemExit("validation failed -- aborting")
    hc = subprocess.run([sys.executable, str(ROOT / "src/audit_no_hardcode.py")],
                        capture_output=True, text=True)
    if hc.returncode != 0:
        raise SystemExit("hard-coded constant audit failed -- aborting")
    vocab = CFG["layer2"]["vocab"]
    inj = CFG["inference"]
    nodes = pd.read_csv(ROOT / "data/frozen/nodes_297.csv")

    A = load_jsonl(ROOT / "annotations/l2_kojiki_passA.jsonl")
    Bp = load_jsonl(ROOT / "annotations/l2_kojiki_passB.jsonl")
    ANC = load_jsonl(ROOT / "annotations/l2_anchors_passA.jsonl")
    LEG = load_jsonl(ROOT / "annotations/legacy_v17_l2.jsonl")
    L1A = load_jsonl(ROOT / "annotations/l1_audit_passA.jsonl")

    k_ids = [r["target"] for r in A]
    a_ids = [r["target"] for r in ANC]
    sub = nodes[nodes["id"].isin(k_ids + a_ids)].reset_index(drop=True)
    sub["is_target"] = sub["kind"].eq("kojiki")

    Mv18 = matrix_from(A + ANC, vocab, sub["id"])
    Mleg = matrix_from(LEG, vocab, sub["id"])
    Mv18.to_csv(OUT / "matrix_l2_v18_passA.csv")
    Mleg.to_csv(OUT / "matrix_l2_legacy_v17.csv")

    coverage = dict(
        v18_targets_with_profile=int((Mv18[sub.is_target.values].sum(axis=1) > 0).sum()),
        legacy_targets_with_profile=int((Mleg[sub.is_target.values].sum(axis=1) > 0).sum()),
        v18_nonzero_cells=int((Mv18.values > 0).sum()),
        legacy_nonzero_cells=int((Mleg.values > 0).sum()),
        anchors=len(a_ids),
    )

    lvl = lambda recs: {(r["target"], k): int(v) for r in recs for k, v in r["levels"].items()}
    lA, lB, lL = lvl(A), lvl(Bp), lvl(LEG)
    full = lambda d: {(t, k): d.get((t, k), 0) for t in k_ids for k in vocab}
    agree_AB = S.agreement_report(full(lA), full(lB))
    agree_AL = S.agreement_report(full(lA), full(lL))

    agree_extra = {}
    pc_cfg = CFG.get("pass_c")
    C_recs = []
    if pc_cfg and (ROOT / pc_cfg["annotation_path"]).exists():
        C_recs = load_jsonl(ROOT / pc_cfg["annotation_path"])
        c_ids = pc_cfg["target_ids"]
        lC = lvl(C_recs)
        full13 = lambda d: {(t, k): d.get((t, k), 0) for t in c_ids for k in vocab}
        ab13 = S.agreement_report(full13(lA), full13(lB))
        ac13 = S.agreement_report(full13(lA), full13(lC))
        bc13 = S.agreement_report(full13(lB), full13(lC))
        agree_extra = dict(
            passA_vs_passB_13=ab13,
            passA_vs_passC_13=ac13,
            passB_vs_passC_13=bc13,
            passA_vs_passC_37_padded=S.agreement_report(full(lA), full(lC)),
            delta_alpha_same13_to_passC=float(ab13["alpha"] - ac13["alpha"]),
            delta_alpha_555baseline_to_passC=float(agree_AB["alpha"] - ac13["alpha"]),
        )

    l1aud = {(r["target"], k): int(r["levels"].get(k, 0)) for r in L1A for k in CFG["layer1_audit"]["vocab"]}
    l1froz = pd.read_csv(ROOT / "data/frozen/l1_75d_legacy_matrix.csv").set_index("id")
    LM = CFG["layer2"]["legacy_level_map"]
    def to_lvl(w):
        return 0 if w <= 0 else (1 if w < LM["lo"] else (2 if w < LM["hi"] else 3))
    l1leg = {(t, k): to_lvl(float(l1froz.loc[t, k])) for (t, k) in l1aud}
    agree_L1 = S.agreement_report(l1aud, l1leg)

    res = {"meta": {}, "agreement": {}, "layer2": {"per_node": {}}, "layer1": {}, "sensitivity": {}}
    tm, pm = sub["is_target"].values, ~sub["is_target"].values
    p_eng = dict(CFG["engine"]["primary"])
    r_eng = dict(CFG["engine"]["reference_v17_compatible"])

    runs = {}
    for label, M, cfgd, isz in [
        ("v18_calibrated", Mv18, p_eng, True),
        ("legacy_v17_calibrated", Mleg, p_eng, True),
        ("v18_cosine_reference", Mv18, r_eng, False),
        ("legacy_v17_cosine_reference", Mleg, r_eng, False),
    ]:
        run = E.run_with_null(sub, M.values, E.EngineConfig(**cfgd), tm, pm,
                              n_perm=inj["n_perm"], seed=inj["seed"])
        runs[label] = (run, isz)
        res["layer2"][label] = summarize(run, isz)

    # ノード別（両モード・FDR 補正）
    def per_node_block(cfgd):
        cfg = E.EngineConfig(**cfgd)
        V = Mv18.values
        pool = np.where(pm)[0]
        rng = np.random.default_rng(inj["seed"] + 1)
        n_node = inj.get("n_node_perm", 100)
        per = np.zeros((n_node, len(sub)))
        for k in range(n_node):
            Vp = E._feature_shuffle(V, pool, rng)
            _, _, _, tk = E.peel(sub, Vp, cfg)
            per[k] = tk
        obs = np.array(runs[label_for(cfgd)][0]["top_node"])
        rows_, ps_ = [], []
        for j in np.where(tm)[0]:
            if np.isnan(obs[j]):
                continue
            mu, sd = per[:, j].mean(), per[:, j].std(ddof=1)
            zz = (obs[j] - mu) / sd if sd > 1e-9 else 0.0
            pp = (np.sum(per[:, j] >= obs[j]) + 1) / (n_node + 1)
            rows_.append({"id": sub.loc[j, "id"], "observed": round(float(obs[j]), 3),
                          "explained": round(float(runs[label_for(cfgd)][0]["expl_node"][j]), 4),
                          "null_mean": round(float(mu), 3), "z": round(float(zz), 3),
                          "p": round(float(pp), 4)})
            ps_.append(pp)
        rej_, q_ = S.bh_fdr(np.array(ps_), alpha=inj["alpha"])
        for r_, qq, rr in zip(rows_, q_, rej_):
            r_["q"] = round(float(qq), 4)
            r_["sig_fdr"] = bool(rr)
        rows_.sort(key=lambda d: -d["z"])
        return rows_, int(np.sum(rej_)), int(np.isnan(obs[tm]).sum()), int(tm.sum())

    def label_for(cfgd):
        return "v18_calibrated" if cfgd is p_eng else "v18_cosine_reference"

    for lbl, cfgd in [("v18_calibrated", p_eng), ("v18_cosine_reference", r_eng)]:
        rows_, nsig, nnan, ntot = per_node_block(cfgd)
        res["layer2"]["per_node"][lbl] = dict(rows=rows_, n_sig_fdr=nsig,
                                              n_evaluable=ntot - nnan, n_targets=ntot)

    # 診断: 単一次元ターゲットの飽和・非被説明ターゲット
    nnz = (Mv18.values[tm] > 0).sum(axis=1)
    exp_node = runs["v18_calibrated"][0]["expl_node"][tm]
    res["layer2"]["diagnostics"] = dict(
        n_targets=int(tm.sum()),
        n_single_dim=int((nnz == 1).sum()),
        mean_explained_single_dim=float(exp_node[nnz == 1].mean()) if (nnz == 1).any() else None,
        mean_explained_multi_dim=float(exp_node[nnz > 1].mean()) if (nnz > 1).any() else None,
        n_zero_explained=int((exp_node == 0).sum()),
        mean_nonzero_dims_per_target=float(nnz.mean()),
    )

    # シード頑健性（主系のみ）
    rob = []
    for sd_ in inj.get("robustness_seeds", [inj["seed"]]):
        r2 = E.run_with_null(sub, Mv18.values, E.EngineConfig(**p_eng), tm, pm,
                             n_perm=inj["n_perm"], seed=int(sd_))
        rob.append(dict(seed=int(sd_), observed=r2["observed"], null_mean=r2["null_mean"],
                        null_sd=r2["null_sd"], p_value=r2["p_value"], effect_d=r2["effect_d"]))
    res["layer2"]["seed_robustness"] = rob

    # 主エンドポイントのパラメータ頑健性（結論が手調整値で反転しないか）
    prob = []
    variants = [("max_dist_km", d_, dict(max_dist_km=d_, proto_dist_km=d_))
                for d_ in CFG["engine"]["sensitivity"]["max_dist_km"]]
    variants += [("z_thresh", z_, dict(z_thresh=z_))
                 for z_ in CFG["engine"]["sensitivity"]["z_thresh"]]
    variants += [("max_parents", m_, dict(max_parents=m_))
                 for m_ in CFG["engine"]["sensitivity"]["max_parents"]]
    for name, val, over in variants:
        c = dict(p_eng); c.update(over)
        rr = E.run_with_null(sub, Mv18.values, E.EngineConfig(**c), tm, pm,
                             n_perm=inj["n_perm"], seed=inj["seed"])
        prob.append(dict(param=name, value=val, observed=rr["observed"], p_value=rr["p_value"],
                         effect_d=rr["effect_d"]))
    res["layer2"]["param_robustness"] = prob

    # 第1層（凍結 legacy 75D）
    l1 = pd.read_csv(ROOT / "data/frozen/l1_75d_legacy_matrix.csv")
    l1n = nodes[nodes["kind"] != "anchor"].reset_index(drop=True)
    l1 = l1.set_index("id").loc[l1n["id"]].reset_index()
    V1 = l1[[c for c in l1.columns if c != "id"]].values
    t1, p1 = l1n["kind"].eq("kojiki").values, ~l1n["kind"].eq("kojiki").values
    for label, cfgd, isz in [("l1_legacy_cosine", r_eng, False), ("l1_legacy_calibrated", p_eng, True)]:
        run = E.run_with_null(l1n, V1, E.EngineConfig(**cfgd), t1, p1,
                              n_perm=inj["n_perm"], seed=inj["seed"])
        res["layer1"][label] = summarize(run, isz)

    # 感度分析
    sens = []
    for zt in CFG["engine"]["sensitivity"]["z_thresh"]:
        c = E.EngineConfig(**p_eng); c.z_thresh = zt
        _, e, _, _ = E.peel(sub, Mv18.values, c)
        sens.append(dict(param="z_thresh", value=zt, explained=float(e[tm].mean())))
    for md in CFG["engine"]["sensitivity"]["max_dist_km"]:
        c = E.EngineConfig(**p_eng); c.max_dist_km = md; c.proto_dist_km = md
        _, e, _, _ = E.peel(sub, Mv18.values, c)
        sens.append(dict(param="max_dist_km", value=md, explained=float(e[tm].mean())))
    for mp in CFG["engine"]["sensitivity"]["max_parents"]:
        c = E.EngineConfig(**p_eng); c.max_parents = mp
        _, e, _, _ = E.peel(sub, Mv18.values, c)
        sens.append(dict(param="max_parents", value=mp, explained=float(e[tm].mean())))
    for st in CFG["engine"]["sensitivity"]["score_thresh"]:
        c = E.EngineConfig(**r_eng); c.score_thresh = st
        _, e, _, _ = E.peel(sub, Mv18.values, c)
        sens.append(dict(param="score_thresh(cosine)", value=st, explained=float(e[tm].mean())))
    for dt in CFG["engine"]["sensitivity"]["dot_thresh"]:
        c = E.EngineConfig(**r_eng); c.dot_thresh = dt
        _, e, _, _ = E.peel(sub, Mv18.values, c)
        sens.append(dict(param="dot_thresh(cosine)", value=dt, explained=float(e[tm].mean())))
    res["sensitivity"] = sens

    if C_recs:
        c_map = {r["target"]: r for r in C_recs}
        AC = [c_map.get(r["target"], r) for r in A]
        Mv18_passC = matrix_from(AC + ANC, vocab, sub["id"])
        Mv18_passC.to_csv(OUT / "matrix_l2_v18_passC_mix.csv")
        run_c = E.run_with_null(sub, Mv18_passC.values, E.EngineConfig(**p_eng), tm, pm,
                                n_perm=inj["n_perm"], seed=inj["seed"])
        res["layer2"]["v18_passC_calibrated"] = summarize(run_c, True)

    # 埋め込みネットワークの全件検証。資材が無い場合も「skipped」で隠さず理由を保存する。
    try:
        import verify_network as VN
        network_exit = VN.main()
        if net_status_path.exists():
            net_status = json.loads(net_status_path.read_text(encoding="utf-8"))
        else:
            net_status = {
                "schema": "network-verification-status/1",
                "status": "failed",
                "reason": f"verify_network returned {network_exit} without a status file",
                "unverified_scope": ["network verification status was not recorded"],
                "artifacts": [],
            }
        expected_exit_state = {0: "passed", 1: "failed", 2: "unavailable"}.get(network_exit)
        if expected_exit_state is None or net_status.get("status") != expected_exit_state:
            net_status = {
                "schema": "network-verification-status/1",
                "status": "failed",
                "reason": (f"verify_network exit/status mismatch: exit={network_exit}, "
                           f"status={net_status.get('status', 'missing')}"),
                "unverified_scope": ["network verification result could not be trusted"],
                "artifacts": [],
            }
            net_status_path.write_text(json.dumps(net_status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if net_status.get("status") == "unavailable":
            print("[UNVERIFIED] ネットワーク全件検証: " + str(net_status.get("reason", "理由不明")))
            print("  未検証範囲: " + " / ".join(net_status.get("unverified_scope", [])))
        elif net_status.get("status") != "passed":
            print("[NETWORK " + str(net_status.get("status", "unknown")).upper() + "] "
                  + str(net_status.get("reason", "理由不明")))
    except Exception as exc:
        for artifact in ("network_verification.md", "network_checks.json",
                         "network_edge_audit.csv", "network_node_audit.csv"):
            (OUT / artifact).unlink(missing_ok=True)
        net_status = {
            "schema": "network-verification-status/1",
            "status": "failed",
            "reason": f"{type(exc).__name__}: {exc}",
            "unverified_scope": ["network verification could not start or complete"],
            "artifacts": [],
        }
        net_status_path.write_text(json.dumps(net_status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("[NETWORK FAILED] " + net_status["reason"])

    # 判定
    prim = res["layer2"]["v18_calibrated"]
    alpha_ok = (agree_AB["alpha"] or 0) >= CFG["agreement"]["min_alpha_for_claim"]
    signal = bool(prim["p_value"] < inj["alpha"] and prim["effect_d"] >= 0.8 and alpha_ok)
    res["decision"] = dict(
        rule="主エンドポイント p<0.05 かつ 効果量 d>=0.8 かつ Krippendorff alpha>=0.667",
        metric=prim["metric"], observed=prim["observed"], p_value=prim["p_value"],
        effect_d=prim["effect_d"], alpha=agree_AB["alpha"], alpha_ok=alpha_ok,
        layer2_signal=signal,
        verdict=("第2層に情報を認める" if signal else "第2層に情報を認めない（帰無仮説を棄却できない）"),
    )
    res["meta"] = dict(
        version="18.0", generated_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__,
        runtime_sec=round(time.time() - t0, 1), config=CFG, coverage=coverage,
        validation="src/validate.py exit 0 / src/audit_no_hardcode.py exit 0",
        network_verification=net_status,
        inputs={str(p.relative_to(ROOT)): sha256(p) for p in
                sorted(list((ROOT / "annotations").glob("*.jsonl")) +
                       list((ROOT / "data/frozen").glob("*.csv")) +
                       [ROOT / "config/analysis.json"])},
    )
    res["agreement"] = dict(passA_vs_passB=agree_AB, passA_vs_legacy=agree_AL,
                            l1_audit_vs_frozen=agree_L1, **agree_extra)
    (OUT / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    make_report(res)
    # 枝 #8–#11 の派生物（edge_reproduction / path_dependency / display_reproducibility）
    for script in ("edge_reproduction.py", "path_dependency.py", "display_reproducibility.py"):
        r = subprocess.run([sys.executable, str(ROOT / "src" / script)],
                           capture_output=True, text=True)
        print(("[OK] " if r.returncode == 0 else "[NG] ") + script + ": " +
              ((r.stdout.strip().splitlines() or [""])[0]))
    vn = subprocess.run([sys.executable, str(ROOT / "src/verify_numbers.py")],
                        capture_output=True, text=True)
    print(vn.stdout.strip())
    vd = subprocess.run([sys.executable, str(ROOT / "src/verify_doc.py")],
                        capture_output=True, text=True)
    doc_ok = (vd.returncode == 0)
    vd_lines = vd.stdout.strip().splitlines()
    res["meta"]["doc_check"] = next((line for line in vd_lines if line.startswith("照合項目")),
                                     vd_lines[0] if vd_lines else "")
    (OUT / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(("文書照合 OK: " if doc_ok else "文書照合 NG: ") + res["meta"]["doc_check"])
    print(("数値ゲート OK: " if vn.returncode == 0 else "数値ゲート NG: ") +
          (vn.stdout.strip().splitlines() or [""])[0])
    if not doc_ok:
        if vd.stdout.strip():
            print(vd.stdout.strip())
        if vd.stderr.strip():
            print(vd.stderr.strip(), file=sys.stderr)
    man = [f"{sha256(p)}  {p.name}" for p in sorted(OUT.glob("*"))
           if p.is_file() and p.name != "manifest.sha256" and not p.name.startswith(".")]
    (OUT / "manifest.sha256").write_text("\n".join(man) + "\n", encoding="utf-8")
    print(json.dumps(res["decision"], ensure_ascii=False, indent=2))
    print("done:", OUT)
    if not doc_ok or not vn.returncode == 0 or net_status.get("status") == "failed":
        raise SystemExit(1)


def pct(x):
    return f"{100*x:.2f}%"


def make_report(res):
    L, a = [], None
    a = L.append
    m = res["meta"]
    a("# v18 検証結果レポート（自動生成）\n")
    a(f"生成: {m['generated_at']} / 実行 {m['runtime_sec']} 秒 / Python {m['python']} / "
      f"numpy {m['numpy']} / pandas {m['pandas']}\n")
    a("`src/run_all.py` が `outputs/results.json` から機械生成。手入力の数値は含まない。\n")

    net = m.get("network_verification", {})
    net_state = net.get("status", "unknown") if isinstance(net, dict) else "unknown"
    state_ja = {"passed": "全検査を実行", "failed": "検証失敗", "unavailable": "未検証（資材不足）"}.get(net_state, net_state)
    a("## ネットワーク全件検証の状態\n")
    a(f"- 状態: **{state_ja}**")
    if isinstance(net, dict) and net.get("reason"):
        a(f"- 理由: {net['reason']}")
    if isinstance(net, dict) and net.get("failed_checks"):
        a("- NG検査ID: " + ", ".join(net["failed_checks"]))
    if isinstance(net, dict) and net.get("unverified_scope"):
        a("- 未検証範囲: " + " / ".join(net["unverified_scope"]))
    a("")

    d = res["decision"]
    a("## 1. 事前登録された判定\n")
    a(f"- ルール: {d['rule']}")
    a(f"- 主エンドポイント（{d['metric']}）= {d['observed']:.3f} / 帰無平均 "
      f"{res['layer2']['v18_calibrated']['null_mean']:.3f} ± "
      f"{res['layer2']['v18_calibrated']['null_sd']:.3f} / p = {d['p_value']:.4f} / d = {d['effect_d']:.2f}")
    a(f"- Krippendorff α（二重評定）= {d['alpha']:.3f}（基準 {CFG['agreement']['min_alpha_for_claim']}）")
    a(f"- **判定: {d['verdict']}**\n")

    a("## 2. アノテーションの信頼性\n")
    a("| 比較 | セル数 | Krippendorff α（順序） | 完全一致率 | ±1 以内 |")
    a("| :--- | ---: | ---: | ---: | ---: |")
    ag_rows = [
        ("LLM pass A vs pass B（L2・37 話 0 埋め基準）", res["agreement"]["passA_vs_passB"]),
        ("LLM pass A vs v17 手書き（L2・37 話）", res["agreement"]["passA_vs_legacy"]),
        ("LLM 監査 vs v16 凍結値（L1 10 次元 × 12 話）", res["agreement"]["l1_audit_vs_frozen"]),
    ]
    for label, key in [
        ("LLM pass A vs pass B（L2・二重評定 13 話のみ）", "passA_vs_passB_13"),
        ("LLM pass A vs pass C（L2・中立操作定義 13 話）", "passA_vs_passC_13"),
        ("LLM pass B vs pass C（L2・中立操作定義 13 話）", "passB_vs_passC_13"),
    ]:
        if key in res["agreement"]:
            ag_rows.append((label, res["agreement"][key]))
    for nm, x in ag_rows:
        a(f"| {nm} | {x['n_cells']} | {x['alpha']:.3f} | {pct(x['exact_agreement'])} | {pct(x['within1_agreement'])} |")
    if "delta_alpha_same13_to_passC" in res["agreement"]:
        a(f"\n語彙変更による α 低下量（同一 13 話 195 セル基準）: "
          f"{res['agreement']['delta_alpha_same13_to_passC']:.3f} "
          f"（{res['agreement']['passA_vs_passB_13']['alpha']:.3f} → "
          f"{res['agreement']['passA_vs_passC_13']['alpha']:.3f} / "
          f"555 セル見かけ基準比: {res['agreement']['delta_alpha_555baseline_to_passC']:.3f}）。")
    a("\nα の目安: ≥0.800 良好 / 0.667–0.800 暫定許容 / <0.667 結論に使用不可（Krippendorff 2004）。\n")

    a("## 3. 第2層（王権・儀礼・レガリア 15D）\n")
    a("| 系 | 主指標 | 帰無平均 ± SD | p | d | ノード平均 95%CI | 参考: 平均被説明率（帰無） | エッジ |")
    a("| :--- | ---: | ---: | ---: | ---: | :--- | :--- | ---: |")
    for k, v in res["layer2"].items():
        if k in ("per_node", "diagnostics", "seed_robustness", "param_robustness"):
            continue
        a(f"| {k} | {v['observed']:.3f} | {v['null_mean']:.3f} ± {v['null_sd']:.3f} | "
          f"{v['p_value']:.3f} | {v['effect_d']:.2f} | [{v['node_ci'][0]:.2f}, {v['node_ci'][1]:.2f}] | "
          f"{pct(v['explained'])}（{pct(v['expl_null_mean'])}） | {v['n_edges']} |")
    a("")
    a("主指標は校正済み類似度の最大値（calibrated 系）またはコサイン最大値（cosine 系）。"
      "帰無は親候補ベクトルの次元並べ替え 200 回。\n")

    for sect, lbl in (("3.1", "v18_calibrated"), ("3.2", "v18_cosine_reference")):
        blk = res["layer2"]["per_node"][lbl]
        a(f"### {sect} ノード別 FDR（{lbl}）\n")
        a(f"評価可能 {blk['n_evaluable']} / {blk['n_targets']} 話、FDR 有意 **{blk['n_sig_fdr']}** 話\n")
        a("| ID | 実測 | 帰無平均 | z | p | q | 有意 |")
        a("| :--- | ---: | ---: | ---: | ---: | ---: | :---: |")
        for r in blk["rows"][:8]:
            a(f"| {r['id']} | {r['observed']:.2f} | {r['null_mean']:.2f} | {r['z']:.2f} | "
              f"{r['p']:.3f} | {r['q']:.3f} | {'○' if r['sig_fdr'] else '—'} |")
        a("")

    dg = res["layer2"]["diagnostics"]
    a("### 3.3 診断（被説明率が使えない理由）\n")
    a(f"- 第2層プロファイルをもつ古事記話数: {dg['n_targets']}")
    a(f"- うち単一モチーフのみ: {dg['n_single_dim']} 話（平均被説明率 "
      f"{pct(dg['mean_explained_single_dim']) if dg['mean_explained_single_dim'] is not None else '—'}）"
      f" / 複数モチーフ: {pct(dg['mean_explained_multi_dim'])}")
    a(f"- 被説明率 0%（適格な親なし）: {dg['n_zero_explained']} 話 / "
      f"1 話あたり非零次元の平均 {dg['mean_nonzero_dims_per_target']:.2f}")
    a("\n単一モチーフの話は相手の同一次元が最大値を取れば被説明率 100% になるため、"
      "被説明率は飽和する。よって主エンドポイントには用いない。\n")

    a("### 3.4 シード頑健性（主系）\n")
    a("| シード | 実測 | 帰無平均 ± SD | p | d |")
    a("| ---: | ---: | ---: | ---: | ---: |")
    for r in res["layer2"]["seed_robustness"]:
        a(f"| {r['seed']} | {r['observed']:.3f} | {r['null_mean']:.3f} ± {r['null_sd']:.3f} | "
          f"{r['p_value']:.3f} | {r['effect_d']:.2f} |")
    a("")

    a("## 4. 第1層（75D・凍結 legacy）\n")
    a("| 系 | 主指標 | 帰無平均 ± SD | p | d | 参考: 平均被説明率（帰無） | エッジ |")
    a("| :--- | ---: | ---: | ---: | ---: | :--- | ---: |")
    for k, v in res["layer1"].items():
        a(f"| {k} | {v['observed']:.3f} | {v['null_mean']:.3f} ± {v['null_sd']:.3f} | "
          f"{v['p_value']:.3f} | {v['effect_d']:.2f} | "
          f"{pct(v['explained'])}（{pct(v['expl_null_mean'])}） | {v['n_edges']} |")
    a("")

    a("### 4.1 主エンドポイントのパラメータ頑健性（第2層・v18 主系）\n")
    a("| パラメータ | 値 | 主指標 | p | d |")
    a("| :--- | ---: | ---: | ---: | ---: |")
    for r in res["layer2"]["param_robustness"]:
        a(f"| {r['param']} | {r['value']} | {r['observed']:.3f} | {r['p_value']:.3f} | {r['effect_d']:.2f} |")
    a("")

    a("## 5. 感度分析（v18 データの平均被説明率）\n")
    a("| パラメータ | 値 | 平均被説明率 |")
    a("| :--- | ---: | ---: |")
    for s in res["sensitivity"]:
        a(f"| {s['param']} | {s['value']} | {pct(s['explained'])} |")
    a("")

    a("## 6. データ来歴（SHA256）\n")
    a("| ファイル | SHA256（先頭 16 桁） |")
    a("| :--- | :--- |")
    for k, v in res["meta"]["inputs"].items():
        a(f"| `{k}` | `{v[:16]}` |")
    a("")
    (OUT / "report.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
