from __future__ import annotations

import argparse
import collections
import json
import math
import random
import shutil
import statistics
import tempfile
import time
from pathlib import Path

from sharp.fingerprint import fingerprint_folder
from sharp.similarity import classify, folder_similarity

DRIFT_LEVELS = [0.0, 0.05, 0.1, 0.25, 0.5]
SCENARIOS = ["S1_drive_change", "S2_new_machine", "S3_no_client_no_id", "S4_usb_remount", "S5_rename", "S6_content_drift"]
BUILD_FILES = {"pom.xml", "build.gradle", "settings.gradle", "gradle.properties", "build.xml", "ivy.xml", "maven.config"}


def find_projects(corpus: Path, projects_glob: str) -> list[Path]:
    projects = [path for path in corpus.glob(projects_glob) if path.is_dir()]
    if len(projects) < 2 and projects_glob != "*":
        projects = [path for path in corpus.glob("*") if path.is_dir()]
    return sorted(projects, key=lambda item: item.as_posix().lower())


def collect_text_lines(projects: list[Path], limit_files: int = 1500) -> list[str]:
    lines: list[str] = []
    seen = 0
    for project in projects:
        for file in project.rglob("*"):
            if seen >= limit_files:
                return lines or ["// fallback line"]
            if not file.is_file() or file.suffix.lower() not in {".java", ".txt", ".md", ".xml", ".gradle"}:
                continue
            try:
                text = file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            lines.extend(line.strip() for line in text.splitlines() if line.strip())
            seen += 1
    return lines or ["// fallback line"]


def drift_snapshot(source: Path, target: Path, drift: float, donor_lines: list[str], rng: random.Random) -> None:
    shutil.copytree(source, target)
    editable = [
        file for file in target.rglob("*")
        if file.is_file() and file.suffix.lower() in {".java", ".txt", ".md", ".xml", ".gradle"}
    ]
    if not editable:
        return
    edit_count = max(1, int(len(editable) * drift)) if drift > 0 else 0
    for file in rng.sample(editable, min(edit_count, len(editable))):
        try:
            lines = file.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        if not lines:
            continue
        replace_count = max(1, int(len(lines) * drift))
        for line_index in rng.sample(range(len(lines)), min(replace_count, len(lines))):
            lines[line_index] = rng.choice(donor_lines)
        file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    remove_count = int(len(editable) * drift * 0.25)
    for file in rng.sample(editable, min(remove_count, len(editable))):
        try:
            file.unlink()
        except OSError:
            pass

    add_count = int(len(editable) * drift * 0.25)
    for index in range(add_count):
        body = "\n".join(rng.choice(donor_lines) for _ in range(30)) + "\n"
        (target / f"sharp_added_{index:03d}.java").write_text(body, encoding="utf-8")


def metrics(rows: list[dict], tau_high: float = 0.82, score_key: str = "score") -> dict:
    positives = [row for row in rows if row["is_true_match"]]
    negatives = [row for row in rows if not row["is_true_match"]]
    accepted_true = [row for row in positives if row[score_key] >= tau_high]
    accepted_false = [row for row in negatives if row[score_key] >= tau_high]
    return {
        "recovery_accuracy": len(accepted_true) / len(positives) if positives else 0.0,
        "false_match_rate": len(accepted_false) / len(negatives) if negatives else 0.0,
        "true_pairs": len(positives),
        "decoy_pairs": len(negatives),
    }


def calibrate_threshold(rows: list[dict], max_fmr: float = 0.005) -> dict:
    sweep = threshold_sweep(rows)
    feasible = [point for point in sweep if point["false_match_rate"] <= max_fmr]
    if not feasible:
        chosen = min(sweep, key=lambda point: point["false_match_rate"])
    else:
        best_accuracy = max(point["accuracy"] for point in feasible)
        near_best = [point for point in feasible if point["accuracy"] >= best_accuracy - 0.005]
        chosen = max(near_best, key=lambda point: point["tau"])
    return {
        "tau_high": chosen["tau"],
        "max_fmr": max_fmr,
        "calibration_accuracy": chosen["accuracy"],
        "calibration_false_match_rate": chosen["false_match_rate"],
    }


def name_hint_score(reference: Path, candidate: str, score: float) -> float:
    ref_name = reference.name.lower()
    candidate_name = Path(candidate).name.lower()
    if ref_name and ref_name in candidate_name:
        return min(1.0, score + 0.03)
    return score


