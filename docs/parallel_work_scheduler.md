# 並列作業キューの運用

このリポジトリでは `config/work_queue.json` をタスク定義、`.work_scheduler/work_scheduler_state.json` を作業中状態として使う。状態ファイルは Git 管理外で、同じ共有ワークスペースを使う複数の Arena チャットが担当を原子的に取り合うためのもの。

## 制約を先に確認

- **この方式が排他を保証するのは、全チャットが同じ共有ファイルシステム上の同じ state path を使う場合だけ。** 別の clone、別 sandbox、同期されない checkout 間は調整しない。
- 排他は state と同じディレクトリにある `.lock` ファイルへの OS `flock` と、state JSON の一時ファイル書き込み・atomic rename で行う。
- チャットごとに一意の worker ID を使う。同じ worker ID を複数チャットで共有すると、同一担当とみなされる。
- 初回 claim でタスク定義の SHA-256 を state に束縛する。`config/work_queue.json` が変わった状態で同じ state を継続利用すると claim を拒否する。キュー変更時は、進行中タスクを引き継いだうえで状態ファイルの扱いを人が判断する。状態を新規に始める必要がある場合も、既存 state を消さずに退避し、全 worker を停止してから全員で新しい `--state` path を選ぶ。
- state と lock はローカル運用用で、Git への commit はしない。claim token は state に平文保存せず SHA-256 のみ保存する。

## 使い方

リポジトリルートで実行する。最初に worker ID を一度発行し、そのチャットの作業中は同じ ID を使う。

```bash
python3 src/work_scheduler.py worker-id
# 出力された ID を控える（例: arena-...）
python3 src/work_scheduler.py status
python3 src/work_scheduler.py claim-next --worker arena-ここに発行ID
```

`claim-next` は優先度順に、依存タスクが完了し、必要なパスが存在する open タスクを一件だけ取得する。個別指定は `claim TASK_ID --worker WORKER_ID`。結果の `claim_token` はその claim の秘密情報であり、claim を更新・完了・解放するために必要。

```bash
python3 src/work_scheduler.py heartbeat TASK_ID --token CLAIM_TOKEN --lease-seconds 21600
python3 src/work_scheduler.py complete TASK_ID --token CLAIM_TOKEN --reason "確認結果を記録"
# 作業を中断・引き継ぐ場合
python3 src/work_scheduler.py release TASK_ID --token CLAIM_TOKEN --reason "中断理由"
python3 src/work_scheduler.py status
```

既定 lease は6時間。期限切れ claim は次の scheduler 操作時に open に戻る。旧 token は期限切れ後には使えない。チャットが終了したり作業を渡したりする場合は、可能なら `release` を行う。作業済みの claim を `complete` にする前に、タスクの acceptance と結果・未解決事項を成果物に記録する。scheduler は成果物の正しさを自動審査しない。

`--state` と `--catalog` を差し替える場合は全 worker で同じパスを指定する。グローバル引数はサブコマンドより前に置く。

```bash
python3 src/work_scheduler.py --state /共有場所/claims.json status
```

## キュー内容

`config/work_queue.json` には、v17原本の回収、資材が揃った後のネットワーク全件検証、L1/古事記/LP14の短証拠レビュー、最後の `make validate` を分離して登録してある。独立レビューは並列に claim でき、ネットワーク検証と最終チェックは依存条件により早すぎる着手を防ぐ。

キューの状態を表示するショートカット:

```bash
make work-status
```

## ネットワーク検証状態との区別

タスクを claim したこと、CI が成功したこと、`make run` が他の解析を完了したことは、v17ネットワーク全件検証の成功を意味しない。実行結果は `outputs/network_verification_status.json` で判定する。

- `passed`: A–F の必須セクション・全件成果物を生成し、NG なしで完了。
- `failed`: 入力が見つかった後の検査で不整合が出た、または検証器が完了できなかった。
- `unavailable`: v17原本または Python 依存がなく、全件検証を開始できなかった。`unverified_scope` が未検証範囲。
- `running`: 実行が中断された可能性がある。完了扱いしない。

`python3 src/verify_network.py` / `make network` は `passed` のときだけ終了コード0、`unavailable` は2、`failed` は1を返す。全解析 `make run` はネットワーク状態を `results.json` と `report.md` に含め、`unavailable` を明示したうえで他の解析を継続する。CI の artifact と job summary にも状態を記録する。ネットワークが `unavailable` の CI 成功を、全件検証成功と表現してはならない。
