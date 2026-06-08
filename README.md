# SHARP

SHARP (Self-Healing Anchor Resolution Protocol) is a Python prototype for resolving broken folder references using content fingerprints instead of fixed paths. It creates an anchor for a folder, searches candidate locations, compares folder fingerprints, and recovers references after common path changes such as renames, remounts, drive-letter changes, or migration to a new machine.

## Why SHARP

Traditional file references are fragile because they usually depend on paths or platform-specific identifiers. SHARP treats a folder's content fingerprint as its identity, allowing the resolver to find the same logical folder even when the original path is no longer valid.

The prototype focuses on:

- content-based folder fingerprinting
- candidate scanning across search roots
- similarity scoring and threshold-based decisions
- local anchor storage with write-back after recovery
- synthetic and real-data evaluation workflows

## Repository Structure

```text
sharp/       Core package and command-line resolver
scripts/     Dataset preparation, experiments, and figure generation
results/     Final JSON results and generated figures
data/        Local datasets, ignored by Git
```

Paper drafts, LaTeX files, raw datasets, and local research artifacts are intentionally ignored so the repository stays focused on code and final results.

## Installation

Create a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

Install the package locally:

```powershell
pip install -e .
```

Install plotting dependencies if you want to regenerate figures:

```powershell
pip install -r requirements.txt
```

The core resolver uses only the Python standard library. `matplotlib` is only required by `scripts/make_figures.py`.

## CLI Usage

Create an anchor:

```powershell
python -m sharp.cli add thesis C:\path\to\folder
```

Resolve an anchor by searching one or more roots:

```powershell
python -m sharp.cli resolve thesis --root C:\search\root
```

Print only the resolved path:

```powershell
python -m sharp.cli go thesis --root C:\search\root
```

Inspect the local anchor store:

```powershell
python -m sharp.cli doctor
```

By default, anchors are stored in `.sharp_anchors.json`. That file is local runtime state and is ignored by Git.

## Experiments

Run a synthetic smoke evaluation:

```powershell
python .\scripts\experiment.py --n 40 --out .\results\synthetic_results.json
```

Prepare a sampled Java corpus:

```powershell
python .\scripts\download_dataset.py --data-dir .\data --extract --sample-projects 500
```

Run the real-data evaluation:

```powershell
python .\scripts\experiment_realdata.py --mode snapshot --corpus .\data\java_projects --n 200 --projects-glob * --seeds 11,17,23,31,47 --out .\results\realdata_n200_5seed.json
```

Regenerate result figures:

```powershell
python .\scripts\make_figures.py --results .\results\realdata_n200_5seed.json --out-dir .\results\figures
```

## Results

The committed final run uses a sampled GitHub Java Corpus snapshot:

- Projects: 200
- Seeds: `11, 17, 23, 31, 47`
- Calibration seed: `11`
- Evaluation seeds: `17, 23, 31, 47`
- Calibrated `tau_high`: `0.64`
- Recovery accuracy: `0.989`
- False-match rate: `0.000`
- ROC AUC: `1.000`

Final result files:

- [results/realdata_n200_5seed.json](results/realdata_n200_5seed.json)
- [results/realdata_validation_calibrated.json](results/realdata_validation_calibrated.json)
- [results/synthetic_results.json](results/synthetic_results.json)
- [results/figures/research_findings.md](results/figures/research_findings.md)

## Figures

| Figure | Description |
|---|---|
| [Fig. 1](results/figures/fig1_recovery_by_scenario.png) | Recovery accuracy across path-change scenarios |
| [Fig. 2](results/figures/fig2_drift_tolerance.png) | Recovery under increasing content drift |
| [Fig. 3](results/figures/fig3_similarity_distribution.png) | True-match and decoy similarity distributions |
| [Fig. 4](results/figures/fig4_threshold_tradeoff.png) | Threshold trade-off curve |
| [Fig. 5](results/figures/fig5_roc.png) | ROC curve |
| [Fig. 6](results/figures/fig6_latency.png) | Resolution latency |
| [Fig. 7](results/figures/fig7_ablation.png) | Fingerprint ablation results |

## Development Checks

Compile-check the package and scripts:

```powershell
python -m compileall sharp scripts
```

Check Git state:

```powershell
git status
```

## License

No license has been selected yet. Add one before public reuse or redistribution.
