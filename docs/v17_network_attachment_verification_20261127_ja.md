# 添付ZIPの調査とv17ネットワーク全件検証（2026-11-27）

## 資料の特定と完全性

前回の入手不能という結論は、今回の添付資料については撤回する。添付ファイルは拡張子が `.zip.txt` だがZIP形式であり、展開した内容にv16/v17のHTMLとCSVが含まれていた。ZIPのCRC検査は正常。
- 添付: `workspace-01a21bab-9788-7269-8dc7-a1085e14ba9c.zip.txt`
- ZIP SHA-256: `9587c8611d45d2cdc881946b3cbba248283aa31c65ff73a3540bfbb0d6e43116`
- アーカイブにはディレクトリを含め123項目。元資料は `vendor/kojiki_mythology_v17_local/` にローカル展開し、リポジトリには追加していない。
- `ZIP_INFO.txt` のvendor目録40件と照合した結果、24件一致、5件欠落、11件不一致。パッケージ全体が同一とは断定できない。
- 全件検証の作業キューが指定する必須15件（v17/v16 HTML、各CSV、集計JSON）はすべて存在し、目録のSHA-256と一致した。検証はこれらの入力で行い、不一致のスクリプトは実行していない。

### 検証必須15件の目録SHA-256

- `vendor/kojiki_mythology_v17_local/output_v17_experiment/eurasia_myth_atlas_v17_interactive.html`: `880c2e5466a4db85c28114a5690d6a135ff6b3088dc8e57ec0355d13203045d0`
- `vendor/kojiki_mythology_v17_local/output_v17_experiment/data/v17_eurasia_edges_multiplex.csv`: `1866bec5753863a728b250e73292d769349118e3c4c8f6931a43b6747b42967f`
- `vendor/kojiki_mythology_v17_local/output_v17_experiment/data/v17_eurasia_297nodes_90d.csv`: `319e9bddb4ffc3399555b83cb47533c4db17d1129152a2e771ca110c7d005bfc`
- `vendor/kojiki_mythology_v17_local/output_v17_experiment/data/v17_eurasia_edges_90d.csv`: `65c4b15102bf07bf807f1decafc17eabe9f43a3ade0482391a311c7a7d3a1515`
- `vendor/kojiki_mythology_v17_local/output_v17_experiment/data/v17_eurasia_edges_joint90d.csv`: `c12bdde413566120860006a5f9b7f78d915c185e5a5cc27ad9659d672af5f12b`
- `vendor/kojiki_mythology_v17_local/output_v17_experiment/data/v17_pure_l2_ext_edges.csv`: `476585ce4bbf2c370ffb384b44ae616136e8b19ec0af796981f56b19aa0450c6`
- `vendor/kojiki_mythology_v17_local/output_v17_experiment/data/v17_pure_l2_ext_nodes.csv`: `101359cd10892e99a819e8890f8f2760361c8ee8d9853a88103a5955276e2bbf`
- `vendor/kojiki_mythology_v17_local/output_v17_experiment/data/v17_pure_l2_dom_edges.csv`: `1f58a72b70d019cc3358118c81905b7145f81b1c4a7cd609263c189a0491281a`
- `vendor/kojiki_mythology_v17_local/output_v17_experiment/data/v17_pure_l2_dom_nodes.csv`: `4aaf8eed58f6501570dede02de68c915c3a192e4b0e9db3cbe931bbc77ab65c8`
- `vendor/kojiki_mythology_v17_local/output_v17_experiment/data/v17_eurasia_297nodes_multiplex.csv`: `6f9c78299359c95dd273549609ff472524a8d34316f94cd2317b0d4a4e03429b`
- `vendor/kojiki_mythology_v17_local/output_v17_experiment/data/v17_kojiki_3layer_decomposition.csv`: `528700673d6d8e166cfa45dfbcc05b17e20a8506a7ac60ee0578354ceda9267a`
- `vendor/kojiki_mythology_v17_local/output_v17_experiment/data/v17_aggregate_summary.json`: `9a30f7cb8ca8b893d70590f2ddd0d9685a29df4bca5d83d1a46dd3bc47302b70`
- `vendor/kojiki_mythology_v17_local/output_v16_experiment/eurasia_myth_atlas_v16_interactive.html`: `ad47c87574a564200ce3a922bb320bfe1a9f6f8c789dee9c03d748dac608a6b6`
- `vendor/kojiki_mythology_v17_local/output_v16_experiment/data/v16_eurasia_edges_75d.csv`: `51add6c0d2829cb0dd058375fd354a45bb3c470e7cbb4e4b2ce45ea338f4bc7e`
- `vendor/kojiki_mythology_v17_local/output_v16_experiment/data/v16_eurasia_281nodes_75d.csv`: `f12573211945355571efd6fc6d38313a88d11df1967fd228765632087eb8f9fd`

