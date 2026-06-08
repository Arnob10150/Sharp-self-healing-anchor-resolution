from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


BLUE = "#1d4ed8"
RED = "#b91c1c"
GREEN = "#047857"
PURPLE = "#6d28d9"
GRAY = "#64748b"
DARK = "#0f172a"
LIGHT = "#e2e8f0"


plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "#cbd5e1",
    "axes.labelcolor": DARK,
    "axes.titlecolor": DARK,
    "axes.titlesize": 14,
    "axes.titleweight": "bold",
    "font.family": "DejaVu Sans",
    "font.size": 10.5,
    "grid.color": "#e5e7eb",
    "grid.linewidth": 0.8,
    "legend.frameon": False,
    "savefig.bbox": "tight",
})


def finish(path: Path) -> None:
    plt.tight_layout()
    plt.savefig(path, dpi=220)
    plt.close()


def clean_axes(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, axis="x", alpha=0.55)


def fig1_recovery_by_scenario(data: dict, out: Path) -> None:
    scenarios = data["scenario_results"]
    labels = [f"{item['scenario']}\n{item['label']}" for item in scenarios]
    y = list(range(len(labels)))
    fig, ax = plt.subplots(figsize=(9.8, 5.6))
    for idx, item in enumerate(scenarios):
        ax.hlines(idx, min(item["path"], item["identifier"], item["sharp"]), max(item["path"], item["identifier"], item["sharp"]), color=LIGHT, linewidth=3)
    ax.scatter([item["path"] for item in scenarios], y, label="Path-based", color=GRAY, s=70, marker="s")
    ax.scatter([item["identifier"] for item in scenarios], y, label="Identifier-based", color=GREEN, s=80, marker="^")
    ax.scatter([item["sharp"] for item in scenarios], y, label="SHARP", color=BLUE, s=95, marker="o")
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlim(-0.04, 1.04)
    ax.set_xlabel("Recovery accuracy")
    ax.set_title("Fig. 1: Recovery by scenario")
    ax.legend(loc="lower right")
    clean_axes(ax)
    finish(out / "fig1_recovery_by_scenario.png")


def fig2_drift_tolerance(data: dict, out: Path) -> None:
    drift_items = sorted(data["by_drift"].items(), key=lambda item: float(item[0]))
    drift = [float(key) * 100 for key, _ in drift_items]
    if "drift_series" in data:
        series = [data["drift_series"][key] for key, _ in drift_items]
        accuracy = [item["recovery_accuracy"]["mean"] for item in series]
        accuracy_err = [item["recovery_accuracy"]["std"] for item in series]
        similarity = [item["mean_true_similarity"]["mean"] for item in series]
        similarity_err = [item["mean_true_similarity"]["std"] for item in series]
    else:
        accuracy = [item["recovery_accuracy"] for _, item in drift_items]
        accuracy_err = None
        similarity = [item["mean_true_similarity"] for _, item in drift_items]
        similarity_err = None
    fig, ax = plt.subplots(figsize=(8.8, 5.6))
    ax.errorbar(drift, accuracy, yerr=accuracy_err, marker="o", label="Recovery accuracy", color=BLUE, linewidth=2.7, capsize=4)
    ax.errorbar(drift, similarity, yerr=similarity_err, marker="s", label="Mean true similarity", color=PURPLE, linewidth=2.7, capsize=4)
    ax.axvspan(25, 50, color="#fee2e2", alpha=0.34, label="high-drift stress zone")
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Content drift (%)")
    ax.set_ylabel("Score")
    ax.set_title("Fig. 2: Drift tolerance with cross-seed error bars")
    ax.legend(loc="lower left")
    ax.grid(True, alpha=0.45)
    finish(out / "fig2_drift_tolerance.png")


def fig3_similarity_distribution(data: dict, out: Path) -> None:
    true_scores = [row["score"] for row in data["rows"] if row["is_true_match"]]
    easy_decoy_scores = [row["score"] for row in data["rows"] if row.get("decoy_kind") == "easy"]
    hard_decoy_scores = [row["score"] for row in data["rows"] if row.get("decoy_kind") == "hard"]
    tau = data["thresholds"]["tau_high"]
    fig, ax = plt.subplots(figsize=(8.8, 5.2))
    bins = [i / 40 for i in range(41)]
    ax.hist(easy_decoy_scores, bins=bins, alpha=0.45, label="Easy decoys", color=GRAY)
    ax.hist(hard_decoy_scores, bins=bins, alpha=0.55, label="Hard decoys", color=RED)
    ax.hist(true_scores, bins=bins, alpha=0.62, label="True matches", color=BLUE)
    ax.axvline(tau, color=DARK, linestyle="--", linewidth=2, label=f"calibrated tau={tau:.2f}")
    ax.set_xlabel("Similarity score")
    ax.set_ylabel("Pair count")
    ax.set_title("Fig. 3: True matches separate from easy and hard decoys")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.35)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    finish(out / "fig3_similarity_distribution.png")


