# v18 — 古事記神話とユーラシア神話の対応関係：再現可能な検証パイプライン

> 新しいチャットで作業を続ける場合は `START_HERE.md`（構成）と `PROMPT.md`（開始用プロンプト）を参照。

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
python3 src/run_all.py        # 検証 → 定数監査 → 全解析 → ネットワーク検証状態 → レポート → マニフェスト（約 85 秒）
```

依存: Python 3.11+ / numpy / pandas（scipy・sklearn・matplotlib・ネットワーク不要）

## 構成

| パス | 内容 |
| :--- | :--- |
| `config/analysis.json` | 唯一の設定源（語彙・エンジン・検定・判定基準） |
| `src/check_prereg.py` | 事前登録が設定変更より前にコミットされたことを git 履歴で検査 |
| `src/check_registry.py` | `docs/registry.md` の枝数から Holm しきい値と必要置換回数を算出し、`n_perm` 不足なら exit 1 |
| `tests/test_check_registry.py` | 登録簿パース・Holm要件・文書宣言の回帰テスト（`make test`） |
| `src/engine.py` | 決定論的剥離エンジン（校正済み類似度 / コサイン、次元シャッフル帰無） |
| `src/stats.py` | BH-FDR、ブートストラップ CI、Krippendorff α（順序） |
| `src/validate.py` | アノテーションのスキーマ・証拠・重複検査（`schema/annotation.schema.json` に準拠） |
| `src/audit_no_hardcode.py` | 数値リテラルの AST 監査。解析定数がコードに漏れていないことを機械的に確認 |
| `src/build.py` | 行列の組み立て |
| `src/verify_network.py` | v17 HTML 埋め込みグラフ（297 ノード / 597 エッジ）の全件検証。構造・層構成・数値再現・全ノード統計。状態は `network_verification_status.json` に `passed` / `failed` / `unavailable` で記録 |
| `src/verify_doc.py` | 手書き文書の数値が `results.json` / `network_checks.json` と一致するかを機械照合（不一致なら exit 1）。ネットワーク未検証状態も表示 |
| `src/work_scheduler.py` | 共有ワークスペース内の並列チャット向け atomic claim・lease・heartbeat・complete/release |
| `config/work_queue.json` | 優先度・依存関係・必要パスつき作業キュー |
| `src/run_all.py` | 上記を順に実行し、結果・レポート・マニフェストを生成 |
| `src/build_interactive_html.py` | v17 原本デザインに最新データを統合して確認用 HTML を再生成（`make interactive`／`--extract` で原本 DATA 抽出） |
| `src/interactive_atlas.template.html.tmpl` | 上記 HTML のテンプレート（v17 原本 UI シェル＋v18 追記部） |
| `src/extract_world_map.mjs` | Natural Earth 1:110m（world-atlas / パブリックドメイン）から地理モード背景地図 `derived/world_land.json` を生成（開発時のみ） |
| `docs/interactive/graph_network_atlas.html` | グラフネットワーク人間確認用インタラクティブ HTML（生成物・追跡対象の例外） |
| `docs/interactive_graph_html_ja.md` | 同 HTML のデザイン系譜・データ出所・検証・再生成手順 |
| `annotations/` | 評定データ（pass A / pass B / 中立操作定義 pass C / アンカー / L1 監査 / v17 legacy 変換） |
| `data/trade_routes.json` | 交易路オーバーレイ用データ（交易史・考古学遺物に基づく中継交易ルートの近似・表示専用） |
| `data/frozen/` | 凍結入力（297 ノード、v16 75D 行列、L1 75D 行列） |
| `derived/` | 凍結 HTML 297 ノード出所・21 話乖離台帳（`html_embedded_v17_audit.json`） |
| `outputs/` | 生成物（結果・レポート・行列・監査・ネットワーク検証・全件台帳・マニフェスト） |
| `docs/v18_method_and_results.md` | 方法と結果の本文（日本語・§11 v18.1 追補含む） |
| `docs/peer_review_summary_ja.md` | 査読用サマリ（日本語 2 ページ要約、`verify_doc.py` 照合済み） |
| `docs/peer_review_summary_en.md` | 査読用サマリ（英語要約、`verify_doc.py` 照合済み） |
| `docs/registry.md` | 事前登録台帳（全 14 枝・Holm 補正・結果一覧） |
| `docs/adr/` | 設計判断記録（ADR 0001〜0003） |
| `docs/github_main_protection_manual_ja.md` | GitHubで`main`に必須CIチェックを設定する簡易手順 |

## 検証コマンド

```bash
python3 src/check_prereg.py        # 事前登録の先行コミット順序検査
python3 src/check_registry.py      # 登録簿の Holm しきい値と n_perm 要件検査
python3 src/validate.py            # アノテーション検証。問題があれば exit 1
python3 src/audit_no_hardcode.py   # 手書き定数監査。違反があれば exit 1
make test                         # 登録簿・scheduler・検証状態の回帰テスト（標準ライブラリのみ）
python3 src/verify_network.py      # 全件検証。終了コード0=passed、2=unavailable、1=failed
python3 src/verify_doc.py          # 本文の数値と results.json / network_checks.json の照合
make work-status                  # 作業キューの担当・lease・依存状態を表示
```

`run_all.py` は `validate` と `audit_no_hardcode` を先に実行し、どちらかが失敗したら解析を中止します。v17原本や Python 依存がない場合、ネットワーク検証は黙って `skipped` にせず `outputs/network_verification_status.json` を `unavailable` として記録し、未検証範囲を `outputs/report.md`・`outputs/results.json`・CI job summary に残して他の解析を続けます。`make run` / CI の成功と、ネットワーク全件検証の成功は別の状態です。`make network` は `unavailable` を終了コード2で返します。

## インタラクティブ HTML（グラフネットワークの人間確認）

`docs/interactive/graph_network_atlas.html` は、**v17 インタラクティブ HTML（原本デザイン）**に
リポジトリの最新データ（表示監査・乖離台帳・第 2 層評定・L1 再評定）を追記統合した
人間確認用ビューです（スイムレーン（**交易路オーバーレイつき**・交易史・考古学遺物に基づく
中継交易ルートを半透明の帯で近似表示）／地理座標（**世界地図背景つき**・Natural Earth
パブリックドメインの陸域・国境を埋め込み SVG で表示）／セクター選択／収録済神話リスト／
インスペクタ）。外部参照ゼロ＝オフライン `file://` のまま動作します。
交易路帯からみた**古事記以前のユーラシア接続性の考察**（リレー式中継ネットワークの
連鎖として物品・情報の流通可能性が成立していたことと、実際の移動はモチーフ伝播グラフ
597 エッジで実証されることの対応）は `docs/interactive_graph_html_ja.md` に記載しています。