def token_set(text: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return {part for part in cleaned.split() if len(part) > 1}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def cosine_counter(left: collections.Counter, right: collections.Counter) -> float:
    keys = set(left) | set(right)
    if not keys:
        return 1.0
    dot = sum(left[key] * right[key] for key in keys)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def project_profile(project: Path) -> dict:
    build_files = set()
    extensions: collections.Counter = collections.Counter()
    lexical_tokens = set(token_set(project.name))
    for file in project.rglob("*"):
        if not file.is_file():
            continue
        lower_name = file.name.lower()
        if lower_name in BUILD_FILES:
            build_files.add(lower_name)
        if file.suffix:
            extensions[file.suffix.lower()] += 1
        lexical_tokens.update(token_set(file.stem))
    return {
        "name_tokens": token_set(project.name),
        "build_files": build_files,
        "extensions": extensions,
        "lexical_tokens": lexical_tokens,
    }


def profile_similarity(left: dict, right: dict) -> float:
    return (
        0.30 * jaccard(left["name_tokens"], right["name_tokens"])
        + 0.25 * jaccard(left["build_files"], right["build_files"])
        + 0.25 * jaccard(left["lexical_tokens"], right["lexical_tokens"])
        + 0.20 * cosine_counter(left["extensions"], right["extensions"])
    )


def threshold_sweep(rows: list[dict], score_key: str = "score") -> list[dict]:
    points = []
    positives = [row for row in rows if row["is_true_match"]]
    negatives = [row for row in rows if not row["is_true_match"]]
    for index in range(101):
        tau = index / 100
        tp = sum(1 for row in positives if row[score_key] >= tau)
        fp = sum(1 for row in negatives if row[score_key] >= tau)
        points.append({
            "tau": tau,
            "accuracy": tp / len(positives) if positives else 0.0,
            "false_match_rate": fp / len(negatives) if negatives else 0.0,
        })
    return points


def auc(points: list[dict]) -> float:
    roc = sorted((point["false_match_rate"], point["accuracy"]) for point in points)
    total = 0.0
    for (x1, y1), (x2, y2) in zip(roc, roc[1:]):
        total += (x2 - x1) * ((y1 + y2) / 2)
    return total


def path_baseline_success(scenario: str) -> float:
    stored_path_still_exists = scenario == "S6"
    return 1.0 if stored_path_still_exists else 0.0


def identifier_baseline_success(scenario: str) -> float:
    external_identifier_available = scenario != "S3"
    return 1.0 if external_identifier_available else 0.0


def scenario_results(rows: list[dict], tau_high: float) -> list[dict]:
    drift0 = [row for row in rows if row["is_true_match"] and row["drift"] == 0.0]
    drift_all = [row for row in rows if row["is_true_match"]]
    sharp_no_drift = metrics(drift0, tau_high)["recovery_accuracy"]
    sharp_drift = metrics(drift_all, tau_high)["recovery_accuracy"]
    scenarios = [
        ("S1", "Drive-letter change", sharp_no_drift),
        ("S2", "New machine", sharp_no_drift),
        ("S3", "No client / no ID", sharp_no_drift),
        ("S4", "USB remount", sharp_no_drift),
        ("S5", "Rename", sharp_no_drift),
        ("S6", "Content drift", sharp_drift),
    ]
    return [
        {
            "scenario": scenario,
            "label": label,
            "sharp": sharp_score,
            "path": path_baseline_success(scenario),
            "identifier": identifier_baseline_success(scenario),
        }
        for scenario, label, sharp_score in scenarios
    ]


def latency_profile(projects: list[Path], fps: dict[str, object]) -> dict:
    folder_points = []
    for project in projects:
        start = time.perf_counter()
        fingerprint_folder(project)
        elapsed = time.perf_counter() - start
        file_count = sum(1 for item in project.rglob("*") if item.is_file())
        folder_points.append({"folder": project.as_posix(), "file_count": file_count, "seconds": elapsed})

    pool_points = []
    pool_sizes = [size for size in [5, 10, 20, 40, 80] if size <= len(projects)]
    for pool_size in pool_sizes:
        elapsed_values = []
        pool = projects[:pool_size]
        for query in projects[: min(10, len(projects))]:
            start = time.perf_counter()
            for candidate in pool:
                folder_similarity(fps[query.as_posix()], fps[candidate.as_posix()])
            elapsed_values.append(time.perf_counter() - start)
        pool_points.append({
            "candidate_pool_size": pool_size,
            "seconds": sum(elapsed_values) / len(elapsed_values) if elapsed_values else 0.0,
        })

    return {"fingerprint": folder_points, "resolution": pool_points}


def hard_decoy_map(
    projects: list[Path],
    decoy_pool: list[Path],
    fps: dict[str, object],
    profiles: dict[str, dict],
    profile_top_k: int = 24,
) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for project in projects:
        profile_ranked = []
        for candidate in decoy_pool:
            if candidate == project:
                continue
            profile_score = profile_similarity(profiles[project.as_posix()], profiles[candidate.as_posix()])
            profile_ranked.append((profile_score, candidate))
        profile_ranked.sort(reverse=True, key=lambda item: item[0])
        ranked = []
        for profile_score, candidate in profile_ranked[:profile_top_k]:
            if candidate.as_posix() not in fps:
                fps[candidate.as_posix()] = fingerprint_folder(candidate)
            content_score = folder_similarity(fps[project.as_posix()], fps[candidate.as_posix()])
            score = (0.55 * content_score) + (0.45 * profile_score)
            ranked.append((score, candidate))
        ranked.sort(reverse=True, key=lambda item: item[0])
        mapping[project.as_posix()] = ranked[0][1]
    return mapping


def add_decoy_row(rows: list[dict], project: Path, decoy: Path, drift: float, fps: dict[str, object], kind: str) -> None:
    decoy_score = folder_similarity(fps[project.as_posix()], fps[decoy.as_posix()])
    rows.append({
        "mode": "real_snapshot",
        "scenario": "decoy",
        "decoy_kind": kind,
        "drift": drift,
        "reference": project.as_posix(),
        "candidate": decoy.as_posix(),
        "score": decoy_score,
        "score_with_name_hint": name_hint_score(project, decoy.as_posix(), decoy_score),
        "decision": classify(decoy_score).label,
        "is_true_match": False,
    })


def summarize_rows(rows: list[dict], tau_high: float) -> dict:
    by_drift = {}
    for drift in DRIFT_LEVELS:
        level_rows = [row for row in rows if row["drift"] == drift]
        true_scores = [row["score"] for row in level_rows if row["is_true_match"]]
        easy_scores = [row["score"] for row in level_rows if row.get("decoy_kind") == "easy"]
        hard_scores = [row["score"] for row in level_rows if row.get("decoy_kind") == "hard"]
        by_drift[str(drift)] = metrics(level_rows, tau_high) | {
            "easy_false_match_rate": metrics([row for row in level_rows if row["is_true_match"] or row.get("decoy_kind") == "easy"], tau_high)["false_match_rate"],
            "hard_false_match_rate": metrics([row for row in level_rows if row["is_true_match"] or row.get("decoy_kind") == "hard"], tau_high)["false_match_rate"],
            "mean_true_similarity": sum(true_scores) / len(true_scores) if true_scores else 0.0,
            "mean_easy_decoy_similarity": sum(easy_scores) / len(easy_scores) if easy_scores else 0.0,
            "mean_hard_decoy_similarity": sum(hard_scores) / len(hard_scores) if hard_scores else 0.0,
        }

    easy_rows = [row for row in rows if row["is_true_match"] or row.get("decoy_kind") == "easy"]
    hard_rows = [row for row in rows if row["is_true_match"] or row.get("decoy_kind") == "hard"]
    return {
        "summary": metrics(rows, tau_high),
        "easy_decoy_summary": metrics(easy_rows, tau_high),
        "hard_decoy_summary": metrics(hard_rows, tau_high),
        "by_drift": by_drift,
    }


def failure_analysis(rows: list[dict], tau_high: float) -> list[dict]:
    failures = [row for row in rows if row["is_true_match"] and row["score"] < tau_high]
    buckets = [
        ("heavy_drift", lambda row: row["drift"] >= 0.5, "Content drift at or above 50% drops below the conservative threshold."),
        ("moderate_drift", lambda row: 0.1 <= row["drift"] < 0.5, "Some moderately edited folders lose enough sampled content overlap to fall below threshold."),
        ("low_similarity", lambda row: row["score"] < 0.7, "The query and stored fingerprint share too little content after edits/additions/deletions."),
    ]
    analysis = []
    for name, predicate, explanation in buckets:
        matching = [row for row in failures if predicate(row)]
        analysis.append({
            "failure_type": name,
            "count": len(matching),
            "share_of_failures": len(matching) / len(failures) if failures else 0.0,
            "explanation": explanation,
        })
    return analysis


def run_trial(corpus: Path, n: int, projects_glob: str, seed: int, include_latency: bool, tau_high: float = 0.82) -> dict:
    all_projects = find_projects(corpus, projects_glob)
    if len(all_projects) < 2:
        raise SystemExit(f"need at least 2 projects under {corpus}; found {len(all_projects)}")
    rng = random.Random(seed)
    projects = rng.sample(all_projects, min(n, len(all_projects)))
    decoy_pool_size = min(len(all_projects), max(len(projects), 500))
    decoy_pool = rng.sample(all_projects, decoy_pool_size) if len(all_projects) > decoy_pool_size else list(all_projects)
    donor_lines = collect_text_lines(projects)
    fps = {}
    profiles = {}
    for project in set(projects + decoy_pool):
        profiles[project.as_posix()] = project_profile(project)
    for project in projects:
        fps[project.as_posix()] = fingerprint_folder(project)
    hard_decoys = hard_decoy_map(projects, decoy_pool, fps, profiles)
    rows: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="sharp_real_") as tmp:
        tmp_root = Path(tmp)
        for drift in DRIFT_LEVELS:
            for project in projects:
                query = tmp_root / f"{project.parent.name}_{project.name}_drift_{int(drift * 100)}"
                drift_snapshot(project, query, drift, donor_lines, rng)
                score = folder_similarity(fps[project.as_posix()], fingerprint_folder(query))
                hinted_score = name_hint_score(project, query.name, score)
                rows.append({
                    "mode": "real_snapshot",
                    "scenario": "content_drift",
                    "decoy_kind": "true",
                    "drift": drift,
                    "reference": project.as_posix(),
                    "candidate": query.name,
                    "score": score,
                    "score_with_name_hint": hinted_score,
                    "decision": classify(score).label,
                    "is_true_match": True,
                })

                decoy = rng.choice([item for item in projects if item != project])
                add_decoy_row(rows, project, decoy, drift, fps, "easy")
                add_decoy_row(rows, project, hard_decoys[project.as_posix()], drift, fps, "hard")

    sweep = threshold_sweep(rows)
    row_summary = summarize_rows(rows, tau_high)

    return {
        "dataset": "GitHub Java Corpus snapshot sample",
        "corpus": str(corpus.resolve()),
        "n_projects": len(projects),
        "seed": seed,
        "thresholds": {"tau_high": tau_high, "tau_low": 0.62},
        "summary": row_summary["summary"],
        "easy_decoy_summary": row_summary["easy_decoy_summary"],
        "hard_decoy_summary": row_summary["hard_decoy_summary"],
        "by_drift": row_summary["by_drift"],
        "scenario_results": scenario_results(rows, tau_high),
        "threshold_sweep": sweep,
        "roc": {"points": sweep, "auc": auc(sweep)},
        "ablation": [
            {"mode": "content_only", **metrics(rows, tau_high, score_key="score")},
            {"mode": "content_plus_name_hint", **metrics(rows, tau_high, score_key="score_with_name_hint")},
        ],
        "latency": latency_profile(projects, fps) if include_latency else {"fingerprint": [], "resolution": []},
        "failure_analysis": failure_analysis(rows, tau_high),
        "rows": rows,
    }


