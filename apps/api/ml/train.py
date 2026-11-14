"""Fit SciCite baselines on training contexts and select using validation macro F1."""

import argparse
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from app.core.config import get_settings
from ml.artifacts import dependency_versions, load_model, save_model
from ml.data import DEFAULT_DATA_DIR, LABEL_NAMES, load_scicite, split_arrays
from ml.evaluate import classification_metrics


def build_pipeline(c: float = 1.0, seed: int = 42) -> Pipeline:
    if not math.isfinite(c) or c <= 0:
        raise ValueError("C must be a finite positive number")
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=50000)),
            (
                "classifier",
                LogisticRegression(C=c, max_iter=1000, solver="lbfgs", random_state=seed),
            ),
        ]
    )


def train_baseline(data, c_values: list[float], seed: int = 42) -> tuple[Pipeline, dict]:
    if not c_values:
        raise ValueError("Provide at least one candidate C value")
    contexts, labels = split_arrays(data.splits["train"])
    validation_contexts, validation_labels = split_arrays(data.splits["validation"])
    if set(labels) != set(LABEL_NAMES):
        raise ValueError("Training split must contain all three citation-intent classes")
    counts = Counter(labels)
    majority_label = max(LABEL_NAMES, key=lambda label: counts[label])
    candidates = []
    best_pipeline = None
    best_metrics = None
    best_c = None
    for c in c_values:
        pipeline = build_pipeline(c, seed)
        pipeline.fit(contexts, labels)
        metrics = classification_metrics(
            validation_labels, pipeline.predict(validation_contexts), majority_label
        )
        candidates.append(
            {"C": c, "accuracy": metrics["accuracy"], "macro_f1": metrics["macro_f1"]}
        )
        if best_metrics is None or metrics["macro_f1"] > best_metrics["macro_f1"]:
            best_pipeline, best_metrics, best_c = pipeline, metrics, c
    return best_pipeline, {
        "selection_metric": "validation macro_f1; ties retain the first candidate",
        "candidates": candidates,
        "selected_C": best_c,
        "seed": seed,
        "training_rows": len(contexts),
        "validation_rows": len(validation_contexts),
        "majority_label": majority_label,
        "validation_metrics": best_metrics,
        "vectorizer": {
            "ngram_range": [1, 2],
            "min_df": 2,
            "max_features": 50000,
            "lowercase": True,
        },
        "classifier": {"C": best_c, "max_iter": 1000, "solver": "lbfgs", "class_weight": None},
        "fitted_vocabulary_size": len(best_pipeline.named_steps["tfidf"].vocabulary_),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--artifact-dir", type=Path, default=get_settings().model_artifact_dir)
    parser.add_argument("--c-values", type=float, nargs="+", default=[1.0, 4.0])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model-version", default="scicite-tfidf-logreg-v1")
    args = parser.parse_args()
    data = load_scicite(args.data_dir)
    pipeline, training = train_baseline(data, args.c_values, args.seed)
    metadata = {
        "model_version": args.model_version,
        "created_at": datetime.now(UTC).isoformat(),
        "model_type": "sklearn Pipeline: TfidfVectorizer -> LogisticRegression",
        "dependencies": dependency_versions(),
        "dataset": data.report,
        "training": training,
    }
    save_model(pipeline, metadata, args.artifact_dir)
    reloaded, _ = load_model(args.artifact_dir)
    probe = data.splits["validation"][0]["string"]
    if reloaded.predict([probe])[0] != pipeline.predict([probe])[0]:
        raise RuntimeError("Reloaded model prediction differs from the fitted model")
    print(f"Saved and reloaded pipeline in {args.artifact_dir}")
    print(
        f"Selected C={training['selected_C']} using validation "
        f"macro F1={training['validation_metrics']['macro_f1']:.6f}"
    )


if __name__ == "__main__":
    main()
