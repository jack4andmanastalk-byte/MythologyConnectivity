# -*- coding: utf-8 -*-
"""
new_id.py -- 並列ワーカーが衝突しない ID を採番する（枝 #14、§13.4 の 5）。

背景:
  §11 で実測したとおり、同じファイルに書く並列ワーカーは互いを壊す。ID も同じで、
  連番（`TASK-1`, `TASK-2`, …）は**必ず衝突する**。枝 #8〜#13 の ID は固定文字列なので
  今は困っていないが、`outputs/` をシャード化すると（§13.4 の 1）必要になる。

  先方 `AIselfMySelf` の `tools/new_id.py` は `PREFIX-YYYYMMDD-xxxxxx`（6 桁乱数）を
  採番し、**全シャードの和集合と照合して衝突を避ける**。ここでも同じ形にするが、
  乱数は `secrets` を使い、**照合は「採番のたびに全シャードを読み直す」**。

  "全シャードの和集合" が要点である。1 つのファイルだけ見て空き番号を探すと、
  別シャードに既にある ID と衝突する（並列で書き込むと特に）。

使い方:
  python3 src/new_id.py                          # TASK-20261128-xxxxxx
  python3 src/new_id.py --prefix BRANCH          # BRANCH-...
  python3 src/new_id.py --count 3                # 3 個まとめて
  python3 src/new_id.py --check TASK-20261128-ab12cd   # 既存と衝突しないか検査

終了コード: 0 成功 / 1 照合回数を使い切った（= 乱数空間が足りない）/ 2 設定不備
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/analysis.json"
DEFAULTS = {
    "default_prefix": "TASK",
    "shards": ["config/work_queue.json", "docs/registry.md"],
    "length": 6,
    "attempts": 8,
}

_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"   # 36 進 6 桁 = 約 21.8 億通り


def config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8")).get("ids", {})
    except (OSError, json.JSONDecodeError):
        return {}


def existing_ids(shards: list[str]) -> set[str]:
    """全シャードから「ID らしき文字列」を集める。

    シャードは JSON（`id` フィールド）と Markdown（表の「枝 ID」列）の 2 種類がある。
    どちらも**中身を解釈せずに文字列として**拾う（壊れたシャードでも落ちない）。
    """
    found: set[str] = set()
    for rel in shards:
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if rel.endswith(".json"):
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                found.update(re.findall(r'"id"\s*:\s*"([^"]+)"', text))
                continue
            tasks = data.get("tasks", data) if isinstance(data, dict) else data
            if isinstance(tasks, list):
                for item in tasks:
                    if isinstance(item, dict) and isinstance(item.get("id"), str):
                        found.add(item["id"])
        else:
            # Markdown の表: 「枝 ID」列（3 列目）
            for line in text.splitlines():
                if not line.strip().startswith("|"):
                    continue
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) >= 3 and re.fullmatch(r"\d+", cells[0]):
                    found.add(cells[2])
    return found


def make_id(prefix: str, length: int, taken: set[str], today: str) -> str:
    for _ in range(10_000):
        suffix = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        candidate = f"{prefix}-{today}-{suffix}"
        if candidate not in taken:
            return candidate
    raise RuntimeError("乱数空間が尽きた（length を増やす）")


def main(argv: list[str] | None = None) -> int:
    cfg = {**DEFAULTS, **config()}
    ap = argparse.ArgumentParser(description="衝突しない ID を採番する")
    ap.add_argument("--prefix", default=cfg["default_prefix"])
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--length", type=int, default=cfg["length"])
    ap.add_argument("--date", default=None, help="YYYYMMDD（テスト用。既定は今日）")
    ap.add_argument("--check", metavar="ID", help="既存 ID と衝突しないか検査する")
    args = ap.parse_args(argv)

    if args.length < 4:
        print("[NG] length は 4 以上にする（短いと衝突確率が上がる）")
        return 2

    today = args.date or dt.date.today().strftime("%Y%m%d")
    taken = existing_ids(cfg["shards"])

    if args.check:
        clash = args.check in taken
        print(f"[{'NG' if clash else 'OK'}] {args.check}: "
              f"{'既存 ID と衝突する' if clash else '衝突しない'}"
              f"（照合したシャード {len(cfg['shards'])} 件 / 既存 {len(taken)} 件）")
        return 1 if clash else 0

    out: list[str] = []
    for _ in range(args.count):
        try:
            new = make_id(args.prefix, args.length, taken | set(out), today)
        except RuntimeError as exc:
            print(f"[NG] {exc}")
            return 1
        out.append(new)

    for value in out:
        print(value)
    if len(out) > 1:
        print(f"[OK] {len(out)} 件を採番（既存 {len(taken)} 件と照合）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
