# -*- coding: utf-8 -*-
"""v18 build.py -- アノテーション -> 特徴量行列（決定論的）"""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from pathlib import Path


def load_annotations(path):
    recs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def to_matrix(recs, vocab, index_ids):
    """ターゲット×モチーフの水準行列（未記載 = 0）。"""
    M = pd.DataFrame(0.0, index=index_ids, columns=vocab)
    for r in recs:
        if r["target"] not in M.index:
            continue
        for k, v in r["levels"].items():
            if k in M.columns:
                M.loc[r["target"], k] = float(v)
    return M


def dense_to_pairs(recs):
    """一致度計算用に (target, motif) -> level の辞書へ"""
    out = {}
    for r in recs:
        for k, v in r["levels"].items():
            out[(r["target"], k)] = int(v)
    for r in recs:  # 明示されていないセルを 0 として補完するかは呼び出し側で決める
        pass
    return out


def full_level_dict(recs, vocab):
    out = {}
    for r in recs:
        for k in vocab:
            out[(r["target"], k)] = int(r["levels"].get(k, 0))
    return out
