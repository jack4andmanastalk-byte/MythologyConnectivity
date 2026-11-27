# Peer-Review Summary: Comparative Mythology Network Verification (v18 / v18.1)

**Research Question**: Does the previously reported Layer 2 (Kingship, Ritual, and Regalia; 15 dimensions) connectivity across 297 Eurasian mythological nodes (52 *Kojiki* episodes plus comparative traditions) reflect genuine structural signal grounded in textual evidence, or is it an artifact of coding design, uncalibrated similarity metrics, and graph composition?

**Principal Conclusions**:
1. **No statistically supportable signal is found in Layer 2 (15D)**: The null hypothesis cannot be rejected on the calibrated primary endpoint (`mean_best_match_z` = 3.020 vs null 3.024 ± 0.100, p = 0.498, Cohen's d = −0.04; ordinalized legacy v17 weights likewise yield 2.473 vs 2.470 ± 0.063, p = 0.502, d = 0.04).
2. **Positive control confirms pipeline sensitivity on Layer 1 (75D)**: On the frozen Layer 1 matrix, both raw cosine (0.761 vs 0.600 ± 0.012, p = 0.005, d = 13.83) and calibrated z (5.268 vs 4.684 ± 0.104, p = 0.005, d = 5.61) remain significant even after Holm correction across all 3 hypothesis branches (first threshold 0.0167).
3. **Conclusion robustness under vocabulary-independent coding (`pass C`)**: Replacing 13 double-coded *Kojiki* episodes with blind ratings scored under a proper-noun-free operational vocabulary (`L2_ALT_V1`, `pass C`) shifts agreement down by 0.220 (α = 0.954 → 0.734 on 195 paired cells) while preserving the null Layer 2 result (2.786 vs 2.855 ± 0.105, p = 0.751, d = −0.65).

---

## 1. Structural Audit of the Legacy v17 System & Display-Mix Policy

An AST-based full audit (`src/verify_network.py`: 60 checks total; OK 40, WARN 7, NG 0, INFO 13) of the frozen v17 interactive HTML (297 nodes, 597 edges) uncovered critical architectural discrepancies:

* **Graph mismatch (Check C5)**: The 597 displayed HTML edges are not the reported 90D joint graph (504 edges; overlap 393, 90D-only 111, display-only 204), but an overlay of Layer 1 (`v16`) edges with Layer 2 edges restricted around *Kojiki* and LP anchors.
* **21-Episode Display Mix Resolution (ADR 0003 / Branch #5 `NET-DISPLAY-21`)**: Among 248 Layer-1-evaluable nodes, 21 episodes (all within the 52 *Kojiki* nodes) exhibit display vs edge-replay discrepancies exceeding 0.01 (largest gap at `K1-05`: displayed 0.707 vs replayed 0.2332, diff −0.4738) because the HTML displays weighted 3-layer decomposition totals (`decomp.total_final`). Per ADR 0003, the frozen HTML is preserved unaltered; full 297-node provenance (`v16.L1` 244, `decomp.total_final` 37, `pureL2_dom` 16) and the 21 gap records are formalized in `derived/html_embedded_v17_audit.json` and continuously verified by Check `F10` (21 / 21 exact match).

## 2. Harness-Driven Re-Verification Design (v18 / v18.1)

* **Zero hardcoded parameters**: All vocabularies, thresholds, and parameters are centralized in `config/analysis.json` (`src/audit_no_hardcode.py`: 0 disallowed numeric literals across 12 scripts).
* **Evidence-grounded coding (`0–3`)**: Every non-zero score requires ≥ 6 characters of primary-text quotation (`src/validate.py`: 0 errors across 6 annotation files / 137 records; 25 *Kojiki* targets retain non-zero Layer 2 profiles, 106 non-zero cells, mean 1.54 active dimensions/episode vs legacy 30 targets / 166 cells).
* **Why explained-variance ratio fails**: For 9 single-motif episodes, matching a single dimension at maximum level saturates explained ratio at 100% (single-motif mean 86.06%, multi-motif mean 51.04%, 14 episodes with 0 eligible parents). Therefore, the preregistered primary endpoint calibrates the maximum match against the empirical cosine distribution over eligible parents (`z`-score) under dimension-permutation nulls (`n_perm` = 200, seed 42).

---

## 3. Core Empirical Results

### 3.1 Hypothesis Tests (Layer 2 & Layer 1)

| Pipeline | Layer | Endpoint | Observed | Null Mean ± SD | p-value | Effect d | Mean Explained (Null) | Edges |
| :--- | :---: | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `v18_calibrated` (primary) | L2 | `mean_best_match_z` | 3.020 | 3.024 ± 0.100 | 0.498 | −0.04 | 43.01% (40.51%) | 51 |
| `legacy_v17_calibrated` | L2 | `mean_best_match_z` | 2.473 | 2.470 ± 0.063 | 0.502 | 0.04 | 42.36% (39.83%) | 58 |
| `v18_cosine_reference` | L2 | `mean_best_cosine` | 0.812 | 0.772 ± 0.022 | 0.040 | 1.83 | 48.20% (45.14%) | 71 |
| `v18_passC_calibrated` | L2 | `mean_best_match_z` | 2.786 | 2.855 ± 0.105 | 0.751 | −0.65 | 36.16% (36.26%) | 47 |
| `l1_legacy_cosine` (pos. ctrl) | L1 | `mean_best_cosine` | 0.761 | 0.600 ± 0.012 | 0.005 | 13.83 | 89.87% (66.77%) | 491 |
| `l1_legacy_calibrated` (pos. ctrl) | L1 | `mean_best_match_z` | 5.268 | 4.684 ± 0.104 | 0.005 | 5.61 | 93.98% (87.75%) | 695 |

The apparent signal in uncalibrated cosine (`p = 0.040`, `d = 1.83`) reflects sparse-vector geometry rather than motif specificity and vanishes under parent-pool z-calibration (`p = 0.498`, `d = −0.04`). Zero of 25 *Kojiki* nodes pass BH-FDR, and seed robustness (seeds 42/43/44: p = 0.498 / 0.493 / 0.517) and parameter sweeps confirm invariance.

### 3.2 Inter-Rater Reliability & Vocabulary Independence (`pass A / B / C`)

| Comparison | Cells | Krippendorff α | Exact Match | Within ±1 |
| :--- | ---: | ---: | ---: | ---: |
| `pass A vs pass B` (same vocab, 37 eps 0-padded) | 555 | 0.755 | 95.68% | 98.38% |
| `pass A vs v17 legacy` (37 episodes) | 555 | 0.498 | 82.88% | 93.51% |
| `L1 audit vs v16 frozen` (12 eps × 10D) | 120 | 0.689 | 71.67% | 89.17% |
| `pass A vs pass B` (13 double-coded eps only) | 195 | 0.954 | 97.44% | 100.00% |
| `pass A vs pass C` (neutral defs `L2_ALT_V1`) | 195 | 0.734 | 80.00% | 94.87% |
| `pass B vs pass C` (neutral defs `L2_ALT_V1`) | 195 | 0.713 | 78.97% | 94.36% |

Shifting from the original vocabulary (`pass A`) to proper-noun-free operational definitions (`pass C`) lowers Krippendorff's α by 0.220 (0.954 → 0.734 on the identical 195 cells) and exact agreement from 97.44% to 80.00%. While α = 0.734 remains above the tentative acceptability floor (0.667), the drop quantifies sensitivity to exemplar-laden wording.

---

## 4. Governance, Limitations & Reproducibility

* **Multi-branch CI Governance (ADR 0002 / `src/check_registry.py`)**: Of 7 registered branches, 3 are formal hypothesis tests (`L2-15D`, `L1-75D`, `L2-PASSC-SENS`), setting α = 0.05 Holm's first threshold to 0.0167 and requiring `n_perm >= 59` (configured `n_perm` = 200). As quantified by `src/sim_swarm_review.py`, increasing ensemble raters R = 1 → 10 cannot remove shared bias (at b = 0.10, RMSE stalls at 0.141 → 0.105), whereas running 144 unregistered branches yields family-wise error 0.9994 and median minimum p = 0.0048. Timestamp validation (`src/check_prereg.py`) and Holm/permutation checks are therefore enforced as hard CI gates.
* **Limitations**: Statistical power with 25 active *Kojiki* profiles (1.54 active dimensions/episode) rules out large effects rather than proving zero effect; passes A/B/C share single-session LLM lineage rather than independent domain experts; spatial/temporal coordinates remain coarse approximations.
* **Determinism & Doc Verification**: `make clean && make all && make network && make determ && make registry` reproduces all 12 core artifacts identically across independent runs (0 byte mismatches), and `src/verify_doc.py` machine-verifies every reported statistic in this summary and the Japanese documents against JSON outputs.
