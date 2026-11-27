# はじめに（このハーネスの使い方）

比較神話学の検証プログラムを、**リポジトリをハーネスとして**継続するための一式です。
新しいチャットでは `PROMPT.md` の内容を最初のメッセージとして送ってください。

## 3 つの入口

| 目的 | 読むファイル |
| :--- | :--- |
| 何をどう検証したか（結果） | `docs/v18_method_and_results.md` |
| なぜリポジトリで運用するか（判断） | `docs/adr/0001-repository-as-harness.md` |
| 多モデル並列運用の限界と規則 | `docs/adr/0002-long-run-independent-review.md` |
| 試行の登録簿（全試行・否定的結果も） | `docs/registry.md` |
| 前段の成果物（v17 検証レポート） | `docs/v17_integrity_verification_report.md` |
| 事前登録（判定基準を結果前に固定） | `docs/prereg/20261127-layer2-verification.md` |

## 最初の 6 コマンド

```bash
unzip arena_harness_v18.zip && cd arena_harness_v18
make validate    # スキーマ・証拠・重複
make audit       # コード内の解析定数ゼロ監査
make sim         # 多モデル運用の誤差訂正能力（ADR 0002 の数値）
make run         # 全解析＋ネットワーク検証状態を記録（約 85 秒）
make doc         # 本文の数値と機械出力の照合（68 項目）
make determ      # 2 回実行して生成物が一致することの確認（約 150 秒）
```

依存は numpy と pandas のみ。外部 API・ネットワーク呼び出しはありません。v17原本が無い場合、`make run` は他の解析を続け、ネットワーク全件検証を `unavailable` として記録します。CI・パイプラインの成功だけで全件検証済みと判断せず、`outputs/network_verification_status.json` の `status` と `unverified_scope` を確認してください。単独の `make network` は `passed` の場合のみ終了コード0です。

## ディレクトリ

| パス | 中身 |
| :--- | :--- |
| `config/analysis.json` | 唯一の設定源（語彙・エンジン・検定・判定基準・運用パラメータ） |
| `src/` | 決定論的パイプライン（engine / stats / validate / build / run_all） |
| `src/verify_network.py` | 埋め込みグラフ 297 ノード / 597 エッジの全件検証。実行状態は `outputs/network_verification_status.json` |
| `src/verify_doc.py` | 手書き本文の数値と機械出力の照合（未検証状態も表示） |
| `src/work_scheduler.py` | 共有 workspace 内の並列作業を原子的に claim する scheduler |
| `config/work_queue.json` | 優先度・依存関係・必要ファイルを含む作業キュー |
| `src/audit_no_hardcode.py` | コード内に解析定数が残っていないことの AST 監査 |
| `src/check_prereg.py` | 事前登録が結果より先にコミットされたことの確認 |
| `src/check_determinism.py` | 同一入力 2 回で生成物が一致することの確認 |
| `src/sim_swarm_review.py` | 多モデル並列レビューの誤差訂正能力の評価 |
| `data/frozen/` | 凍結入力（297 ノード、75 次元行列 281×75）。**上書き禁止** |
| `annotations/` | 評定データ（pass A / pass B / アンカー / L1 監査 / v17 legacy）。原文引用つき |
| `schema/` | アノテーションの JSON Schema |
| `docs/` | 本文・ADR・事前登録・登録簿 |
| `outputs/` | 生成物のスナップショット。**リポジトリでは追跡しない**（`make run` で再生成） |
| `vendor/` | v17 パッケージ（ネットワーク検証に使用。無くても他は動く） |
| `v18_harness.bundle` | git 履歴（6 コミット）。`git clone` で復元できる |
| `ZIP_INFO.txt` | この zip の作成年月日・先頭コミット・全ファイルのハッシュ |

## 生成物の見どころ

| ファイル | 内容 |
| :--- | :--- |
| `outputs/results.json` | 全数値・設定・入力ハッシュ（これが正） |
| `outputs/report.md` | 第 2 層検証の自動生成レポート |
| `outputs/network_verification_status.json` | `passed` / `failed` / `unavailable` と未検証範囲を記録。CI成功とは別に確認する |
| `outputs/network_verification.md` | 埋め込みグラフ全件検証（実行可能な場合） |
| `outputs/network_edge_audit.csv` | エッジ 597 行の判定台帳（全件検証完了時） |
| `outputs/network_node_audit.csv` | ノード 297 行の判定台帳（表示値・再計算値・出所、全件検証完了時） |
| `outputs/swarm_sim.md` | 多モデル運用の誤差訂正能力（ADR 0002 の根拠） |
| `outputs/manifest.sha256` | 生成物のハッシュ一覧 |

## 触るときの約束

1. `outputs/` はコミットしない。
2. `data/frozen/` は上書きしない（変更するなら `frozen_v2/` を切る）。
3. 新しい仮説は `docs/registry.md` に**先に**登録する。
4. 本文の数値は `src/verify_doc.py` の照合対象に入れる。
5. 確定した結論を後から動かさない（動かすなら新しい枝として登録）。

## 複数チャットで並列作業する場合

`config/work_queue.json` にあるタスクを共有 state で claim します。チャットごとに `python3 src/work_scheduler.py worker-id` で一意 ID を発行し、`python3 src/work_scheduler.py claim-next --worker <ID>` で担当を取得してください。状態表示は `make work-status`。期限付き claim は heartbeat で延長し、完了時は claim token を添えて complete、作業を渡す場合は release します。詳しい排他方式・状態ファイル・復旧手順は `docs/parallel_work_scheduler.md` を参照してください。

この scheduler が排他を保証するのは、全チャットが同じ共有ファイルシステム上の同じ state path を使う場合のみです。別 sandbox / clone 間は調整しません。
