# -*- coding: utf-8 -*-
"""
tests/test_interactive_html.py -- 人間確認用インタラクティブ HTML の回帰検査（標準ライブラリのみ）。

* docs/interactive/graph_network_atlas.html が存在し、実体のある自己完結文書であること
* 外部参照（script src / link / img / fetch / XHR / WebSocket / http(s) URL 等）が
  一切ないこと = ローカルの file:// で開いてもネットワーク要求が発生せず 404 になり得ない
* 埋め込み DATA が凍結データ（nodes_297.csv / derived 台帳）と整合すること
* エッジの参照整合（source/target がすべて実在ノード）が保たれていること
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
NODES_CSV = ROOT / "data/frozen/nodes_297.csv"
AUDIT_JSON = ROOT / "derived/html_embedded_v17_audit.json"

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
    "absolute http(s) URL": r"https?://",
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

    def test_no_external_references(self):
        """外部参照ゼロ = ローカル file:// 表示で 404 など通信エラーが発生し得ない。"""
        for label, pattern in EXTERNAL_PATTERNS.items():
            hits = re.findall(pattern, self.text)
            self.assertEqual(hits, [], f"外部参照が残っています: {label} ({len(hits)} 件)")

    def test_node_ids_match_frozen_csv(self):
        with open(NODES_CSV, encoding="utf-8") as stream:
            csv_ids = {row["id"] for row in csv.DictReader(stream)}
        html_ids = {n["id"] for n in self.data["nodes"]}
        self.assertEqual(html_ids, csv_ids, "HTML のノード ID が nodes_297.csv と一致しない")

    def test_gap_ledger_matches_derived_audit(self):
        audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
        audit_gap = {g["id"] for g in audit["gap_nodes"]}
        html_gap = {n["id"] for n in self.data["nodes"] if n.get("gap")}
        self.assertEqual(html_gap, audit_gap, "乖離台帳（gap ノード）が derived 台帳と一致しない")

    def test_edge_referential_integrity(self):
        """エッジの source/target はすべて実在ノード（参照切れ 0）。"""
        ids = {n["id"] for n in self.data["nodes"]}
        for layer, edges in self.data["edges"].items():
            self.assertGreater(len(edges), 0, f"{layer} 層のエッジが 0 本")
            for e in edges:
                self.assertIn(e["s"], ids, f"{layer} 層に参照切れ source: {e['s']}")
                self.assertIn(e["t"], ids, f"{layer} 層に参照切れ target: {e['t']}")
                self.assertNotEqual(e["s"], e["t"], f"{layer} 層に自己ループ: {e['s']}")

    def test_meta_counts_consistent(self):
        counts = self.data["meta"]["counts"]
        self.assertEqual(counts["nodes"], len(self.data["nodes"]))
        for layer in ("primary", "reference"):
            self.assertEqual(
                self.data["meta"]["layers"][layer]["edges"],
                len(self.data["edges"][layer]),
            )

    def test_template_placeholder_present(self):
        """テンプレートが再生成可能（__DATA_JSON__ を保持、未置換のままでは出荷しない）。"""
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
        self.assertIn("__DATA_JSON__", template)
        self.assertNotIn("__DATA_JSON__", self.text)


if __name__ == "__main__":
    unittest.main()
