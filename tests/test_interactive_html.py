# -*- coding: utf-8 -*-
"""
tests/test_interactive_html.py -- 人間確認用インタラクティブ HTML の回帰検査（標準ライブラリのみ）。

* docs/interactive/graph_network_atlas.html が v17 原本デザインを保持していること
* 外部参照（script src / link / img / fetch / XHR / WebSocket / http(s) URL 等）が
  ないこと = ローカルの file:// で開いてもネットワーク要求が発生せず 404 になり得ない
  （XML 名名空間 http://www.w3.org/2000/svg は通信しない識別子なので許可）
* 埋め込み DATA が原本グラフ（297 ノード / 597 エッジ）と凍結データ（nodes_297.csv /
  derived 台帳 / annotations）に整合すること
* v18 追記（表示監査・第 2 層評定・L1 再評定）が正しく注入されていること
* テンプレートが __DATA_JSON__ プレースホルダを保持し、再生成可能であること
"""
from __future__ import annotations

import csv
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "docs/interactive/graph_network_atlas.html"
TEMPLATE_PATH = ROOT / "src/interactive_atlas.template.html.tmpl"
EMBEDDED_PATH = ROOT / "derived/v17_html_embedded_data.json"
NODES_CSV = ROOT / "data/frozen/nodes_297.csv"
AUDIT_JSON = ROOT / "derived/html_embedded_v17_audit.json"
ANNOTATION_DIR = ROOT / "annotations"
VERIFICATION_DOC = ROOT / "docs/v17_network_attachment_verification_20261127_ja.md"

# 通信には使われない XML 名名空間識別子（createElementNS 用）は許可する
NAMESPACE_ALLOWLIST = ("http://www.w3.org/2000/svg", "http://www.w3.org/1999/xhtml")

# ネットワーク要求に繋がりうる構文の総ざらい（1 つでもあれば自己完結でない）
EXTERNAL_PATTERNS = {
    "script src": r"<script[^>]*\ssrc\s*=",
    "link href": r"<link[^>]*\shref\s*=",
    "img src": r"<img[^>]*\ssrc\s*=",
    "url(http)": r"url\(\s*[\"']?https?:",
    "fetch()": r"\bfetch\s*\(",
    "XMLHttpRequest": r"XMLHttpRequest",
    "WebSocket": r"WebSocket",
    "sendBeacon": r"sendBeacon",
    "EventSource": r"EventSource",
    "importScripts": r"importScripts",
    "@import": r"@import",
    "iframe": r"<iframe",
    "object/embed": r"<(object|embed)",
    "protocol-relative URL": r"(?:[\"'\s(=])//[a-zA-Z0-9-]+\.[a-z]{2,}",
}


def load_embedded_data(text: str) -> dict:
    marker = "const DATA = "
    idx = text.index(marker) + len(marker)
    data, _ = json.JSONDecoder().raw_decode(text[idx:])
    return data


