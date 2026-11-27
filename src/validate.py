# -*- coding: utf-8 -*-
"""v18 validate.py -- アノテーションファイルの機械検証（スキーマ・証拠・網羅性）"""
from __future__ import annotations
import json, sys
from pathlib import Path

REQUIRED = ["schema", "target", "grid", "annotator", "pass", "coded_at", "levels", "evidence"]
ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/analysis.json").read_text(encoding="utf-8"))
MIN_EV = int(CFG["validation"]["min_evidence_chars"])
LEVELS = {0, 1, 2, 3}


def load(path):
    recs = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"[NG] {path}:{i} JSON 構文エラー: {e}")
    return recs


def validate_file(path, vocab_map):
    recs = load(path)
    errs, warns = [], []
    seen = set()
    for r in recs:
        vocab = vocab_map(r.get("grid", ""))
        reference = str(r.get("annotator", "")).startswith("human-v17-legacy")
        miss = [k for k in REQUIRED if k not in r]
        if miss:
            errs.append(f"{r.get('target','?')}: 必須キー欠落 {miss}")
            continue
        key = (r["target"], r["pass"])
        if key in seen:
            errs.append(f"{key}: 重複レコード")
        seen.add(key)
        lv = r["levels"]
        if not isinstance(lv, dict):
            errs.append(f"{r['target']}: levels が辞書でない")
            continue
        for k, v in lv.items():
            if k not in vocab:
                errs.append(f"{r['target']}: 未知のコード {k}")
            if not isinstance(v, int) or v not in LEVELS:
                errs.append(f"{r['target']}.{k}: 水準値が 0-3 でない ({v})")
        ev = r.get("evidence", {})
        if not isinstance(ev, dict):
            errs.append(f"{r['target']}: evidence が辞書でない")
            continue
        for k, v in lv.items():
            if v > 0 and not reference:
                if k not in ev or not str(ev.get(k, "")).strip():
                    errs.append(f"{r['target']}.{k}: レベル {v} に証拠引用が無い")
                elif len(str(ev[k]).strip()) < MIN_EV:
                    warns.append(f"{r['target']}.{k}: 証拠が短すぎる")
        for k in ev:
            if k not in lv or lv.get(k, 0) == 0:
                warns.append(f"{r['target']}.{k}: 証拠はあるがレベル 0")
        if not reference and not r.get("blinded_to"):
            warns.append(f"{r['target']}: blinded_to が未記載")
    return recs, errs, warns


def main():
    root = Path(__file__).resolve().parents[1]
    cfgs = json.loads((root / "config/analysis.json").read_text(encoding="utf-8"))
    l2 = set(cfgs["layer2"]["vocab"])
    l1 = set(cfgs["layer1_audit"]["vocab"])

    def vocab_map(grid):
        return l1 if str(grid).startswith("L1") else l2

    all_ok = True
    for p in sorted((root / "annotations").glob("*.jsonl")):
        recs, errs, warns = validate_file(p, vocab_map)
        status = "OK" if not errs else "NG"
        print(f"[{status}] {p.name}: {len(recs)} レコード, エラー {len(errs)}, 警告 {len(warns)}")
        for e in errs[:20]:
            print("   ERR ", e)
        for w in warns[:10]:
            print("   WARN", w)
        all_ok &= not errs
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
