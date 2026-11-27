# `main` ブランチ保護の簡易設定手順

この手順は `MythologyConnectivity` のCIが失敗した状態で `main` へマージされるのを防ぐためのものです。

## 設定する内容

- 対象ブランチ: `main`
- マージ前にPull Requestを必須にする
- 必須ステータスチェック: `gates`
- ブランチを最新状態にしてからマージする
- 管理者によるチェックの迂回を許可しない（推奨）
- Force pushとブランチ削除を禁止する（推奨）

このリポジトリの `.github/workflows/verify.yml` は `verify` ワークフロー内の `gates` ジョブで検証を実行します。GitHubの画面にチェック名が `gates` または `verify / gates` と表示される場合は、**画面に出ている実際のチェック名**を選んでください。

## GitHubのWeb画面から設定する

1. GitHubで [`jack4andmanastalk-byte/MythologyConnectivity`](https://github.com/jack4andmanastalk-byte/MythologyConnectivity) を開く。
2. **Settings** → **Branches** を開く。
3. 画面に応じて、次のどちらかを選ぶ。
   - **Branch protection rules** が表示される場合: **Add branch protection rule** を選ぶ。
   - **Rulesets** を使う画面の場合: **New branch ruleset** を作成する。
4. 対象ブランチのパターンに `main` を指定する。
5. **Require a pull request before merging** を有効にする。
   - 何人の承認を必須にするかは運用方針に合わせる。作成者自身が緑のCIを確認してマージする運用なら承認数は0、第三者レビューも必須にするなら1以上にする。
6. **Require status checks to pass before merging** を有効にし、必須チェックとして `gates`（または画面に表示される正確なチェック名）を選ぶ。
   - チェック名が候補に出ない場合は、先にテスト用Pull Requestを作成して `verify` を一度実行し、完了後に設定画面を開き直す。
   - **Require branches to be up to date before merging** も有効にする。
7. 管理者による迂回を防ぐ項目（**Do not allow bypassing the above settings** / **Include administrators** など）があれば有効にする。
8. Force pushとブランチ削除を許可しない設定にする。
9. 設定内容を確認して **Save changes** を押す。

## 設定後の確認

- `main` のブランチ保護ルールまたはRulesetが有効になっている。
- Pull RequestのChecks欄で `gates` が必須チェックとして表示され、成功後にマージ可能になる。
- 可能ならテスト用のブランチでCIを一時的に失敗させ、失敗時はマージできないことを確認する。その後、失敗を直して緑に戻す。

## 権限について

この設定には通常、リポジトリの管理者権限が必要です。今回、ArenaのGitHub接続から保護設定APIの更新を試みましたが、GitHubが `403 Resource not accessible by integration` を返したため、**設定自体は変更されていません**。このマニュアルに沿って管理者アカウントで設定してください。

Arena経由での設定を希望する場合は、GitHub接続を再接続し、対象リポジトリのブランチ保護設定を変更できる権限が付与されていることを確認してください。資格情報やトークンをチャットに貼る必要はありません。
