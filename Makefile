PY ?= python3
# 出力先。並列に走らせるときは `make OUTDIR=runs/w1 run` のように分ける（既定は outputs/）。
OUTDIR ?=
ifneq ($(OUTDIR),)
export ANALYSIS_OUTPUT_DIR := $(OUTDIR)
endif

.PHONY: all prereg registry validate audit test sim run network doc determ interactive work-status clean edges pathdep repro numbers probe outdir generated gate invariant new-id rules

all: prereg registry validate audit test sim run doc numbers probe generated invariant rules    ## 事前登録 → 登録簿 → 検証 → 監査 → 回帰テスト → 全解析 → 文書照合 → 数値ゲート → 並行安全性 → 生成物の鮮度 → 不変性 → ruleset

prereg:                            ## 事前登録が結果より先に固定されたか（git 履歴）
	$(PY) src/check_prereg.py

registry:                          ## 登録簿の枝数から Holm しきい値・必要置換回数を算出・検査
	$(PY) src/check_registry.py

validate:                          ## アノテーションのスキーマ・証拠・重複検査
	$(PY) src/validate.py

audit:                             ## 解析定数がコードに漏れていないことの AST 監査
	$(PY) src/audit_no_hardcode.py

test:                              ## 登録簿・並列作業claim・検証状態の回帰テスト（標準ライブラリのみ）
	$(PY) -m unittest discover -s tests -v

sim:                               ## 多モデル並列レビューの誤差訂正能力の評価（ADR 0002 の数値）
	$(PY) src/sim_swarm_review.py

run: prereg registry validate audit sim  ## 全解析（results.json / report.md / manifest を生成）
	$(PY) src/run_all.py

edges:                             ## 597 エッジを 4 クラスに全件分類（枝 #8）
	$(PY) src/edge_reproduction.py

pathdep:                           ## 古事記経路の単一障害点・中継依存の感度分析（枝 #9）
	$(PY) src/path_dependency.py

repro:                             ## 表示被説明率の再計算可否台帳（枝 #10）
	$(PY) src/display_reproducibility.py

numbers:                           ## 文書中の総数表現の統一ゲート（枝 #11）
	$(PY) src/verify_numbers.py

probe:                             ## 出力の並行安全性を実測する（枝 #12）
	$(PY) src/concurrency_probe.py

outdir:                            ## 現在の出力先を表示する
	@$(PY) -c "import sys; sys.path.insert(0,'src'); import analysis_io as IO; print(IO.output_dir())"

generated:                         ## 追跡下の生成物が今のコードと一致するか（枝 #13）
	$(PY) src/check_generated.py

gate:                              ## origin/main を取り込んだ状態でゲートを回す（マージ前）
	$(PY) src/merge_gate.py

invariant:                         ## 登録簿の事前登録セルと凍結データが書き換わっていないか（枝 #14）
	$(PY) src/append_only.py --base origin/main

invariant-history:                 ## 全履歴を走査して不変性違反を洗い出す（枝 #14）
	$(PY) src/append_only.py --history

new-id:                            ## 衝突しない ID を採番する（枝 #14。make new-id ARGS="--count 3"）
	$(PY) src/new_id.py $(ARGS)

rules:                             ## ruleset（コードで直せない設定）を期待値と突合（枝 #14）
	$(PY) src/repo_rules.py

rules-live:                        ## gh api で実際の ruleset を取得して突合（ネットワーク要）
	$(PY) src/repo_rules.py --live

network:                           ## 埋め込みグラフ 297 ノード / 597 エッジの全件検証
	$(PY) src/verify_network.py

doc:                               ## 手書き本文の数値が機械出力と一致するかの照合
	$(PY) src/verify_doc.py

work-status:                       ## 並列作業キューのclaim状況を表示（状態は .work_scheduler/ に保存）
	$(PY) src/work_scheduler.py status

determ:                            ## 2 回実行して生成物が一致することの確認
	$(PY) src/check_determinism.py

interactive:                       ## 凍結データからグラフネットワーク確認用 HTML を再生成
	$(PY) src/build_interactive_html.py

clean:
	rm -rf outputs/*.csv outputs/*.json outputs/*.md outputs/*.sha256 src/__pycache__