### 目録との不一致・欠落

欠落:
- `README.md`
- `output_v17_experiment/figures/v17_fig1_dual_layer_swimlane.png`
- `output_v17_experiment/figures/v17_fig2_ablation_and_3layer_decomp.png`
- `output_v17_experiment/figures/v17_fig3_6hypotheses_quantified.png`
- `requirements.txt`

SHA-256不一致:
- `run_myth_analysis.py`
- `run_myth_v10_chronological_atlas.py`
- `run_myth_v11_indo_iran_atlas.py`
- `run_myth_v12_land_sea_atlas.py`
- `run_myth_v13_steppe_norse_split.py`
- `run_myth_v14_semantic_zoom_sector_ui.py`
- `run_myth_v15_corridor_east_asia.py`
- `run_myth_v16_deep_kernel_audit.py`
- `run_myth_v17_ritual_polity_layer.py`
- `run_myth_v8_eurasia_atlas.py`
- `run_myth_v9_mesopotamia_atlas.py`

## 再実行

添付ZIPの先頭ディレクトリの内容を `vendor/kojiki_mythology_v17_local/` に配置し、上記15件を目録と照合する。Python仮想環境にNumPy・pandasを導入し、`make network PY=.venv/bin/python` を実行する。ZIP・vendor・outputs は既存の除外方針どおりコミットしていないため、CIでは別途資料が提供されなければ未検証となる。今回のローカル実行結果とCIの状態は区別する。

## 実行と結果

- 環境: Python 3.11.2、NumPy 2.4.6、pandas 3.1.1。
- `make network PY=.venv/bin/python`: 終了コード0。状態 `passed`、60検査中 OK 40、WARN 7、NG 0、参考 13。
- `make all PY=.venv/bin/python`: 終了コード0。文書照合183項目、不一致0。単体テスト20件成功。
- 入力となるグラフは297ノード、597エッジ。全件台帳はそれぞれ `outputs/network_node_audit.csv` と `outputs/network_edge_audit.csv` に出力された（`outputs/` はコミット対象外）。
- `passed` は検証器の判定であり、警告7件が存在しないことや、パッケージ全体の完全一致を意味しない。

### 注意点

- 年代差0の辺21本、scoreがweight未満の辺4本、孤立ノード2件。
- 表示グラフと90D同時推定は異なる。表示上の被説明率と表示L1辺からの再計算が0.01を超えて異なるノードは21件。
- 第2層表示辺からの再計算と純L2記録値にも差がある。表示の層混成に留意する。

## 生成物のSHA-256

監査台帳・機械出力は同一入力で再生成できる。今回のローカル生成物のハッシュを以下に記録する。
- `outputs/network_checks.json`: `f3f3c54e2c97fe00a189ab81d1bea77dfcda7ddcb08066bb5df9492c256257e6`
- `outputs/network_edge_audit.csv`: `8590785f6c3dc869dce7e9aa64c0940208cbe2fb9afaa18ec12674b14741e58f`
- `outputs/network_node_audit.csv`: `38538f8793f52366c3d2948e0f770d87ae508e2b4ab0f58a51c5784b7ed087f3`
- `outputs/network_verification.md`: `656f243740496634e3d4087123c462cd361d02e853d9d0b4f5fa028749597620`
- `outputs/network_verification_status.json`: `1f4d51baa90d3b5ea23a11b25ba615c1d0fba6d668587cb1595d58f80b68168b`

## 全検査結果

以下は `outputs/network_checks.json` の60件を転記したもの。

