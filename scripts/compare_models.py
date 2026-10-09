"""Run isolated model comparisons; calibrate only on synthetic development data."""
import json
import subprocess
import sys
from pathlib import Path


def calibrate(report):
    positives = [r["best_similarity"] for r in report["metrics"]["semantic"]["observations"]]
    negatives = [r["best_similarity"] for r in report["absent_target_observations"]]
    values = sorted(set(positives + negatives))
    thresholds = [values[0] - 0.000001, values[-1] + 0.000001] + [(a + b) / 2 for a, b in zip(values, values[1:])]
    observations = []
    for threshold in thresholds:
        retained = sum(value >= threshold for value in positives)
        rejected = sum(value < threshold for value in negatives)
        balanced = (retained / len(positives) + rejected / len(negatives)) / 2
        observations.append((balanced, rejected, retained, threshold))
    balanced, rejected, retained, threshold = max(observations)
    return {"minimum_similarity": threshold, "balanced_accuracy": balanced,
            "present_queries_retained": retained, "present_queries": len(positives),
            "absent_queries_rejected": rejected, "absent_queries": len(negatives),
            "calibration": "synthetic-development-only; not confidence or held-out validation"}


def main():
    reports = {}
    for name in ["minilm", "bge"]:
        destination = Path("reports/runtime") / f"comparison-{name}"
        subprocess.run([sys.executable, "scripts/evaluate.py", "--model", f"models/{name}",
                        "--output", str(destination)], check=True)
        report = json.loads((destination / "report.json").read_text(encoding="utf-8"))
        reports[name] = {"report": report, "calibration": calibrate(report)}
    policy = {"schema": 1, "scope": "Synthetic development calibration; verify source evidence",
              "models": {entry["report"]["model"]: entry["calibration"] for entry in reports.values()}}
    Path("config").mkdir(exist_ok=True)
    Path("config/retrieval-policy.json").write_text(json.dumps(policy, indent=2), encoding="utf-8")
    Path("reports/runtime/model-comparison.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(json.dumps({name: {"metrics": {mode: {key: value for key, value in values.items() if key != "observations"}
                                          for mode, values in entry["report"]["metrics"].items()},
                            "calibration": entry["calibration"]} for name, entry in reports.items()}, indent=2))


if __name__ == "__main__":
    main()
