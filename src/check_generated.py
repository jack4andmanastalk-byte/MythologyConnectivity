# -*- coding: utf-8 -*-
"""
check_generated.py -- 追跡下の生成物が「今のコードから再生成した値」と一致するかを検査する。

背景（`docs/path_connectivity_validity_review_20261128_ja.md` §13.4 #3）:
  `derived/` には git 管理下の生成物がある。手で直すと、コードと中身が食い違ったまま
  緑になる。`AIselfMySelf` の `--check-map`（生成物は手でマージせず再生成で解決する）と
  同じ規律を機械化する。

3 層で確かめる:

  1. **マニフェスト** `derived/generated_manifest.json` が、各生成物の sha256 と
     「それを生成したコードファイルの sha256」を記録している。生成物だけ変わって
     コードが変わっていなければ「手で編集された」と判定できる。
  2. **再生成の一致** 生成関数を呼び直し、値が追跡下のファイルと一致するか比べる
     （`--full` のときだけ。既定は速い 1 のみ）。
  3. **ずれの申告** 生成物に `manual_edits` として理由を書けば、1 の不一致を
     「承認済みの逸脱」として通す。理由の無い逸脱は通さない。

使い方:
    python3 src/check_generated.py            # 層 1（速い。CI と make all で回す）
    python3 src/check_generated.py --full     # 層 1 + 2（生成関数を再実行）
    python3 src/check_generated.py --write    # マニフェストを作り直す（生成物を更新したとき）

終了コード: 0 一致 / 1 不一致 / 2 判定できない（対象が無い等）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import analysis_io as IO  # noqa: E402

MANIFEST = ROOT / "derived/generated_manifest.json"
SCHEMA = "generated-manifest/1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_sha256(payload) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ registry of
# 生成物 -> (生成コード, 生成関数, 出力の組み立て方)
# 生成関数は「引数なしで呼ぶと追跡下ファイルと同じ JSON を返す」ものだけを登録する。
def _display_reproducibility() -> dict:
    import display_reproducibility as D
    _, payload = D.build()
    return payload


TARGETS = {
    "derived/display_reproducibility.json": dict(
        sources=["src/display_reproducibility.py", "src/analysis_io.py"],
        build=_display_reproducibility,
        note="ADR 0003 の表示台帳。src/display_reproducibility.py が生成する。",
    ),
}


def current_entry(rel: str, spec: dict) -> dict:
    return dict(
        sha256=sha256_file(ROOT / rel),
        sources={src: sha256_file(ROOT / src) for src in spec["sources"] if (ROOT / src).exists()},
        note=spec.get("note", ""),
    )


def build_manifest() -> dict:
    return dict(
        schema=SCHEMA,
        note=("生成物を手で編集していないことの証拠。`python3 src/check_generated.py --write` で更新する。"
              "生成物を更新したら、生成コードも同じ PR で更新すること。"),
        artifacts={rel: current_entry(rel, spec) for rel, spec in TARGETS.items()
                   if (ROOT / rel).exists()},
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="追跡下の生成物の鮮度を検査する")
    ap.add_argument("--full", action="store_true", help="生成関数を再実行して値まで比べる")
    ap.add_argument("--write", action="store_true", help="マニフェストを作り直す")
    args = ap.parse_args(argv)

    if args.write:
        manifest = build_manifest()
        IO.write_json_atomic(MANIFEST, manifest)
        print(f"[write] {MANIFEST.relative_to(ROOT)}: {len(manifest['artifacts'])} 件")
        return 0

    if not MANIFEST.exists():
        print(f"[NG] マニフェストが無い: {MANIFEST.relative_to(ROOT)}")
        print("     python3 src/check_generated.py --write で作る")
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    recorded = manifest.get("artifacts", {})

    problems: list[str] = []
    checked = 0
    manual = 0

    for rel, spec in TARGETS.items():
        path = ROOT / rel
        if not path.exists():
            problems.append(f"{rel}: 生成物が無い")
            continue
        entry = recorded.get(rel)
        if entry is None:
            problems.append(f"{rel}: マニフェストに未登録（--write で登録する）")
            continue
        checked += 1
        actual = sha256_file(path)

        # 層 3: 生成物自身が申告した手編集
        declared = {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            declared = payload.get("manual_edits") or {}
        except json.JSONDecodeError:
            problems.append(f"{rel}: JSON として読めない")
            continue
        if declared:
            manual += 1
            if actual != entry["sha256"]:
                # 申告があるので通すが、何が変わったかは出す
                print(f"[declared] {rel}: 手編集の申告あり（{declared.get('reason', '理由なし')}）")

        if actual != entry["sha256"] and not declared:
            problems.append(
                f"{rel}: 内容がマニフェストと違う（コード側の変更なら --write で更新、"
                f"手で直したなら manual_edits に理由を書く）")
            continue

        # 層 1b: 生成コードが変わったのに生成物が変わっていない -> 再生成忘れ
        for src, digest in entry.get("sources", {}).items():
            src_path = ROOT / src
            if not src_path.exists():
                problems.append(f"{rel}: 生成コード {src} が無い")
                continue
            if sha256_file(src_path) != digest:
                problems.append(
                    f"{rel}: 生成コード {src} が変わっている（生成物を再生成して --write する）")
                break

        # 層 2: 実際に生成し直して比べる
        if args.full and not declared:
            built = spec["build"]()
            if canonical_sha256(built) != canonical_sha256(payload):
                problems.append(f"{rel}: 再生成した値が追跡下のファイルと違う")

    if problems:
        print(f"[NG] 生成物の鮮度: {len(problems)} 件 / 検査 {checked} 件")
        for line in problems:
            print("  " + line)
        return 1
    print(f"[OK] 生成物の鮮度: 違反 0 件 / 検査 {checked} 件"
          f"{f' / 申告済みの手編集 {manual} 件' if manual else ''}"
          f"{' / 再生成一致も確認' if args.full else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