def fig4_threshold_tradeoff(data: dict, out: Path) -> None:
    points = data.get("threshold_series") or data["threshold_sweep"]
    tau = [point["tau"] for point in points]
    if "threshold_series" in data:
        accuracy = [point["accuracy"]["mean"] for point in points]
        accuracy_std = [point["accuracy"]["std"] for point in points]
        fmr = [point["false_match_rate"]["mean"] for point in points]
        fmr_std = [point["false_match_rate"]["std"] for point in points]
    else:
        accuracy = [point["accuracy"] for point in points]
        accuracy_std = [0.0 for _ in points]
        fmr = [point["false_match_rate"] for point in points]
        fmr_std = [0.0 for _ in points]
    fig, ax = plt.subplots(figsize=(8.8, 5.2))
    ax.plot(tau, accuracy, label="Recovery accuracy", color=BLUE, linewidth=2.7)
    ax.plot(tau, fmr, label="False-match rate", color=RED, linewidth=2.7)
    ax.fill_between(tau, [max(0, y - e) for y, e in zip(accuracy, accuracy_std)], [min(1, y + e) for y, e in zip(accuracy, accuracy_std)], color=BLUE, alpha=0.14)
    ax.fill_between(tau, [max(0, y - e) for y, e in zip(fmr, fmr_std)], [min(1, y + e) for y, e in zip(fmr, fmr_std)], color=RED, alpha=0.14)
    ax.axvline(data["thresholds"]["tau_high"], color=DARK, linestyle="--", linewidth=1.9, label=f"held-out tau={data['thresholds']['tau_high']:.2f}")
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Threshold tau")
    ax.set_ylabel("Rate")
    ax.set_title("Fig. 4: Threshold tradeoff on held-out seeds", pad=44)
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, 1.02),
        ncol=3,
        handlelength=2.5,
        columnspacing=1.25,
    )
    ax.grid(True, alpha=0.45)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    finish(out / "fig4_threshold_tradeoff.png")


def fig5_roc(data: dict, out: Path) -> None:
    points = sorted(data["roc"]["points"], key=lambda point: point["false_match_rate"])
    x = [point["false_match_rate"] for point in points]
    y = [point["accuracy"] for point in points]
    fig, ax = plt.subplots(figsize=(6.6, 5.8))
    ax.plot(x, y, color=BLUE, linewidth=2.8, label=f"AUC={data['roc']['auc']:.3f}")
    ax.fill_between(x, y, color=BLUE, alpha=0.10)
    ax.plot([0, 1], [0, 1], color=GRAY, linestyle="--", linewidth=1.5)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.set_xlabel("False-accept rate")
    ax.set_ylabel("True-accept rate")
    ax.set_title("Fig. 5: ROC curve")
    ax.legend(loc="lower right")
    ax.grid(True, alpha=0.35)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    finish(out / "fig5_roc.png")


def fig6_latency(data: dict, out: Path) -> None:
    latency = data["latency"]
    folder_points = sorted(latency["fingerprint"], key=lambda item: item["file_count"])
    pool_points = sorted(latency["resolution"], key=lambda item: item["candidate_pool_size"])
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8))
    axes[0].scatter(
        [item["file_count"] for item in folder_points],
        [item["seconds"] for item in folder_points],
        color=BLUE,
        alpha=0.75,
    )
    axes[0].set_xlabel("Folder size (files)")
    axes[0].set_ylabel("Fingerprint time (s)")
    axes[0].set_title("Fingerprinting")
    axes[0].grid(alpha=0.35)
    axes[0].spines["top"].set_visible(False)
    axes[0].spines["right"].set_visible(False)
    axes[1].plot(
        [item["candidate_pool_size"] for item in pool_points],
        [item["seconds"] for item in pool_points],
        marker="o",
        color=GREEN,
        linewidth=2.5,
    )
    axes[1].set_xlabel("Candidate pool size")
    axes[1].set_ylabel("Resolution scoring time (s)")
    axes[1].set_title("Resolution")
    axes[1].grid(alpha=0.35)
    axes[1].spines["top"].set_visible(False)
    axes[1].spines["right"].set_visible(False)
    fig.suptitle("Fig. 6: Latency")
    finish(out / "fig6_latency.png")


def fig7_ablation(data: dict, out: Path) -> None:
    ablation = data["ablation"]
    labels = [item["mode"].replace("_", " + ") for item in ablation]
    y = list(range(len(labels)))
    fig, ax = plt.subplots(figsize=(7.8, 4.7))
    for idx, item in enumerate(ablation):
        ax.hlines(idx, item["false_match_rate"], item["recovery_accuracy"], color=LIGHT, linewidth=4)
    ax.scatter([item["false_match_rate"] for item in ablation], y, color=RED, label="False-match rate", s=90, marker="x")
    ax.scatter([item["recovery_accuracy"] for item in ablation], y, color=BLUE, label="Recovery accuracy", s=100)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlim(-0.04, 1.04)
    ax.set_xlabel("Rate")
    ax.set_title("Fig. 7: Ablation of name hint")
    ax.legend(loc="lower right")
    clean_axes(ax)
    finish(out / "fig7_ablation.png")