def mean_std(values: list[float]) -> dict:
    return {
        "mean": statistics.mean(values) if values else 0.0,
        "std": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def aggregate_trials(trials: list[dict]) -> dict:
    calibration = calibrate_threshold(trials[0]["rows"])
    tau_high = calibration["tau_high"]
    evaluation_trials = trials[1:] if len(trials) > 1 else trials
    combined_rows = [row for trial in evaluation_trials for row in trial["rows"]]
    row_summary = summarize_rows(combined_rows, tau_high)
    drift_series = {}
    for drift in DRIFT_LEVELS:
        key = str(drift)
        trial_summaries = [summarize_rows(trial["rows"], tau_high)["by_drift"][key] for trial in evaluation_trials]
        drift_series[key] = {
            "recovery_accuracy": mean_std([summary["recovery_accuracy"] for summary in trial_summaries]),
            "false_match_rate": mean_std([summary["false_match_rate"] for summary in trial_summaries]),
            "easy_false_match_rate": mean_std([summary["easy_false_match_rate"] for summary in trial_summaries]),
            "hard_false_match_rate": mean_std([summary["hard_false_match_rate"] for summary in trial_summaries]),
            "mean_true_similarity": mean_std([summary["mean_true_similarity"] for summary in trial_summaries]),
            "mean_easy_decoy_similarity": mean_std([summary["mean_easy_decoy_similarity"] for summary in trial_summaries]),
            "mean_hard_decoy_similarity": mean_std([summary["mean_hard_decoy_similarity"] for summary in trial_summaries]),
        }

    sweep_by_tau = {}
    for point in trials[0]["threshold_sweep"]:
        tau = point["tau"]
        matching = [[item for item in trial["threshold_sweep"] if item["tau"] == tau][0] for trial in evaluation_trials]
        sweep_by_tau[str(tau)] = {
            "tau": tau,
            "accuracy": mean_std([item["accuracy"] for item in matching]),
            "false_match_rate": mean_std([item["false_match_rate"] for item in matching]),
        }

    latency = trials[0]["latency"]
    return {
        "dataset": trials[0]["dataset"],
        "corpus": trials[0]["corpus"],
        "n_projects": trials[0]["n_projects"],
        "seeds": [trial["seed"] for trial in trials],
        "calibration_seed": trials[0]["seed"],
        "evaluation_seeds": [trial["seed"] for trial in evaluation_trials],
        "threshold_calibration": calibration,
        "thresholds": {"tau_high": tau_high, "tau_low": 0.62},
        "summary": row_summary["summary"],
        "easy_decoy_summary": row_summary["easy_decoy_summary"],
        "hard_decoy_summary": row_summary["hard_decoy_summary"],
        "by_drift": row_summary["by_drift"],
        "drift_series": drift_series,
        "scenario_results": scenario_results(combined_rows, tau_high),
        "threshold_sweep": threshold_sweep(combined_rows),
        "threshold_series": list(sweep_by_tau.values()),
        "roc": {"points": threshold_sweep(combined_rows), "auc": auc(threshold_sweep(combined_rows))},
        "ablation": [
            {"mode": "content_only", **metrics(combined_rows, tau_high, score_key="score")},
            {"mode": "content_plus_name_hint", **metrics(combined_rows, tau_high, score_key="score_with_name_hint")},
        ],
        "latency": latency,
        "failure_analysis": failure_analysis(combined_rows, tau_high),
        "trial_summaries": [
            {
                "seed": trial["seed"],
                "summary": summarize_rows(trial["rows"], tau_high)["summary"],
                "easy_decoy_summary": summarize_rows(trial["rows"], tau_high)["easy_decoy_summary"],
                "hard_decoy_summary": summarize_rows(trial["rows"], tau_high)["hard_decoy_summary"],
                "by_drift": summarize_rows(trial["rows"], tau_high)["by_drift"],
            }
            for trial in trials
        ],
        "rows": combined_rows,
    }


def run_snapshot(corpus: Path, n: int, projects_glob: str, seeds: list[int]) -> dict:
    trials = []
    for index, seed in enumerate(seeds):
        print(f"running trial seed={seed} ({index + 1}/{len(seeds)})")
        trials.append(run_trial(corpus, n, projects_glob, seed, include_latency=index == 0))
    if len(trials) == 1:
        return trials[0]
    return aggregate_trials(trials)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["snapshot"], default="snapshot")
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--n", type=int, default=80)
    parser.add_argument("--projects-glob", default="*/*")
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--seeds", default="", help="comma-separated seeds for repeated runs, e.g. 11,17,23,31,47")
    parser.add_argument("--out", default="../results/realdata_results.json")
    args = parser.parse_args()

    seeds = [int(item.strip()) for item in args.seeds.split(",") if item.strip()] if args.seeds else [args.seed]
    results = run_snapshot(Path(args.corpus), args.n, args.projects_glob, seeds)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results["summary"], indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
