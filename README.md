# v18 — 古事記神話とユーラシア神話の対応関係：再現可能な検証パイプライン

v17 パッケージ（`kojiki_mythology_v17_local`）の手法を「手書きの結論」から
「設定ファイル駆動・決定論的・外部 API 非依存」の実装へ作り直したものです。

* 解析上のしきい値・重み・件数は **すべて** `config/analysis.json` にあります（コード内に既定値なし）。
* LLM による評定は **このチャット内で実行済み**で、結果は `annotations/*.jsonl` に原文引用つきで保存されています。
  実行時に外部モデル・外部 API・ネットワークを一切呼びません。
* 出力は `outputs/report.md`（自動生成レポート）、`outputs/results.json`（全数値）、
  `outputs/manifest.sha256`（成果物のハッシュ）です。

## クイックスタート

```bash
cd v18
python3 src/run_all.py        # 検証 → 定数監査 → 全解析 → ネットワーク全件検証 → レポート → マニフェスト（約 85 秒）
```

依存: Python 3.13 /numpy / pandas（scipy・sklearn・ネットワーク不要）

## 構成

| パス | 内容 |
| :--- | :--- |
| `config/analysis.json` | 唯一の設定源（語彙・エンジン・検定・判定基準） |
| `src/engine.py` | 決定論的剥離エンジン（校正済み類似度 / コサイン、次元シャッフル帰無） |
| `src/stats.py` | BH-FDR、ブートストラップ CI、Krippendorff α（順序） |
| `src/validate.py` | アノテーションのスキーマ・証拠・重複検査（`schema/annotation.schema.json` に準拠） |
| `src/audit_no_hardcode.py` | 数値リテラルの AST 監査。解析定数がコードに漏れていないことを機械的に確認 |
| `src/build.py` | 行列の組み立て |
| `src/verify_network.py` | v17 HTML 埋め込みグラフ（297 ノード / 597 エッジ）の全件検証。構造・層構成・数値再現・全ノード統計 |
| `src/verify_doc.py` | 手書き文書の数値が `results.json` / `network_checks.json` と一致するかを機械照合（不一致なら exit 1） |
| `src/run_all.py` | 上記を順に実行し、結果・レポート・マニフェストを生成 |
| `annotations/` | 評定データ（pass A / pass B / アンカー / L1 監査 / v17 legacy 変換） |
| `data/frozen/` | 凍結入力（297 ノード、v16 75D 行列、L1 75D 行列） |
| `outputs/` | 生成物（結果・レポート・行列・監査・ネットワーク検証・全件台帳・マニフェスト） |
| `docs/v18_method_and_results.md` | 方法と結果の本文（日本語） |

## 検証コマンド

```bash
python3 src/validate.py            # アノテーション検証。問題があれば exit 1
python3 src/audit_no_hardcode.py   # 手書き定数監査。違反があれば exit 1
python3 src/verify_network.py      # 埋め込みグラフ全件の検証。outputs/network_verification.md を生成
python3 src/verify_doc.py          # 本文の数値と results.json / network_checks.json の照合
```

`run_all.py` はこの 2 つを先に実行し、どちらかが失敗したら解析を中止します。

## リポジトリとしての運用（ハーネス）

このディレクトリはそのまま git リポジトリとして使える（初期コミット済み）。

```bash
make all      # validate → audit → 全解析（ネットワーク全件検証を含む）→ 文書照合
make determ   # 2 回実行して生成物が一致することを確認（約 150 秒）
make network  # 埋め込みグラフ全件の検証だけを再実行
```

* `outputs/` は追跡しない（CI が artifacts として保存する）。
* `docs/prereg/` の事前登録は**結果より前**にコミットする。その順序は
  `src/check_prereg.py` が git 履歴で検査し、CI の最初のゲートになる。
* 運用方針とその限界は `docs/adr/0001-repository-as-harness.md` に書いてある。

## 決定性

同一環境で 2 回実行したとき、`results.json`（時刻・実行時間を除く）と
`matrix_l2_v18_passA.csv` は完全に一致します（乱数はすべてシード固定）。
