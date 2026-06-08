# SHARP

SHARP (Self-Healing Anchor Resolution Protocol) is a Python prototype for resolving broken folder references with content fingerprints instead of fixed paths. It can anchor a folder, search candidate locations, score content similarity, and recover moved, renamed, or remounted directories.

## Repository Layout

```text
sharp/      Core package and CLI
scripts/    Dataset, experiment, and figure-generation scripts
results/    Final experiment outputs and generated result figures
data/       Local datasets, ignored by Git
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

The core resolver uses only the Python standard library. `matplotlib` is needed only for regenerating figures.

## CLI Usage

```powershell
python -m sharp.cli add thesis C:\path\to\folder
python -m sharp.cli resolve thesis --root C:\search\root
python -m sharp.cli go thesis --root C:\search\root
python -m sharp.cli doctor
```

The anchor store defaults to `.sharp_anchors.json`, which is ignored because it is local runtime state.

## Run Experiments

Synthetic smoke run:

```powershell
python .\scripts\experiment.py --n 40 --out .\results\synthetic_results.json
```

Real-data evaluation after preparing the local corpus:

```powershell
python .\scripts\download_dataset.py --data-dir .\data --extract --sample-projects 500
python .\scripts\experiment_realdata.py --mode snapshot --corpus .\data\java_projects --n 200 --projects-glob * --seeds 11,17,23,31,47 --out .\results\realdata_n200_5seed.json
```

Regenerate figures:

```powershell
python .\scripts\make_figures.py --results .\results\realdata_n200_5seed.json --out-dir .\results\figures
```

## Results

Final outputs are committed under `results/`, including:

- `results/realdata_n200_5seed.json`
- `results/realdata_validation_calibrated.json`
- `results/synthetic_results.json`
- `results/figures/`

Large raw datasets stay local under `data/` and are intentionally ignored.
