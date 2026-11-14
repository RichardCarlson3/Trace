"""Evaluate the finalized SciCite pipeline on a held-out split."""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

from app.core.config import get_settings
from ml.artifacts import dependency_versions, load_model
from ml.data import DEFAULT_DATA_DIR, LABEL_NAMES, load_scicite, split_arrays


def classification_metrics(labels, predictions, majority_label: str) -> dict:
    if not len(labels) or len(labels) != len(predictions):
        raise ValueError("Evaluation requires equally sized, nonempty labels and predictions")
    if not set(labels) <= set(LABEL_NAMES) or not set(predictions) <= set(LABEL_NAMES):
        raise ValueError("Evaluation contains an unknown citation-intent label")
    if majority_label not in LABEL_NAMES:
        raise ValueError("Majority class must come from the training labels")
    report = classification_report(
        labels, predictions, labels=list(LABEL_NAMES), output_dict=True, zero_division=0
    )
    baseline = [majority_label] * len(labels)
    return {
        "accuracy": accuracy_score(labels, predictions),
        "macro_f1": f1_score(
            labels, predictions, labels=list(LABEL_NAMES), average="macro", zero_division=0
        ),
        "per_class": {label: report[label] for label in LABEL_NAMES},
        "confusion_matrix": confusion_matrix(
            labels, predictions, labels=list(LABEL_NAMES)
        ).tolist(),
        "label_order": list(LABEL_NAMES),
        "majority_baseline": {
            "class": majority_label,
            "accuracy": accuracy_score(labels, baseline),
            "macro_f1": f1_score(
                labels, baseline, labels=list(LABEL_NAMES), average="macro", zero_division=0
            ),
        },
    }


def save_confusion_matrix(matrix: list[list[int]], path: Path, split: str) -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(path.parent / ".matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import ConfusionMatrixDisplay

    figure, axis = plt.subplots(figsize=(7, 6))
    ConfusionMatrixDisplay(np.asarray(matrix), display_labels=LABEL_NAMES).plot(
        ax=axis, cmap="Purples", values_format="d", colorbar=False
    )
    axis.set_title(f"SciCite {split} - TF-IDF + Logistic Regression")
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def evaluate_saved_model(data, artifact_dir: Path, split: str = "test") -> dict:
    if split not in ("validation", "test"):
        raise ValueError("Evaluate a validation or test split")
    pipeline, metadata = load_model(artifact_dir)
    if data.report["fingerprint"] != metadata["dataset"]["fingerprint"]:
        raise ValueError(
            "Dataset files differ from the training run; use the recorded SciCite splits"
        )
    contexts, labels = split_arrays(data.splits[split])
    metrics = classification_metrics(
        labels, pipeline.predict(contexts), metadata["training"]["majority_label"]
    )
    return {
        "evaluated_at": datetime.now(UTC).isoformat(),
        "model_version": metadata["model_version"],
        "artifact_sha256": metadata["artifact_sha256"],
        "dependencies": dependency_versions(),
        "dataset": {
            "id": data.report["dataset_id"],
            "reference_revision": data.report["reference_revision"],
            "fingerprint": data.report["fingerprint"],
            "split": split,
            **data.report["effective_splits"][split],
        },
        "training_configuration": metadata["training"],
        **metrics,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--artifact-dir", type=Path, default=get_settings().model_artifact_dir)
    parser.add_argument("--split", choices=("validation", "test"), default="test")
    args = parser.parse_args()
    data = load_scicite(args.data_dir)
    report = evaluate_saved_model(data, args.artifact_dir, args.split)
    stem = "evaluation" if args.split == "test" else "validation_evaluation"
    (args.artifact_dir / f"{stem}.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    plot_name = (
        "confusion_matrix.png" if args.split == "test" else "validation_confusion_matrix.png"
    )
    save_confusion_matrix(report["confusion_matrix"], args.artifact_dir / plot_name, args.split)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