def write_findings(data: dict, out: Path) -> None:
    if "drift_series" in data:
        drift_lines = [
            (
                f"| {float(drift):.2f} | "
                f"{series['recovery_accuracy']['mean']:.3f} +/- {series['recovery_accuracy']['std']:.3f} | "
                f"{series['mean_true_similarity']['mean']:.3f} +/- {series['mean_true_similarity']['std']:.3f} | "
                f"{series['easy_false_match_rate']['mean']:.3f} +/- {series['easy_false_match_rate']['std']:.3f} | "
                f"{series['hard_false_match_rate']['mean']:.3f} +/- {series['hard_false_match_rate']['std']:.3f} |"
            )
            for drift, series in sorted(data["drift_series"].items(), key=lambda item: float(item[0]))
        ]
    else:
        drift_lines = [
            f"| {float(drift):.2f} | {summary['recovery_accuracy']:.3f} | {summary['mean_true_similarity']:.3f} | {summary.get('easy_false_match_rate', 0.0):.3f} | {summary.get('hard_false_match_rate', summary['false_match_rate']):.3f} |"
            for drift, summary in sorted(data["by_drift"].items(), key=lambda item: float(item[0]))
        ]
    scenario_lines = [
        f"| {item['scenario']} | {item['label']} | {item['sharp']:.3f} | {item['path']:.3f} | {item['identifier']:.3f} |"
        for item in data["scenario_results"]
    ]
    (out / "research_findings.md").write_text(
        "\n".join([
            "# SHARP Research Findings",
            "",
            f"Dataset: {data['dataset']}",
            f"Projects: {data['n_projects']}",
            f"Seeds: {', '.join(str(seed) for seed in data.get('seeds', [data.get('seed')]))}",
            f"Calibration seed: {data.get('calibration_seed', 'n/a')}",
            f"Evaluation seeds: {', '.join(str(seed) for seed in data.get('evaluation_seeds', data.get('seeds', [])))}",
            f"Calibrated tau_high: {data['thresholds']['tau_high']:.2f}",
            f"Recovery accuracy: {data['summary']['recovery_accuracy']:.3f}",
            f"False-match rate: {data['summary']['false_match_rate']:.3f}",
            f"Easy-decoy false-match rate: {data.get('easy_decoy_summary', {}).get('false_match_rate', 0.0):.3f}",
            f"Hard-decoy false-match rate: {data.get('hard_decoy_summary', {}).get('false_match_rate', 0.0):.3f}",
            f"ROC AUC: {data['roc']['auc']:.3f}",
            "",
            "## Scenario Results",
            "",
            "| Scenario | Meaning | SHARP | Path-based | Identifier-based |",
            "|---|---|---:|---:|---:|",
            *scenario_lines,
            "",
            "## Drift Tolerance",
            "",
            "| Drift | Recovery accuracy | Mean true similarity | Easy FMR | Hard FMR |",
            "|---:|---:|---:|---:|---:|",
            *drift_lines,
            "",
            "## Figures",
            "",
            "- fig1_recovery_by_scenario.png",
            "- fig2_drift_tolerance.png",
            "- fig3_similarity_distribution.png",
            "- fig4_threshold_tradeoff.png",
            "- fig5_roc.png",
            "- fig6_latency.png",
            "- fig7_ablation.png",
            "",
            "## Failure Analysis",
            "",
            "| Failure type | Count | Share | Explanation |",
            "|---|---:|---:|---|",
            *[
                f"| {item['failure_type']} | {item['count']} | {item['share_of_failures']:.3f} | {item['explanation']} |"
                for item in data.get("failure_analysis", [])
            ],
        ]),
        encoding="utf-8",
    )


def build(results_path: Path, out_dir: Path) -> dict:
    data = json.loads(results_path.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    fig1_recovery_by_scenario(data, out_dir)
    fig2_drift_tolerance(data, out_dir)
    fig3_similarity_distribution(data, out_dir)
    fig4_threshold_tradeoff(data, out_dir)
    fig5_roc(data, out_dir)
    fig6_latency(data, out_dir)
    fig7_ablation(data, out_dir)
    write_findings(data, out_dir)
    return {
        "figures": [str(path) for path in sorted(out_dir.glob("fig*.png"))],
        "findings": str(out_dir / "research_findings.md"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="../results/realdata_results.json")
    parser.add_argument("--out-dir", default="../sharp_figures")
    args = parser.parse_args()
    outputs = build(Path(args.results), Path(args.out_dir))
    print(json.dumps(outputs, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
