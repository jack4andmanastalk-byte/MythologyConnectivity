# -*- coding: utf-8 -*-
"""
append_only.py -- 事前登録と凍結データが「後から書き換えられていない」ことを git 履歴で検査する（枝 #14）。

背景（`docs/path_connectivity_validity_review_20261128_ja.md` §13.4 の 6・§16）:
  `docs/registry.md` の規律は「結果を見る前に枝を登録し、結果が出たら判定を追記する」。
  ところがこれまでは規律だけが機械の裏づけを持たず、誰かが既存の行を書き換えても
  `check_registry` も `verify_numbers` も通ってしまう（数値が整合していれば）。
  凍結データ `data/frozen/` も、上書き禁止がコメントにしか書かれていなかった。

  先方 `AIselfMySelf` の `tools/append_only_check.py` は「基底にあった行が同じバイト列で
  残るか」を見る。だが本リポジトリにそのまま適用すると**誤検出する**。実測（git 履歴 7 コミット）:

    * c106f98 で行 5–7 の「結果 / p / 効果量 / 判定」が `pending` → 実測値へ変わっている。
      これは**この登録簿の規則そのもの**（結果を追記する）なので、違反にしてはいけない。
    * cb39f8e では 9 列 → 10 列に列が増え、既存 4 行が 1 セルずつずれた。
      内容は無傷だが、**バイト列は全行が変わる**。バイトだけを見ると必ず落ちる。
    * 同じコミットで、既存行の**仮説セル**は変化していない（列名で対応づけると無傷）。
      以後 6 コミットのうち、事前登録セルが変わったものは 0 件。

  したがって検査は「行のバイト列」ではなく「意味の層」で行う。列名で対応づけ、
  2 種類のセルを別々に扱う。

    1. 事前登録セル（`#`, 日付, 枝 ID, 種別, 仮説, 主エンドポイント）
       ---- **登録後に 1 バイトも変わってはならない**
    2. 結果セル（結果, p, 効果量, 判定）
       ---- `pending` からの**前進は 1 回だけ**。一度確定した値は書き換えられない。
            意味のない差（空白・`**`）は変化と見なさない。

  行の追加（新しい枝）と並べ替えは許す。行の削除は違反。
  凍結データは内容（git blob）が同一であることを要求する（追加は許す）。

使い方:
  python3 src/append_only.py                      # 基底は origin/main（無ければ HEAD~1）
  python3 src/append_only.py --base HEAD~1        # 直前のコミットを基底にする
  python3 src/append_only.py --history            # 全履歴を走査（過去の違反も洗い出す）

終了コード: 0 違反なし / 1 違反あり / 2 基底が解決できない
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/analysis.json"

DEFAULTS = {
    "registry": "docs/registry.md",
    "frozen_glob": "data/frozen/*",
    "key_column": "#",
    # 登録時点で固定されるセル（この列は後から変えてはいけない）
    "frozen_columns": ["#", "日付", "枝 ID", "種別", "仮説", "主エンドポイント"],
    # 結果として後から埋まるセル（pending からの前進は 1 回だけ）
    "result_columns": ["結果", "p", "効果量", "判定"],
    "pending": "pending",
    # 結果が出る前の「まだ書いていない」印。pending と同じ扱いにする。
    # 実測: c106f98 で 判定 が「事前登録済み」から確定値へ変わっている（規則どおり）。
    "pending_markers": ["pending", "事前登録済み", "未実施", "未判定"],
}


def config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8")).get("append_only", {})
    except (OSError, json.JSONDecodeError):
        return {}


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def has_git() -> bool:
    return git("rev-parse", "--is-inside-work-tree").returncode == 0


def resolve_base(explicit: str | None) -> str | None:
    cands = [explicit] if explicit else ["origin/main", "HEAD~1"]
    for cand in cands:
        if git("rev-parse", "--verify", "--quiet", f"{cand}^{{commit}}").returncode == 0:
            return cand
    return None


# ------------------------------------------------------------------ 台帳の解析
def parse_table(text: str, key_column: str) -> tuple[list[str], dict[str, dict[str, str]]]:
    """Markdown の表を「列名 → 値」の辞書に読み直す。

    列数が合わない行は無視する（cb39f8e のような列追加の過渡状態で落ちないため）。
    """
    header: list[str] | None = None
    rows: dict[str, dict[str, str]] = {}
    for line in text.split("\n"):
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if all(re.fullmatch(r":?-+:?", c) for c in cells):
            continue
        if len(cells) != len(header):
            continue
        row = dict(zip(header, cells))
        key = row.get(key_column, "")
        if re.fullmatch(r"\d+", key):
            rows[key] = row
    return header or [], rows


def normalise(value: str) -> str:
    """意味のない差を落とす（空白・強調・全角/半角の空白）。"""
    return re.sub(r"\s+", "", value.replace("**", "").replace("*", "")).strip()


_EMPTY = {"", "—", "-", "–", "n/a", "na", "tbd", "未定", "未実施"}


def is_pending(value: str, cfg: dict) -> bool:
    markers = {m.lower() for m in cfg.get("pending_markers", [])}
    markers.add(cfg.get("pending", "pending").lower())
    return normalise(value).lower() in _EMPTY | markers


def compare_rows(old: dict[str, str], new: dict[str, str], cfg: dict) -> list[str]:
    """1 行を列名で比べる。違反の説明を返す（空なら無傷）。"""
    key = old.get(cfg["key_column"], "?")
    bad: list[str] = []
    frozen_cols = [c for c in cfg["frozen_columns"] if c in old and c in new]
    result_cols = [c for c in cfg["result_columns"] if c in old and c in new]

    for col in frozen_cols:
        if normalise(old[col]) != normalise(new[col]):
            bad.append(f"行{key}: 事前登録セル「{col}」が書き換えられている"
                       f"（登録後は不変であるべき）: {old[col]!r} -> {new[col]!r}")

    for col in result_cols:
        if normalise(old[col]) == normalise(new[col]):
            continue
        if not is_pending(old[col], cfg):
            bad.append(f"行{key}: 確定済みの「{col}」が書き換えられている"
                       f"（結果は 1 回だけ、pending から書く）: {old[col]!r} -> {new[col]!r}")
        if is_pending(new[col], cfg):
            bad.append(f"行{key}: 「{col}」が確定値から pending に戻っている: {old[col]!r} -> {new[col]!r}")
    return bad


def check_registry_between(base_text: str, cur_text: str, cfg: dict) -> list[str]:
    _, old_rows = parse_table(base_text, cfg["key_column"])
    _, new_rows = parse_table(cur_text, cfg["key_column"])
    bad: list[str] = []
    for key, old in sorted(old_rows.items(), key=lambda kv: int(kv[0])):
        if key not in new_rows:
            bad.append(f"行{key}: 登録済みの枝が消えている（{old.get('枝 ID', '?')}）")
            continue
        bad += compare_rows(old, new_rows[key], cfg)
    return bad


def check_registry_file(base: str, rel: str, cfg: dict) -> list[str]:
    run = git("show", f"{base}:{rel}")
    if run.returncode != 0:
        return []          # 基底に無い（新規追加）→ 検査不要
    path = ROOT / rel
    if not path.exists():
        return [f"{rel}: ファイルごと消えている"]
    return check_registry_between(run.stdout, path.read_text(encoding="utf-8"), cfg)


# ------------------------------------------------------------------ 凍結データ
def _dir_of(pattern: str) -> str:
    """glob から git に渡すディレクトリを取り出す（`data/frozen/*` -> `data/frozen`）.

    `git ls-tree` の pathspec はシェル風 glob を解さない（`:` プレフィックスが要る）。
    実測: `-- data/frozen/*` は 0 件、`-- data/frozen` は 3 件。パターンをそのまま
    渡すと検査が**黙って空振りする**ので、ディレクトリを渡して Python 側で絞る。
    """
    return pattern.rsplit("/", 1)[0] if "*" in pattern else pattern


def base_blobs(base: str, pattern: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in git("ls-tree", "-r", base, "--", _dir_of(pattern)).stdout.splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        # `ls-tree` は "100644 blob <sha>"、`ls-files -s` は "100644 <sha> 0"。
        # 位置で取ると取り違えるので、40 桁の 16 進を探す。
        sha = next((p for p in parts if re.fullmatch(r"[0-9a-f]{40}", p)), None)
        if sha and Path(path).match(pattern.rsplit("/", 1)[-1]):
            out[path] = sha
    return out


def current_blobs(pattern: str) -> dict[str, str]:
    """作業ツリーの内容から blob ハッシュを計算する。

    `git ls-files -s` は**インデックス**を読むので、`git add` していない変更を見逃す。
    実測: 凍結 CSV を 1 バイト書き換えただけでは検出できなかった（検査が空振り）。
    ローカルで「保存した瞬間に落ちる」方が価値が高いので、作業ツリーを読む。
    """
    directory = _dir_of(pattern)
    name = pattern.rsplit("/", 1)[-1]
    root = ROOT / directory
    if not root.exists():
        return {}
    files = sorted(p for p in root.glob(name) if p.is_file())
    if not files:
        return {}
    rels = [p.relative_to(ROOT).as_posix() for p in files]
    run = git("hash-object", "--", *rels)
    if run.returncode != 0:
        return {}
    return dict(zip(rels, run.stdout.split()))


def check_frozen(base: str, pattern: str) -> list[str]:
    old, new = base_blobs(base, pattern), current_blobs(pattern)
    bad: list[str] = []
    for path, sha in sorted(old.items()):
        if path not in new:
            bad.append(f"{path}: 基底にあった凍結データが消えている")
        elif new[path] != sha:
            bad.append(f"{path}: 凍結データが変更されている（上書き禁止）")
    return bad


# ------------------------------------------------------------------ 全履歴の走査
def history_violations(rel: str, cfg: dict) -> list[str]:
    """registry を変更した全コミットについて、直前の版からの変化を検査する。"""
    commits = git("log", "--format=%H", "--reverse", "--", rel).stdout.split()
    bad: list[str] = []
    for sha in commits:
        run = git("show", f"{sha}:{rel}")
        if run.returncode != 0:
            continue
        parent = git("rev-parse", "--verify", "--quiet", f"{sha}^")
        if parent.returncode != 0:
            continue
        prev = git("show", f"{parent.stdout.strip()}:{rel}")
        if prev.returncode != 0:
            continue
        width = int(cfg.get("history_subject_chars", 50))
        short = int(cfg.get("short_sha_chars", 7))
        subject = git("log", "-1", "--format=%s", sha).stdout.strip()[:width]
        for msg in check_registry_between(prev.stdout, run.stdout, cfg):
            bad.append(f"{sha[:short]} ({subject}) {msg}")
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="事前登録の不変性と凍結データの不変性を検査する")
    ap.add_argument("--base", help="基底リビジョン（既定: origin/main → HEAD~1 の順）")
    ap.add_argument("--history", action="store_true", help="全履歴を走査する")
    args = ap.parse_args(argv)

    if not has_git():
        print("[skip] git 管理下ではないため、不変性は検査しない")
        return 0

    cfg = {**DEFAULTS, **config()}

    if args.history:
        bad = history_violations(cfg["registry"], cfg)
        for line in bad:
            print(f"[NG] {line}")
        print(f"\n{'[NG]' if bad else '[OK]'} 全履歴の不変性: 違反 {len(bad)} 件"
              f"（{cfg['registry']} の全変更コミット）")
        return 1 if bad else 0

    base = resolve_base(args.base)
    if base is None:
        print("[NG] 基底リビジョンを解決できない（git fetch してから実行する）")
        return 2
    bad = check_registry_file(base, cfg["registry"], cfg)
    bad += check_frozen(base, cfg["frozen_glob"])

    for line in bad:
        print(f"[NG] {line}")
    if bad:
        print(f"\n[NG] 不変性: 違反 {len(bad)} 件（基底 {base}）")
        return 1
    print(f"[OK] 不変性: 事前登録セルは基底 {base} のまま不変、凍結データも同一"
          f"（{len(base_blobs(base, cfg['frozen_glob']))} 件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