class TestInteractiveHtml(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = HTML_PATH.read_text(encoding="utf-8")
        cls.data = load_embedded_data(cls.text)

    def test_html_exists_and_substantial(self):
        self.assertTrue(HTML_PATH.is_file(), "生成物 docs/interactive/graph_network_atlas.html が存在しない")
        self.assertGreater(HTML_PATH.stat().st_size, 100 * 1024, "生成物が小さすぎます（生成失敗の疑い）")
        self.assertTrue(self.text.startswith("<!DOCTYPE html>"))
        self.assertIn('<html lang="ja">', self.text)

    def test_original_design_preserved(self):
        """v17 原本デザイン（スイムレーン/地理/セクター/カタログ/インスペクタ）が保持されている。"""
        for marker in (
            'id="atlas-svg"', "スイムレーン", "地理座標", "セクター選択",
            "sector-drawer", "catalog-view", "detail-panel",
            "computeDynamicLayout", "computeSectorVisibilityAndBridges",
            "window.__v14Debug", "xWarp",
        ):
            self.assertIn(marker, self.text, f"原本デザインの部品が欠落: {marker}")

    def test_v18_annotations_injected(self):
        """v18 追記（表示監査・第 2 層評定・L1 再評定カード）が注入されている。"""
        for marker in ("表示監査（ADR 0003）", "第2層 評定 L2_R01-R15", "L1 信頼性 再評定", "v18Cards"):
            self.assertIn(marker, self.text, f"v18 追記が欠落: {marker}")

    def test_no_external_references(self):
        """外部参照ゼロ = ローカル file:// 表示で 404 など通信エラーが発生し得ない。"""
        scrubbed = self.text
        for ns in NAMESPACE_ALLOWLIST:
            scrubbed = scrubbed.replace(ns, "")
        for label, pattern in EXTERNAL_PATTERNS.items():
            hits = re.findall(pattern, scrubbed)
            self.assertEqual(hits, [], f"外部参照が残っています: {label} ({len(hits)} 件)")
        remaining = re.findall(r"https?://[^\s\"'<>)]+", scrubbed)
        self.assertEqual(remaining, [], f"想定外の URL 文字列: {remaining[:3]}")

    def test_node_ids_match_frozen_csv(self):
        with open(NODES_CSV, encoding="utf-8") as stream:
            csv_ids = {row["id"] for row in csv.DictReader(stream)}
        html_ids = {n["id"] for n in self.data["nodes"]}
        self.assertEqual(html_ids, csv_ids, "HTML のノード ID が nodes_297.csv と一致しない")

    def test_embedded_graph_counts(self):
        self.assertEqual(len(self.data["nodes"]), 297)
        self.assertEqual(len(self.data["edges"]), 597)
        self.assertEqual(len(self.data["lanes"]), 19)

    def test_gap_ledger_matches_derived_audit(self):
        audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
        audit_gap = {g["id"] for g in audit["gap_nodes"]}
        html_gap = {n["id"] for n in self.data["nodes"] if n.get("gap")}
        self.assertEqual(html_gap, audit_gap, "乖離台帳（gap ノード）が derived 台帳と一致しない")

    def test_annotations_match_jsonl(self):
        expect_l2 = 0
        expect_l1 = 0
        for path in sorted(ANNOTATION_DIR.glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                if str(rec.get("grid", "")).startswith("L1"):
                    expect_l1 += 1
                else:
                    expect_l2 += 1
        got_l2 = sum(len(n.get("l2", [])) for n in self.data["nodes"])
        got_l1 = sum(len(n.get("l1audit", [])) for n in self.data["nodes"])
        self.assertEqual(got_l2, expect_l2, "第 2 層評定レコード数が annotations/ と一致しない")
        self.assertEqual(got_l1, expect_l1, "L1 再評定レコード数が annotations/ と一致しない")
        self.assertGreater(got_l2, 0)
        self.assertGreater(got_l1, 0)

    def test_edge_referential_integrity(self):
        """エッジの source/target はすべて実在ノード（参照切れ 0・自己ループ 0）。"""
        ids = {n["id"] for n in self.data["nodes"]}
        for e in self.data["edges"]:
            self.assertIn(e["source"], ids, f"参照切れ source: {e['source']}")
            self.assertIn(e["target"], ids, f"参照切れ target: {e['target']}")
            self.assertNotEqual(e["source"], e["target"], f"自己ループ: {e['source']}")

    def test_meta_counts_consistent(self):
        counts = self.data["v18meta"]["counts"]
        self.assertEqual(counts["nodes"], len(self.data["nodes"]))
        self.assertEqual(counts["edges"], len(self.data["edges"]))
        self.assertEqual(counts["gap_nodes"], sum(1 for n in self.data["nodes"] if n.get("gap")))

    def test_source_provenance_recorded(self):
        """derived JSON の出所 SHA-256 が検証報告書の目録ハッシュと一致すること。"""
        embedded = json.loads(EMBEDDED_PATH.read_text(encoding="utf-8"))
        sha = embedded["__source"]["sha256"]
        self.assertIn(sha, VERIFICATION_DOC.read_text(encoding="utf-8"),
                      "抽出元 SHA-256 が検証報告書（ZIP 目録）に存在しない")
        self.assertEqual(self.data["v18meta"]["source_html_sha256"], sha)

    def test_template_placeholder_present(self):
        """テンプレートが再生成可能（__DATA_JSON__ を保持、未置換のままでは出荷しない）。"""
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
        self.assertIn("__DATA_JSON__", template)
        self.assertNotIn("__DATA_JSON__", self.text)


if __name__ == "__main__":
    unittest.main()
