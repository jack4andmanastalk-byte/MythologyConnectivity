# `AIselfMySelf` の GitSwarm 型ハーネスは本リポジトリにどこまで参考になるか

- 調査日: 2026-11-27（UTC）
- 対象: `MythologyConnectivity` の作業ブランチ `arena/6f9a9d86-mythologyconnectivity`（基点 `13a9d1bd01920dc249264785a40fbcb43691689a`）
- 比較先: [`aiselfmyselfresearch-max/AIselfMySelf`](https://github.com/aiselfmyselfresearch-max/AIselfMySelf)、調査時の `main` `ab6c425858e57c9428caf85b3a265cdd50f672ec`（2026-11-27 12:36 UTC）
- 調査方法: 両リポジトリのコード・設計文書・CI定義を静的に確認し、GitHub APIからブランチ保護状態と外部リポジトリのツリーを読み取り。外部リポジトリのコードや設定は変更していない。
- 規模の目安: 本リポジトリは追跡ファイル44件、比較先はGitHubツリーAPIでblob 2,953件。これは品質の優劣ではなく、比較先の仕組みがより大きな記録アーカイブを支えるために育ったことを示す。

## 1. 結論

**参考価値は高い。ただし、参考にすべきなのは「複数作業者の衝突を減らす運用設計」と「GitHub側のマージ保護」であり、ハーネス一式やコードをそのまま移植することではない。**

| 評価対象 | 評価 | 要点 |
|---|---|---|
| 並列作業の分割・重複防止という設計思想 | **高** | 固定した作業単位、担当の分離、専用出力先、重複・網羅性検査は、将来このリポジトリで複数の独立監査を走らせる場合に有効。 |
| 外部リポジトリのコードを直接移植する価値 | **低** | `AIselfMySelf` は大規模な追記専用記憶アーカイブ。本リポジトリは凍結入力に対する小規模な数値解析パイプラインで、共有台帳・Webビューア・大量シャードを持たない。 |
| 今すぐ最優先で取り入れるべき点 | **高** | 本リポジトリの GitHub `main` は調査時点で `protected: false`、ルールセットも空だった。CIワークフローがあるだけでは、失敗時のマージを止める仕組みにならない。 |
| モデルの独立性や研究結論を保証する力 | **低** | ブランチ分割やCIは、モデル間の共有バイアス、盲検の実施、解釈の妥当性を保証しない。 |

本稿では「GitSwarm 型」を、**複数の作業ブランチに作業を分け、リポジトリ内の担当記録・成果物・検査を通じて協調させる方式**という意味で使う。比較先のコードはワーカー用LLMを起動する実行基盤ではない。`git` と `gh` を使って作業枠を調整し、外部の作業者がそれに従うためのハーネスである。

## 2. 比較先のハーネスの中身

### 2.1 作業単位の固定と、ブランチ間の担当分離

比較先は、リポジトリ内の大量の台帳・精読記録・コードを **16ユニット（U01〜U16）= 4トラック × 4ユニット**に分ける。`tools/taxonomy_plan.py` は各ユニットについて対象範囲・件数・出力先を示し、同じ作業を複数ブランチで重ねないための処理を持つ。

- `taxonomy/claims/<track>-<branch-seed>.json` に担当トラックを記録。
- `taxonomy/shards/<unit>-<branch-seed>.jsonl` と `taxonomy/notes/` にブランチ固有の成果物を保存。
- `--next-unit --auto-claim` で次の未完了ユニットを選び、`--prepare-push` は、既に `origin/main` にある分類との重複や自ブランチの検証エラーがある場合に push 準備を止める。
- シャード検査は必須キー、値の集合、対象の重複、ユニットごとの対象網羅を確認する。

担当確保は中央の排他ロックではない。コードはリモートブランチを走査し、担当票を push し、同時取得が起きた場合は再走査・時刻順の競合解決を試みる。`tests/test_taxonomy_plan.py` に、共有の Git リモートを使って4ワーカーが別トラックを取るケースなどがある。これは**試験した条件下での協調機構**の証拠であって、任意のネットワーク障害や全ての分散実行環境での厳密な排他を証明するものではない。

### 2.2 追記専用台帳と並列I/Oの安全策

`docs/parallel-work.md` と `docs/parallel-safety-audit.md` は、共有台帳を同時に更新したときの実害を再現したうえで、次の仕組みを説明している。

- 凍結ベース台帳と、追記先の分離された `state/*.d/` シャード。
- 衝突しにくいID採番、安定読み込み、原子的書き込み、必要な処理のロック。
- `append_only_check.py` による、マージ基点にあった行が**同じバイト列のまま残る**ことの検査。行を別シャードへ移す保守は許すが、過去行の書き換え・削除を検出する。
- 並列書き込み・読み込みを模したプローブと、重複ID・シャード読み込み・ビューア応答などの回帰テスト。

この設計は、実際に複数のワーカーが同一の追記専用データベースを更新する場合には強い。一方、本リポジトリの `data/frozen/` と既存の評定データは解析入力として読み込まれ、通常の実行時に複数プロセスから共通台帳へ追記する構成ではない。そのため、`ledger_io.py` 相当の汎用並列I/O層は、現状では導入コストに見合いにくい。

### 2.3 CI、テスト、生成物

比較先の `.github/workflows/ci.yml` は、スキーマ・参照・追記専用性・生成マップの鮮度・日付・サイズなどを検査し、回帰テストをファイル名パターン別の5ジョブに分割している。ワークフローのコメントは、2026-11-23の測定として1,125テスト、直列実行約482秒を記している。`map.yml` は大きな生成マップをGit履歴へ含めず、Actions artifactとして保存する。

これは「大きくなったテスト群をCI上で並列化する」良い例だが、比較先のドメインに特有の多数の台帳・索引・ビューアを支える構成でもある。本リポジトリに同規模のテスト群や共有データ書き込みがある、という意味ではない。

## 3. `MythologyConnectivity` 側に既にあるもの

本リポジトリは、研究用の再現可能なパイプラインとして必要な中核をすでに持っている。

- `config/analysis.json` を設定源とし、凍結データ・アノテーション・実行条件を管理。
- `docs/prereg/`、`docs/registry.md`、`src/check_prereg.py`、`src/check_registry.py` で事前登録、試行一覧、Holm補正と必要置換回数を確認。
- `src/validate.py` と `schema/annotation.schema.json` でアノテーション形式・証拠・重複を検査。
- `src/audit_no_hardcode.py` で解析定数のコード埋め込みを監査。
- `src/run_all.py` が結果・レポート・入力ハッシュを生成し、`src/verify_doc.py` が本文の数値と生成結果を照合。
- `src/check_determinism.py` と `make determ` で同一環境の再実行一致を確認。
- `outputs/` はGit追跡外とし、CI artifactに回す。
- `src/sim_swarm_review.py` と `docs/adr/0002-long-run-independent-review.md` は、共有バイアス・多重試行・鎖状レビューの問題を既に検討している。

したがって、比較先から研究方法そのものを持ち込む必要は薄い。むしろ、**このリポジトリが既に持つ統計・事前登録のゲートを保ったまま、実際に並列作業が必要になった箇所だけを分離する**のが適切である。

ただし、`docs/adr/0001-repository-as-harness.md` は現在「提案（草案）」であり、本文には「CIが失敗したらマージできない」という趣旨がある。ワークフロー定義だけではこの条件は成立しない。調査時点で GitHub API は `MythologyConnectivity` の `main` を `protected: false` と返し、リポジトリのルールセット一覧も空だった。**CIをマージ必須条件にするには、GitHub側でブランチ保護またはルールセットを設定し、実際の必須チェックを指定する必要がある。**

## 4. 適用性の評価

| 機能 | 比較先から参考にする点 | 本リポジトリへの適合 | 推奨 |
|---|---|---:|---|
| 固定した作業分割・担当範囲 | 対象を先に列挙し、同じファイルを複数ワーカーが編集しない | **高** | 将来、独立したネットワーク監査や盲検評定を並列化するときに、固定対象集合と担当表を使う。16ユニットやトラック数は模倣しない。 |
| ブランチ別の成果物置き場 | 各作業者が固有パスへ出力し、最後に統合する | **高** | `annotations/` は評定者・パスごとの新規ファイル、生成物は実験ID別のCI artifactなど、既存ファイルを同時編集しない形にする。 |
| 担当確保・期限切れの調整 | 複数のブランチに対する担当票と状態表示 | **中** | 3件以上の同時作業が反復して重複した場合に再検討。今は固定した担当表または人手の割当で十分。 |
| 追記専用・バイト単位の履歴検査 | 既に確定した証拠・事前登録を後から書き換えない | **中〜高** | `docs/prereg/` と凍結入力には有効。ただし `docs/registry.md` は結果確定後に状態・結果を記すため、比較先の単純な追記専用検査をそのまま適用すると運用と衝突する。必要なら「事前登録」と「結果イベント」を別レコードに分ける。 |
| 原子的I/O・共有台帳ロック | 同じファイルを複数プロセスが同時更新する場合の保護 | **低（現状）** | 現在は共通台帳への並列書き込みがない。並列化するならまず作業ブランチ・実行環境・出力先を分け、ロック層は必要性が確認されてから足す。 |
| CIのテスト分割 | 大きい回帰テスト群を複数ジョブに分ける | **中** | 調査時点では一つの `gates` ジョブで独立した `tests/` 群はなかった。今回、登録簿・Holm計算の小規模テストを追加して同ジョブで実行する。実測時間が問題になった段階で分割する。 |
| GitHubのマージ保護 | 赤いCIをマージ前に止める | **非常に高** | 最優先。ワークフローの記述とGitHub側の必須チェック設定を一致させる。 |
| 比較先固有の記憶アーカイブ一式 | 12コレクション、巨大索引、ビューア、自己モデル監査など | **低** | 研究対象・保存形式・利用者が異なるため移植しない。 |

## 5. 移植時に注意すべき限界

### 5.1 GitHub上の担当票は、厳密な排他ロックではない

`taxonomy_plan.py` の現行コードでは、`git ls-remote` に失敗した場合にリモート状態を空として返す経路があり、呼び出し側が全トラックを空きとみなす可能性がある。また push に失敗した場合は `claimed_local_only` を返す。これは中央サーバーのトランザクションではなく、GitHubへの読み書き・再確認を用いた協調方式である。

本リポジトリで同種の仕組みが必要になった場合は、ネットワーク確認失敗時に**割当を確定しない（fail closed）**こと、未pushの担当票を有効扱いしないこと、競合・期限切れ・再試行のテストを置くことが必要である。現段階では、専用の割当サービスや動的スケジューラーを追加するより、事前に決めた対象範囲をブランチごとに割り当てる方が単純で安全である。

### 5.2 ブランチ分割は盲検や独立性を自動では作らない

作業者が同じモデル系統、同じプロンプト、同じ先行評価を見ているなら、ブランチが別でも誤差は相関しうる。Gitの履歴や多数決は、それを独立評価に変えない。`AIselfMySelf` 側のハーネスも、リポジトリの構造・形式を検査するもので、解釈の真偽を判定するものではない。

本リポジトリでは、独立評定を追加するなら次を先に固定する。

1. 評定者・モデル系統・使用指示と、見せない情報の範囲。
2. 事前登録済みの対象・語彙・主評価指標・停止規則。
3. 評定者ごとに分けた出力ファイルと、重複・欠落を検査するコード。
4. 全評定を固定した後にだけ比較し、不一致の分布や一致度を残す集約手順。
5. 可能なら人手抽出監査など、LLM以外のアンカー。

### 5.3 CI成功は、証拠の妥当性を意味しない

比較先の多数のテストが示すのは、実装した不変条件やファイル構造が守られていることだ。引用の正確さ、語彙の妥当性、神話間の対応に因果的・歴史的根拠があることまでは証明しない。本リポジトリでも、機械検証できる整合性と、学術的な解釈の妥当性を別々に報告する必要がある。この区分は既存の `docs/adr/0001`・`docs/adr/0002` の方向性と一致する。

## 6. 推奨する導入順

### 優先度1: GitHub側の必須チェックを設定する

`main` に対し、現在のCIワークフローの実際のチェック（ジョブ `gates` に対応するチェック名をGitHub上で確認）を必須化する。設定後は、わざと失敗させたテストでマージが止まることを確認する。GitHub APIで `protected: false`、ルールセット一覧が空だった状態は、ソースコードだけでは直らない。

### 優先度2: 並列化が必要な一つの作業で小さく試す

最初の試行は、例えば「297ノード・597エッジの独立再計算」または「事前登録した対象だけの独立盲検評定」のどちらか一つに絞る。各作業者に重ならない対象と専用出力先を割り当て、共有の設定・事前登録・結果表を同時編集させない。最後に一つの統合役が網羅性・重複・差分を機械検査し、結果を登録簿へ反映する。

### 優先度3: 実測した問題にだけ仕組みを足す

- 重複作業が起きたら担当表や単純な claim ファイルを追加。
- 同一ファイルの同時書き込みが起きたら、追記専用シャードまたは独立worktreeを導入。
- テスト時間が長くなったら、測定結果を根拠にCIを分割し、全ての分割チェックをマージ条件へ含める。
- 事前登録の順序をより強く証明したくなったら、Gitコミット時刻だけでなく、実験IDごとの結果イベントを追記専用で記録する。

**推奨しないこと:** いまの段階で `taxonomy_plan.py`、`ledger_io.py`、16ユニット分類、巨大な台帳構造をまとめて移植すること。作業規模に対して複雑性が先行する。

## 7. 調査上の留保

- 比較先の `main` は調査中にも進んだため、外部コード・ツリー数は上記コミットSHAで固定した。GitHub APIのブランチ情報では同リポジトリの `main` は `protected: true` だったが、権限上、必須チェックの詳細設定までは読み取れなかった。`main-guard.yml` と `main_guard.py` の記述には過去の未保護状態を前提にした文言が残っているため、文書だけで現在の設定を推定しない。
- 最新コミット `ab6c425` に対する全CIの完了は確認していない。調査時に新規のマップ生成ワークフローは実行待ちで、直近の `ledger-ci` 成功はひとつ前のコミット `4fc41a9` に対するものだった。
- 本リポジトリでは `src/check_registry.py`、`src/validate.py`、`src/audit_no_hardcode.py` を実行した。登録簿・定数監査は合格し、アノテーションはエラー0件だったが、短い証拠に関する警告は残った。`src/sim_swarm_review.py` と全解析は、この実行環境に `numpy` がなかったため実行していない。したがって本稿は、今回の全パイプライン再現試験ではなく、構成と運用設計の比較である。
- GitHubの設定変更、外部リポジトリの変更、他ブランチへの変更は行っていない。

## 8. 実施後追補（2026-11-27）

この報告後、提案のうちリポジトリ内で完結する小さな実装を進めた。

- `tests/test_check_registry.py` を追加し、登録表の読み取り、仮説検定行の識別、Holmしきい値、必要置換回数、文書記載値との不一致検出を7件のテストで確認する。
- `make test` を追加し、`.github/workflows/verify.yml` の `gates` 内から実行する。READMEにもテストコマンドと設定手順を掲載した。
- GitHubの `main` 保護設定はAPIから更新を試みたが、`403 Resource not accessible by integration` で拒否された。設定は未変更のままなので、管理者向け手順を [`docs/github_main_protection_manual_ja.md`](github_main_protection_manual_ja.md) に作成した。
- 並列担当スケジューラーや共有台帳I/O層は追加していない。実際の複数作業者による試行がまだなく、固定担当表・専用出力先から始めるという本報告の段階的な推奨を維持する。

## 9. 参照資料

### 比較先（`AIselfMySelf`、コミット `ab6c425858e57c9428caf85b3a265cdd50f672ec`）

- [リポジトリのコミット](https://github.com/aiselfmyselfresearch-max/AIselfMySelf/commit/ab6c425858e57c9428caf85b3a265cdd50f672ec)
- [`tools/taxonomy_plan.py`](https://github.com/aiselfmyselfresearch-max/AIselfMySelf/blob/ab6c425858e57c9428caf85b3a265cdd50f672ec/tools/taxonomy_plan.py) — 担当確保、ユニット選択、重複拒否、シャード検査
- [`docs/parallel-work.md`](https://github.com/aiselfmyselfresearch-max/AIselfMySelf/blob/ab6c425858e57c9428caf85b3a265cdd50f672ec/docs/parallel-work.md) — 台帳のシャード運用・並列作業規約
- [`docs/parallel-safety-audit.md`](https://github.com/aiselfmyselfresearch-max/AIselfMySelf/blob/ab6c425858e57c9428caf85b3a265cdd50f672ec/docs/parallel-safety-audit.md) — 競合の再現、修正、未解決事項
- [`docs/artifact-taxonomy-and-parallel-plan.md`](https://github.com/aiselfmyselfresearch-max/AIselfMySelf/blob/ab6c425858e57c9428caf85b3a265cdd50f672ec/docs/artifact-taxonomy-and-parallel-plan.md) — 16ユニットの分割計画
- [`.github/workflows/ci.yml`](https://github.com/aiselfmyselfresearch-max/AIselfMySelf/blob/ab6c425858e57c9428caf85b3a265cdd50f672ec/.github/workflows/ci.yml) — 台帳検査と5分割テスト
- [`.github/workflows/main-guard.yml`](https://github.com/aiselfmyselfresearch-max/AIselfMySelf/blob/ab6c425858e57c9428caf85b3a265cdd50f672ec/.github/workflows/main-guard.yml) / [`tools/main_guard.py`](https://github.com/aiselfmyselfresearch-max/AIselfMySelf/blob/ab6c425858e57c9428caf85b3a265cdd50f672ec/tools/main_guard.py) — ブランチ保護状態の確認
- [`tools/append_only_check.py`](https://github.com/aiselfmyselfresearch-max/AIselfMySelf/blob/ab6c425858e57c9428caf85b3a265cdd50f672ec/tools/append_only_check.py) — ベース行のバイト単位の保持検査
- [GitHub API: 比較先 `main` ブランチ情報](https://api.github.com/repos/aiselfmyselfresearch-max/AIselfMySelf/branches/main)

### 本リポジトリ

- [`README.md`](../README.md)、[`START_HERE.md`](../START_HERE.md)、[`Makefile`](../Makefile)
- [`.github/workflows/verify.yml`](../.github/workflows/verify.yml)
- [`config/analysis.json`](../config/analysis.json)、[`docs/registry.md`](registry.md)、[`docs/prereg/`](prereg/)
- [`docs/adr/0001-repository-as-harness.md`](adr/0001-repository-as-harness.md)、[`docs/adr/0002-long-run-independent-review.md`](adr/0002-long-run-independent-review.md)
- [`src/check_prereg.py`](../src/check_prereg.py)、[`src/check_registry.py`](../src/check_registry.py)、[`src/run_all.py`](../src/run_all.py)、[`src/check_determinism.py`](../src/check_determinism.py)、[`src/sim_swarm_review.py`](../src/sim_swarm_review.py)
- [GitHub API: 本リポジトリ `main` ブランチ情報](https://api.github.com/repos/jack4andmanastalk-byte/MythologyConnectivity/branches/main)
- [GitHub API: 本リポジトリのルールセット](https://api.github.com/repos/jack4andmanastalk-byte/MythologyConnectivity/rulesets)
