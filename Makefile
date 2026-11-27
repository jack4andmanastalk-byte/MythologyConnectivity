PY ?= python3

.PHONY: all prereg registry validate audit sim run network doc determ clean

all: prereg registry validate audit sim run doc    ## 事前登録 → 登録簿 → 検証 → 監査 → 運用シミュレーション → 全解析 → 文書照合

prereg:                            ## 事前登録が結果より先に固定されたか（git 履歴）
	$(PY) src/check_prereg.py

registry:                          ## 登録簿の枝数から Holm しきい値・必要置換回数を算出・検査
	$(PY) src/check_registry.py

validate:                          ## アノテーションのスキーマ・証拠・重複検査
	$(PY) src/validate.py

audit:                             ## 解析定数がコードに漏れていないことの AST 監査
	$(PY) src/audit_no_hardcode.py

sim:                               ## 多モデル並列レビューの誤差訂正能力の評価（ADR 0002 の数値）
	$(PY) src/sim_swarm_review.py

run: prereg registry validate audit sim  ## 全解析（results.json / report.md / manifest を生成）
	$(PY) src/run_all.py

network:                           ## 埋め込みグラフ 297 ノード / 597 エッジの全件検証
	$(PY) src/verify_network.py

doc:                               ## 手書き本文の数値が機械出力と一致するかの照合
	$(PY) src/verify_doc.py

determ:                            ## 2 回実行して生成物が一致することの確認
	$(PY) src/check_determinism.py

clean:
	rm -rf outputs/*.csv outputs/*.json outputs/*.md outputs/*.sha256 src/__pycache__
