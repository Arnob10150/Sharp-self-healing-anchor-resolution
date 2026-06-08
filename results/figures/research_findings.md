# SHARP Research Findings

Dataset: GitHub Java Corpus snapshot sample
Projects: 200
Seeds: 11, 17, 23, 31, 47
Calibration seed: 11
Evaluation seeds: 17, 23, 31, 47
Calibrated tau_high: 0.64
Recovery accuracy: 0.989
False-match rate: 0.000
Easy-decoy false-match rate: 0.000
Hard-decoy false-match rate: 0.000
ROC AUC: 1.000

## Scenario Results

| Scenario | Meaning | SHARP | Path-based | Identifier-based |
|---|---|---:|---:|---:|
| S1 | Drive-letter change | 1.000 | 0.000 | 1.000 |
| S2 | New machine | 1.000 | 0.000 | 1.000 |
| S3 | No client / no ID | 1.000 | 0.000 | 0.000 |
| S4 | USB remount | 1.000 | 0.000 | 1.000 |
| S5 | Rename | 1.000 | 0.000 | 1.000 |
| S6 | Content drift | 0.989 | 1.000 | 1.000 |

## Drift Tolerance

| Drift | Recovery accuracy | Mean true similarity | Easy FMR | Hard FMR |
|---:|---:|---:|---:|---:|
| 0.00 | 1.000 +/- 0.000 | 1.000 +/- 0.000 | 0.000 +/- 0.000 | 0.000 +/- 0.000 |
| 0.05 | 1.000 +/- 0.000 | 0.986 +/- 0.002 | 0.000 +/- 0.000 | 0.000 +/- 0.000 |
| 0.10 | 1.000 +/- 0.000 | 0.970 +/- 0.002 | 0.000 +/- 0.000 | 0.000 +/- 0.000 |
| 0.25 | 0.994 +/- 0.006 | 0.896 +/- 0.003 | 0.000 +/- 0.000 | 0.000 +/- 0.000 |
| 0.50 | 0.951 +/- 0.017 | 0.720 +/- 0.005 | 0.000 +/- 0.000 | 0.000 +/- 0.000 |

## Figures

- fig1_recovery_by_scenario.png
- fig2_drift_tolerance.png
- fig3_similarity_distribution.png
- fig4_threshold_tradeoff.png
- fig5_roc.png
- fig6_latency.png
- fig7_ablation.png

## Failure Analysis

| Failure type | Count | Share | Explanation |
|---|---:|---:|---|
| heavy_drift | 39 | 0.886 | Content drift at or above 50% drops below the conservative threshold. |
| moderate_drift | 5 | 0.114 | Some moderately edited folders lose enough sampled content overlap to fall below threshold. |
| low_similarity | 44 | 1.000 | The query and stored fingerprint share too little content after edits/additions/deletions. |