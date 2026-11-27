# -*- coding: utf-8 -*-
"""v18 stats.py -- 客観的検証のための統計ユーティリティ（外部依存なしで実装）"""
from __future__ import annotations
import numpy as np


def bh_fdr(pvals, alpha=0.05):
    """Benjamini-Hochberg。返り値 (棄却フラグ, q値)"""
    p = np.asarray(pvals, float)
    m = p.size
    order = np.argsort(p)
    ranked = p[order]
    q = ranked * m / np.arange(1, m + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    q = np.clip(q, 0, 1)
    out_q = np.empty(m)
    out_q[order] = q
    return out_q <= alpha, out_q


def bootstrap_ci(values, stat=np.mean, n_boot=10000, alpha=0.05, seed=42):
    """ノード単位ブートストラップ（平均などの 95% CI）"""
    v = np.asarray(values, float)
    if v.size == 0:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, v.size, size=(n_boot, v.size))
    stats = stat(v[idx], axis=1)
    return float(np.quantile(stats, alpha / 2)), float(np.quantile(stats, 1 - alpha / 2))


def krippendorff_alpha_ordinal(units, n_levels):
    """
    順序尺度の Krippendorff's alpha。
    units: list[list[int|None]]  各ユニット（＝セル）に対する複数評定者の値
    n_levels: 尺度の水準数（0..n_levels-1）
    """
    # 一致行列 O (n_levels x n_levels) を作る
    O = np.zeros((n_levels, n_levels))
    for u in units:
        vals = [v for v in u if v is not None]
        m = len(vals)
        if m < 2:
            continue
        for a in range(m):
            for b in range(m):
                if a != b:
                    O[vals[a], vals[b]] += 1.0 / (m - 1)
    n_total = O.sum()
    if n_total == 0:
        return float("nan")
    # 順序尺度の距離: 累積度数に基づく
    nc = O.sum(axis=1)                      # 各水準の周辺度数
    n_cum = np.cumsum(nc)
    delta = np.zeros((n_levels, n_levels))
    for c in range(n_levels):
        for k in range(n_levels):
            lo, hi = min(c, k), max(c, k)
            s = 0.0
            for g in range(lo, hi + 1):
                s += nc[g]
            delta[c, k] = (s - (nc[c] + nc[k]) / 2.0) ** 2
    Do = (O * delta).sum() / n_total
    e = np.outer(nc, nc)
    np.fill_diagonal(e, nc * (nc - 1))
    De = (e * delta).sum() / (n_total * (n_total - 1))
    if De == 0:
        return float("nan")
    return float(1 - Do / De)


def agreement_report(pass_a, pass_b, n_levels=4):
    """2 つのアノテーション辞書 {(target, motif): level} から α と完全一致率を出す。"""
    keys = sorted(set(pass_a) & set(pass_b))
    units = [[pass_a[k], pass_b[k]] for k in keys]
    alpha = krippendorff_alpha_ordinal(units, n_levels)
    exact = float(np.mean([1.0 if pass_a[k] == pass_b[k] else 0.0 for k in keys])) if keys else float("nan")
    within1 = float(np.mean([1.0 if abs(pass_a[k] - pass_b[k]) <= 1 else 0.0 for k in keys])) if keys else float("nan")
    return dict(n_cells=len(keys), alpha=alpha, exact_agreement=exact, within1_agreement=within1)


def proportion_gain(expl):
    """被説明率は飽和しやすいので、参考として 0/1 変換した保有率も出す（発見的指標）。"""
    e = np.asarray(expl, float)
    return float((e > 0).mean())
