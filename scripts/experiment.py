from __future__ import annotations

import argparse
import json
import random
import shutil
import string
import tempfile
from pathlib import Path

from sharp.fingerprint import fingerprint_folder
from sharp.similarity import classify, folder_similarity

DRIFT_LEVELS = [0.0, 0.1, 0.25, 0.5]


def _words(seed: int, count: int = 200) -> list[str]:
    rng = random.Random(seed)
    base = ["anchor", "resolver", "volume", "fingerprint", "drift", "candidate", "hash", "folder"]
    return base + ["".join(rng.choices(string.ascii_lowercase, k=rng.randint(4, 10))) for _ in range(count)]


def _write_project(root: Path, project_id: int, file_count: int = 10) -> None:
    rng = random.Random(project_id)
    vocab = _words(project_id)
    root.mkdir(parents=True, exist_ok=True)
    for index in range(file_count):
        lines = []
        for line_no in range(35):
            picked = " ".join(rng.choice(vocab) for _ in range(8))
            lines.append(f"// p{project_id} f{index} l{line_no} {picked}\n")
        (root / f"src_{index:02d}.java").write_text("".join(lines), encoding="utf-8")


def _drift_project(source: Path, target: Path, drift: float, donor_lines: list[str]) -> None:
    shutil.copytree(source, target)
    rng = random.Random(hash((source.name, drift)) & 0xFFFFFFFF)
    files = sorted(target.glob("*.java"))
    edit_count = int(len(files) * drift)
    remove_count = int(len(files) * drift * 0.4)
    add_count = int(len(files) * drift * 0.6)

    for file in rng.sample(files, min(edit_count, len(files))):
        lines = file.read_text(encoding="utf-8").splitlines()
        replace_count = max(1, int(len(lines) * drift))
        for line_index in rng.sample(range(len(lines)), min(replace_count, len(lines))):
            lines[line_index] = rng.choice(donor_lines)
        file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    remaining = sorted(target.glob("*.java"))
    for file in rng.sample(remaining, min(remove_count, len(remaining))):
        file.unlink()

    for index in range(add_count):
        body = "\n".join(rng.choice(donor_lines) for _ in range(25)) + "\n"
        (target / f"added_{index:02d}.java").write_text(body, encoding="utf-8")


def _metrics(rows: list[dict], tau_high: float = 0.82) -> dict:
    positives = [row for row in rows if row["is_true_match"]]
    negatives = [row for row in rows if not row["is_true_match"]]
    accepted_true = [row for row in positives if row["score"] >= tau_high]
    accepted_false = [row for row in negatives if row["score"] >= tau_high]
    return {
        "recovery_accuracy": len(accepted_true) / len(positives) if positives else 0.0,
        "false_match_rate": len(accepted_false) / len(negatives) if negatives else 0.0,
        "true_pairs": len(positives),
        "decoy_pairs": len(negatives),
    }


def run(n: int, seed: int) -> dict:
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory(prefix="sharp_synth_") as tmp:
        base = Path(tmp)
        corpus = base / "corpus"
        queries = base / "queries"
        corpus.mkdir()
        queries.mkdir()

        projects = []
        for project_id in range(n):
            root = corpus / f"project_{project_id:03d}"
            _write_project(root, project_id)
            projects.append(root)

        donor_lines = []
        for file in corpus.glob("*/*.java"):
            donor_lines.extend(file.read_text(encoding="utf-8").splitlines())
        rng.shuffle(donor_lines)

        fps = {project.name: fingerprint_folder(project) for project in projects}
        rows: list[dict] = []

        for drift in DRIFT_LEVELS:
            for project in projects:
                query = queries / f"{project.name}_drift_{int(drift * 100)}"
                _drift_project(project, query, drift, donor_lines)
                query_fp = fingerprint_folder(query)
                true_score = folder_similarity(fps[project.name], query_fp)
                rows.append({
                    "mode": "synthetic",
                    "scenario": "content_drift",
                    "drift": drift,
                    "reference": project.name,
                    "candidate": query.name,
                    "score": true_score,
                    "decision": classify(true_score).label,
                    "is_true_match": True,
                })

                decoy = rng.choice([item for item in projects if item != project])
                decoy_score = folder_similarity(fps[project.name], fps[decoy.name])
                rows.append({
                    "mode": "synthetic",
                    "scenario": "decoy",
                    "drift": drift,
                    "reference": project.name,
                    "candidate": decoy.name,
                    "score": decoy_score,
                    "decision": classify(decoy_score).label,
                    "is_true_match": False,
                })

        by_drift = {}
        for drift in DRIFT_LEVELS:
            by_drift[str(drift)] = _metrics([row for row in rows if row["drift"] == drift])

        return {
            "dataset": "controlled synthetic supplement",
            "n_projects": n,
            "seed": seed,
            "thresholds": {"tau_high": 0.82, "tau_low": 0.62},
            "summary": _metrics(rows),
            "by_drift": by_drift,
            "rows": rows,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default="../results/synthetic_results.json")
    args = parser.parse_args()

    results = run(args.n, args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results["summary"], indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
