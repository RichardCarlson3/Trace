"""Train only when explicitly invoked with locally obtained SciCite JSONL splits."""

import argparse
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from app.core.config import get_settings

LABELS = {"background", "method", "result"}


def load_split(path: Path):
    # Generic JSON loading works with current datasets versions without remote scripts.
    from datasets import load_dataset

    rows = load_dataset("json", data_files=str(path), split="train")
    contexts = [row["string"] for row in rows]
    labels = [row["label"] for row in rows]
    if not contexts or any(not isinstance(text, str) or not text.strip() for text in contexts):
        raise ValueError("Each SciCite row requires a nonblank string citation context")
    if not set(labels) <= LABELS:
        raise ValueError("Use original SciCite string labels: background, method, result")
    return contexts, labels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-file", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, default=get_settings().model_artifact_dir)
    args = parser.parse_args()
    contexts, labels = load_split(args.train_file)
    if set(labels) != LABELS:
        raise ValueError("Training split must contain all three citation-intent classes")
    pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=50000)),
            ("classifier", LogisticRegression(max_iter=1000, random_state=42)),
        ]
    )
    pipeline.fit(contexts, labels)
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    temporary = args.artifact_dir / "citation_pipeline.tmp.joblib"
    joblib.dump(pipeline, temporary)
    temporary.replace(args.artifact_dir / "citation_pipeline.joblib")
    print(f"Saved pipeline to {args.artifact_dir}")


if __name__ == "__main__":
    main()
