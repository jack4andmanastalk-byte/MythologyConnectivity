PY ?= python3

.PHONY: all validate audit run network doc determ clean

all: validate audit run doc        ## 検証 → 監査 → 全解析（ネットワーク全件検証を含む）→ 文書照合

validate:                          ## アノテーションのスキーマ・証拠・重複検査
	$(PY) src/validate.py

audit:                             ## 解析定数がコードに漏れていないことの AST 監査
	$(PY) src/audit_no_hardcode.py

run: validate audit                ## 全解析（results.json / report.md / manifest を生成）
	$(PY) src/run_all.py

network:                           ## 埋め込みグラフ 297 ノード / 597 エッジの全件検証
	$(PY) src/verify_network.py

doc:                               ## 手書き本文の数値が機械出力と一致するかの照合
	$(PY) src/verify_doc.py

determ:                            ## 2 回実行して生成物が一致することの確認
	$(PY) src/check_determinism.py

clean:
	rm -rf outputs/*.csv outputs/*.json outputs/*.md outputs/*.sha256 src/__pycache__
