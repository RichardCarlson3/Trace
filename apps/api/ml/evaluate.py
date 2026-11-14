"""Evaluate a trained pipeline on an untouched local held-out SciCite split."""

import argparse
import json
from collections import Counter
from pathlib import Path

import joblib
from sklearn.metrics import ConfusionMatrixDisplay, accuracy_score, classification_report, f1_score

from app.core.config import get_settings
from ml.train import load_split


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-file", type=Path, required=True)
    parser.add_argument("--test-file", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, default=get_settings().model_artifact_dir)
    args = parser.parse_args()
    _, training_labels = load_split(args.train_file)
    contexts, labels = load_split(args.test_file)
    model = joblib.load(args.artifact_dir / "citation_pipeline.joblib")
    predictions = model.predict(contexts)
    majority = Counter(training_labels).most_common(1)[0][0]
    baseline = [majority] * len(labels)
    report = {
        "accuracy": accuracy_score(labels, predictions),
        "macro_f1": f1_score(labels, predictions, average="macro"),
        "per_class": classification_report(labels, predictions, output_dict=True, zero_division=0),
        "majority_baseline": {
            "class": majority,
            "accuracy": accuracy_score(labels, baseline),
            "macro_f1": f1_score(labels, baseline, average="macro"),
        },
    }
    (args.artifact_dir / "evaluation.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ConfusionMatrixDisplay.from_predictions(
        labels, predictions, labels=["background", "method", "result"]
    )
    plt.tight_layout()
    plt.savefig(args.artifact_dir / "confusion_matrix.png")
    plt.close()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