| ID | 検査 | 値 | 判定 | 備考 |
| :--- | :--- | :--- | :--- | :--- |
| A1 | v17 HTML のノード数 / エッジ数 | 297 / 597 | ok |  |
| A2 | HTML エッジ集合 == multiplex CSV エッジ集合 | 共通 597 / 差 0 本 | ok |  |
| A3 | エッジ属性の最大ずれ（dt / dist / weight / score） | 0.0e+00 / 0.0e+00 / 5.0e-04 / 5.0e-04 | ok | weight/score の差は HTML 側 3 桁丸めによる |
| A4 | 文字列属性の一致率（type / shared / transforms） | 1.000 / 1.000 / 1.000 | ok |  |
| A5 | HTML ノード ID 順 == 90D ノード CSV の ID 順 | 一致 | ok |  |
| A6 | ノード座標・年代・次数の最大ずれ（次数は multiplex 表と比較） | 0.0e+00 / 0.0e+00 / 0.0e+00 / 0.0e+00 | ok |  |
| A7 | ノード region 一致率 | 1.000 | ok |  |
| A8 | v16 HTML のノード数 / エッジ数 vs v16 CSV | 281 / 494 vs 281 / 494 | ok |  |
| A9 | v16 HTML エッジ集合 == v16 CSV エッジ集合 | 0 本の差 | ok |  |
| A10 | motif_desc の語彙数（v17 / v16） | 90 / 75 | ok | L1 75 次元 + L2 15 次元 = 90 / L1 のみ 75 |
| B1 | 自己ループ | 0 | ok |  |
| B2 | 重複エッジ（同 source-target の再出現） | 0 本 | ok |  |
| B3 | 参照切れノード | 0 件 | ok |  |
| B4 | エッジの年代差 dt <= 0 | 21 本 | warn | dt 最小 0 年（負が無ければ時間逆行ではない。0 は同時代の並行エッジ） |
| B5 | dt の記録値と t_eff 差の不一致 | 0 本 | ok |  |
| B6 | 座標から再計算した距離と dist_km の最大差 | 0.05 km | ok |  |
| B7 | DAG 判定（Kahn で全ノードを整列できたか） | 297 / 297 | ok | 整列できれば非巡回 |
| B8 | 次数の再計算と記録値の不一致 | 0 件 | ok |  |
| B9 | 親数（層の合算）と同一 source の重複 | 最大 6（L1 3 + L2 3 = 6 が上限） / 重複 0 件 | ok | 多層を重ねた表示のため 1 ノードの親は最大 6 |
| B10 | 型の規則（dt≥350 → 伝播 / <350 → 平行）との不一致 | 0 本 | ok |  |
| B11 | weight / score の範囲 | [0.250, 1.000] / [0.452, 1.000] | ok |  |
| B12 | score < weight のエッジ | 4 本 | warn | いずれも L1+L2 統合エッジで、重みのみ max(L1,L2) に置換したため得点が追随していない |
| B13 | 剥離ステップ（層ごと） | 1..k の連続性からの逸脱 26 / 上限超 0 / 重複 0 | ok | 逸脱は、統合時に LP・古事記関連以外の第2層エッジを除いたための番号の欠番（仕様） |
| B14 | レーン（region / lane_idx / color）の整合 | 一致 | ok | レーン数 19 |
| B15 | モチーフ ID の辞書照合 | 4698 参照 / 未知 0 件 | ok |  |
| B16 | 変換表記（A↔B）の書式 | 正常 597 / 異常 0 | ok |  |
| B17 | explained_pct の範囲 | [0.0, 100.0] | ok |  |
| B18 | best_p の範囲 | [0.0066, 1.0000] | ok |  |
| B19 | 弱連結成分数 / 孤立ノード | 3 / 2 | warn | 孤立: NO07,EX16 |
| B20 | 入次数 0 のノード（根）数 | 31 | info |  |
| B21 | 古事記ノードを source とするエッジ（規則違反） | 0 本 | ok |  |
| C1 | 公開された規則（v16 494 本 + 純 L2 dom の LP/古事記関連）での再構成 | 597 本 | ok | 追加 103 / 重複統合 5 / 差分 0 |
| C2 | 層ラベル（L1_myth / L2_ext / L2_dom / L1+L2）の一致率 | 1.000 | ok | {'L1_myth': 489, 'L2_ext': 85, 'L2_dom': 18, 'L1+L2': 5} |
| C3 | L1+L2 統合エッジの重み = max(L1, L2) | 5 本 / 一致 ○ | ok |  |
| C4 | 純 L2 エッジのうち HTML に載らないもの（LP/古事記 関連以外を除外） | ext 75 / dom 61 | info | 仕様どおりの絞り込み。グラフ全体が純 L2 の全辺を含むわけではない |
| C5 | 90D 同時推定グラフ（504 本）と表示グラフ（597 本）の差分 | 共通 393 / 90D のみ 111 / 表示のみ 204 | warn | 表示グラフは v16 L1 + 純 L2 の重ね合わせであり、90D 同時推定の結果ではない |
| C6 | 3 層分解の算術（L1+L2ext+L2dom=total / 100-total=irreducible） | 最大誤差 0.010 / 0.000 pp | ok | 37 話 |
| D1 | L1 第1ステップの重み = 75 次元コサイン（最大差） | 5.0e-05（247 本） | ok | 差は CSV の 4 桁丸め |
| D2 | L1 エッジ列を再帰剥離して得た被説明率 vs v16 記録値 | 平均差 0.0045 / 最大 0.4211 / 0.01 以内 0.984 | ok | 248 ノード |
| D3 | 第2層 15D：表示エッジからの再計算 vs 純 L2 記録値 | 平均差 0.169 / 0.01 以内 0.569（ext 0.667 / dom 0.200） | warn | 乖離は、統合時に第2層エッジを LP・古事記関連に絞ったため（D 節の残りは元の全エッジで計算された値） |
| D4 | HTML の explained_pct の出所分類 | v16.L1 244 / decomp.total_final 37 / pureL2_dom 16 | ok | ノードごとに別の計算（3層分解 / v16 L1 / 純 L2）が混在 |
| D5 | 表示エッジから再計算した被説明率と表示値が 0.01 超ずれるノード | 全体 21 / 248、うち古事記 21 / 52 話 | warn | 最大は K1-05。古事記の表示値は 3 層分解（L1+L2 同時）に由来し、画面の L1 エッジからは導けない |
| D6 | 集計 JSON の multiplex エッジ数 vs 実際 | {'L1_myth': 489, 'L2_ext': 85, 'L2_dom': 18, 'L1+L2': 5} vs 597 | info |  |
| D7 | 集計 JSON の古事記平均被説明率（3 層全適用） | 0.8217 | info | v17 報告書の「85.44%」とは一致しない（報告書側の表記は §3 参照） |
| D8 | 集計 JSON の v16 L1 平均被説明率（古事記） | 0.7954 | info |  |
| F1 | エッジ全件台帳の行数 | 597 行（source/target/層/step/dt/距離/型/重み/共有モチーフ） | info | outputs/network_edge_audit.csv |
| F2 | 全 597 エッジのうち dt > 0 を満たさないもの | 21 本 | ok | 内訳は台帳を参照 |
| F3 | 全 597 エッジのうち 型の規則 を満たさないもの | 0 本 | ok |  |
| F4 | 全 597 エッジのうち 距離の再計算一致 を満たさないもの | 0 本 | ok |  |
| F5 | 全 597 エッジのうち score >= weight を満たさないもの | 4 本 | warn | 内訳は台帳を参照 |
| F6 | 共有モチーフが両ノードのベクトルに存在しないエッジ | 0 本 | ok | L1 は 75 次元行列、L2 は再構成した 15 次元ベクトルで照合 |
| F7 | ノード全件台帳の行数 | 297 行（次数・表示値・再計算値・出所） | info | outputs/network_node_audit.csv |
| F8 | 次数が記録と一致しないノード | 0 件 | ok |  |
| F9 | 表示値と L1 再計算値が 0.01 超ずれるノード（全件） | 21 件 | info | F2 の台帳で個別に確認できる |
| F10 | 表示混成 21 話と全ノード出所の derived 台帳照合（ADR 0003） | 21 / 21 話一致（出所一致=True） | ok | derived/html_embedded_v17_audit.json |
| E-cosine | 古事記 37 話をターゲットにした順列検定 | 実測 0.761 / 帰無 0.600±0.012 / p=0.005 / d=13.83 / エッジ 491 | info |  |
| E-cosine-all | 全 281 ノードをターゲットにした順列検定（ネットワーク全体） | 実測 0.616 / 帰無 0.465±0.005 / p=0.005 / d=32.37 / エッジ 491 | info |  |
| E-calibrated | 古事記 37 話をターゲットにした順列検定 | 実測 5.268 / 帰無 4.684±0.104 / p=0.005 / d=5.61 / エッジ 695 | info |  |
| E-calibrated-all | 全 281 ノードをターゲットにした順列検定（ネットワーク全体） | 実測 4.061 / 帰無 3.725±0.035 / p=0.005 / d=9.72 / エッジ 695 | info |  |
| E-jac | v18 エンジンで独立に作ったエッジ集合と v16 の 494 本の重なり | 共通 255 / v18 491 / v16 494 / Jaccard 0.349 | info | 変換なし・全距離許容という v18 仕様のため完全一致はしない |
