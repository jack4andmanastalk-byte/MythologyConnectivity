# -*- coding: utf-8 -*-
"""
v18 engine.py -- 決定論的剥離エンジン（設定駆動・手書き定数を排除）

v17 との違い:
  * 変換ペア（TRANS_PAIRS: 手書き重み 0.10-0.15）を既定で使わない（use_transforms=False）。
  * 類似度を「校正済み類似度 (calibrated)」で測れる。
      各ターゲットにつき、時空間的に適格な親候補集合上でのコサイン分布 (mu, sigma) を
      実測し、z = (cos - mu) / sigma を類似度とする。
      これにより「どのペアでも高く出る」飽和（v17 の 15D 問題）を除去する。
  * しきい値・親数・距離上限はすべて Config で明示（既定値は config/analysis.json）。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
import numpy as np
import pandas as pd

EARTH_R = 6371.0


@dataclass
class EngineConfig:
    # 数値はすべて config/analysis.json から注入する（既定値を持たせない = 手書き定数を残さない）
    mode: str = "calibrated"          # "calibrated" | "cosine"
    z_thresh: float | None = None     # calibrated モードの親採用しきい値
    score_thresh: float | None = None  # cosine モードのスコアしきい値
    dot_thresh: float | None = None   # cosine モードの内積しきい値
    max_parents: int | None = None
    proto_dist_km: float | None = None  # dt < dt_split のときの距離上限
    max_dist_km: float | None = None  # dt >= dt_split のときの距離上限
    dt_split: int | None = None
    use_transforms: bool = False
    transform_pairs: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def haversine_matrix(lat, lon):
    lat_r = np.radians(np.asarray(lat, float))[:, None]
    lon_r = np.radians(np.asarray(lon, float))[:, None]
    a = (np.sin((lat_r - lat_r.T) / 2) ** 2
         + np.cos(lat_r) * np.cos(lat_r.T) * np.sin((lon_r - lon_r.T) / 2) ** 2)
    return EARTH_R * 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def build_eligibility(nodes: pd.DataFrame, cfg: EngineConfig):
    """親候補の時空間マスク（ターゲット×候補の bool 行列）と候補順序を返す。"""
    ids = nodes["id"].tolist()
    t = nodes["t_eff"].values.astype(int)
    D = haversine_matrix(nodes["lat"].values, nodes["lon"].values)
    n = len(nodes)
    order = sorted(range(n), key=lambda i: (int(t[i]), ids[i]))
    pos = {idx: p for p, idx in enumerate(order)}
    ok = np.zeros((n, n), dtype=bool)
    for j in range(n):
        for i in range(n):
            if i == j or pos[i] >= pos[j]:
                continue
            dt = int(t[j] - t[i])
            cap = cfg.proto_dist_km if dt < cfg.dt_split else cfg.max_dist_km
            if D[i, j] <= cap:
                ok[j, i] = True
    return ok, D


def _unit(V):
    nrm = np.linalg.norm(V, axis=1, keepdims=True)
    return np.divide(V, np.maximum(nrm, 1e-12)), nrm.ravel()


def calibrate(Vn, elig, j):
    """ターゲット j の適格候補集合上でのコサイン分布から z 値を返す。"""
    cand = np.where(elig[j])[0]
    if cand.size < 3:
        return cand, None
    cos = Vn[cand] @ Vn[j]
    mu, sd = float(cos.mean()), float(cos.std())
    if sd < 1e-9:
        return cand, None
    return cand, (cos - mu) / sd


def peel(nodes: pd.DataFrame, V: np.ndarray, cfg: EngineConfig):
    """残余剥離 DAG。返り値: (edges DataFrame, explained np.array, parents list[list[int]])"""
    need = ["max_parents", "proto_dist_km", "max_dist_km", "dt_split"]
    need += ["z_thresh"] if cfg.mode == "calibrated" else ["score_thresh", "dot_thresh"]
    missing = [f for f in need if getattr(cfg, f) is None]
    if missing:
        raise ValueError("EngineConfig 未設定: " + ", ".join(missing) +
                         "（config/analysis.json から注入すること）")
    V = np.asarray(V, float)
    Vn, nrm = _unit(V)
    n, dim = V.shape
    elig, D = build_eligibility(nodes, cfg)
    ids = nodes["id"].tolist()

    trans = None
    if cfg.use_transforms and cfg.transform_pairs:
        trans = np.eye(dim)
        idx = {f: k for k, f in enumerate(nodes.attrs.get("feats", []))}
        for a, b, w, _tag in cfg.transform_pairs:
            if a in idx and b in idx:
                trans[idx[a], idx[b]] = max(trans[idx[a], idx[b]], w)
                trans[idx[b], idx[a]] = max(trans[idx[b], idx[a]], w)

    explained = np.zeros(n)
    parents = [[] for _ in range(n)]
    topscore = np.full(n, np.nan)
    rows = []

    for j in range(n):
        if nrm[j] < 1e-8:
            continue
        cand, z = calibrate(Vn, elig, j) if cfg.mode == "calibrated" else (np.where(elig[j])[0], None)
        if cand.size == 0:
            topscore[j] = np.nan
            continue
        dot_all = Vn[cand] @ Vn[j]
        if cfg.mode == "calibrated":
            if z is None:          # 候補集合内でコサインが一定 → 情報なし。評価対象外（実測・帰無で同一扱い）
                topscore[j] = np.nan
                continue
            topscore[j] = float(np.max(z))
            score = z.copy()
            keep = np.where(score >= cfg.z_thresh)[0]
        else:
            topscore[j] = float(np.max(dot_all))
            score = dot_all.copy()
            keep = np.where((score >= cfg.score_thresh) & (dot_all >= cfg.dot_thresh))[0]
        if keep.size == 0:
            continue

        v_rem = V[j].copy()
        tgt2 = float(np.linalg.norm(V[j]) ** 2)
        chosen = []
        for step in range(cfg.max_parents):
            if np.linalg.norm(v_rem) < 0.25 or keep.size == 0:
                break
            u = v_rem / max(1e-12, float(np.linalg.norm(v_rem)))
            dots = Vn[cand[keep]] @ u
            k = int(np.argmax(dots))
            if cfg.mode == "cosine" and dots[k] < cfg.dot_thresh:
                break
            if cfg.mode == "calibrated" and dots[k] <= 0:
                break
            p = int(cand[keep[k]])
            w = float(dots[k])
            rows.append({
                "source": ids[p], "target": ids[j],
                "dt_years": int(nodes.t_eff.iloc[j] - nodes.t_eff.iloc[p]),
                "dist_km": round(float(D[p, j]), 1),
                "similarity": round(float(score[keep[k]]), 4),
                "cosine": round(float(dot_all[keep[k]]), 4),
                "step": step + 1,
            })
            chosen.append(p)
            v_rem = np.maximum(0.0, v_rem - w * Vn[p])
            keep = np.delete(keep, k)
        if chosen:
            parents[j] = chosen
            explained[j] = max(0.0, min(1.0, 1.0 - float(np.linalg.norm(v_rem) ** 2) / max(1e-12, tgt2)))
    return pd.DataFrame(rows), explained, parents, topscore


def _feature_shuffle(V, pool, rng):
    """プール内の各ノードの次元を並べ替える（水準の多重集合は保存、モチーフの対応のみ破壊）。"""
    Vp = V.copy()
    for i in pool:
        if np.linalg.norm(V[i]) > 0:
            Vp[i] = V[i][rng.permutation(V.shape[1])]
    return Vp


def run_with_null(nodes, V, cfg: EngineConfig, target_mask, pool_mask, n_perm=200, seed=42,
                  null_mode="feature_shuffle"):
    """
    主エンドポイント = ターゲットごとの「最良親との校正済み類似度 (max z)」の平均。
    帰無モデル = プール（親候補）の特徴ベクトルの次元を並べ替える（意味的対応を破壊）。
                 プール内の個体を入れ替えるだけでは多重集合が保存され情報量が変わらないため用いない。
    """
    edges, expl, parents, top = peel(nodes, V, cfg)
    obs_top = float(np.nanmean(top[target_mask]))
    obs_exp = float(expl[target_mask].mean())
    pool = np.where(pool_mask)[0]
    rng = np.random.default_rng(seed)
    null_top = np.empty(n_perm)
    null_exp = np.empty(n_perm)
    for k in range(n_perm):
        Vp = _feature_shuffle(V, pool, rng) if null_mode == "feature_shuffle" else V.copy()
        if null_mode == "pool_permute":
            Vp[pool] = V[rng.permutation(pool)]
        _, e_k, _, t_k = peel(nodes, Vp, cfg)
        null_top[k] = float(np.nanmean(t_k[target_mask]))
        null_exp[k] = float(e_k[target_mask].mean())
    mu, sd = float(null_top.mean()), float(null_top.std(ddof=1))
    p = float((np.sum(null_top >= obs_top) + 1) / (n_perm + 1))
    mue, sde = float(null_exp.mean()), float(null_exp.std(ddof=1))
    pe = float((np.sum(null_exp >= obs_exp) + 1) / (n_perm + 1))
    return dict(observed=obs_top, null_mean=mu, null_sd=sd, p_value=p,
                effect_d=(obs_top - mu) / sd if sd > 0 else 0.0,
                explained=obs_exp, expl_null_mean=mue, expl_null_sd=sde,
                expl_p_value=pe, null_top=null_top, null_expl=null_exp,
                n_edges=int(len(edges)), expl_node=expl, top_node=top,
                parents=parents, edges=edges)