```bash
make interactive   # docs/interactive/graph_network_atlas.html を再生成（標準ライブラリのみ）
```

土台は照合済みの v17 原本グラフ（297 ノード / 597 エッジ、`derived/v17_html_embedded_data.json`）。
表示値は ADR 0003 に従い改変せず、21 話の乖離台帳と評定（証拠つき）を注記カードとして追加します。
詳細と再生成手順は `docs/interactive_graph_html_ja.md` と HTML 内の凡例を参照してください。

## 並列チャットの担当取得

`config/work_queue.json` のタスクは、同じ共有 workspace 上で `src/work_scheduler.py` により排他的に取得できます。worker ID はチャットごとに一意に発行し、lease を heartbeat で延長してください。

```bash
python3 src/work_scheduler.py worker-id
python3 src/work_scheduler.py status
python3 src/work_scheduler.py claim-next --worker arena-発行ID
# 完了時: python3 src/work_scheduler.py complete TASK_ID --token CLAIM_TOKEN --reason "結果を記録"
```

状態は Git 管理外の `.work_scheduler/work_scheduler_state.json` に置きます。排他が成立するのは全 worker が同じ共有ファイルシステム・同じ state path を使う場合だけで、独立した sandbox/clone 間は調整しません。設計・lease・復旧手順は `docs/parallel_work_scheduler.md` を参照。

## リポジトリとしての運用（ハーネス）

このディレクトリはそのまま git リポジトリとして使える（初期コミット済み）。

```bash
make all      # prereg → registry → validate → audit → test → sim → 全解析 → 文書照合
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

## 並列実行（GitSwarm 型）

出力先は既定で `outputs/`。**同じ出力先への二重起動は拒否されます**（黙って上書きしません）。
並列に走らせるときは、ワーカーごとに出力先を分けてください。

```sh
make run                      # 単独
make OUTDIR=runs/w1 run &     # ワーカー 1
make OUTDIR=runs/w2 run &     # ワーカー 2（同時に走らせてよい）
make probe                    # 並行安全性の実測（6 検査）
make gate                     # マージ前: origin/main を取り込んで全ゲートを通す
```

* 実装は `src/analysis_io.py`（出力先の解決・原子的書き込み・`flock`）。
* 経緯と実測は `docs/path_connectivity_validity_review_20261128_ja.md` §11〜§15。
* 限界: ロックは同一ファイルシステム内でのみ有効です。別クローン間では効きません。

### マージ前の再検証（`make gate`）

CI は**ブランチ単独**を検査します。main とマージした**結果**は検査しません。
`make gate` は `origin/main` を `git merge --no-commit` で取り込み、同じゲートを回して
**必ず `git merge --abort` で元に戻します**（作業ツリーは変わりません）。

```sh
make gate       # 全ゲート通過なら exit 0、失敗 exit 1、競合 exit 2、origin/main と同じなら exit 3
make generated  # 追跡下の生成物が今のコードと一致するか（--full は再生成して照合）
```

* 生成物（`derived/`）を手で編集すると `make generated` と CI が落ちます。
  正当な手編集は生成物の `manual_edits` に理由を書くと通ります（理由が無ければ通りません）。
* 経緯と実測は同 §15。

### 書き換えの防止（`make invariant`）

登録簿 `docs/registry.md` は「結果を見る前に枝を登録し、結果が出たら追記する」運用です。
**事前登録セル**（枝 ID・仮説・主エンドポイントなど）は登録後に変えられず、
**結果セル**（結果・p・効果量・判定）は `pending` から 1 回だけ前進できます。
凍結データ `data/frozen/` は内容が変われません。

```sh
make invariant           # 基底 origin/main との比較（PR 相当）
make invariant-history   # 全履歴を走査
make new-id ARGS="--count 3"   # 衝突しない ID（JSON と Markdown の全シャードと照合）
make rules-live          # ruleset（コードで直せない設定）を実測と突合
```

* `make invariant` は**行のバイト不変ではありません**。列名で対応づけ、上の 2 層で見ます。
  バイトで見ると正しい運用（結果の追記・列の追加）が落ちるためです（§16.1 に実測）。
* 経緯と罠（`ls-tree` の glob・`ls-files` のインデックス読み）は同 §16。
