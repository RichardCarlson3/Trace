"""Persist the fitted sklearn Pipeline and the metadata needed to reload it."""

import json
import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from tempfile import NamedTemporaryFile

import joblib
from sklearn.pipeline import Pipeline

from ml.data import LABEL_NAMES, file_sha256

MODEL_FILENAME = "citation_pipeline.joblib"
METADATA_FILENAME = "model_metadata.json"


def dependency_versions() -> dict:
    versions = {"python": platform.python_version()}
    for package in ("scikit-learn", "numpy", "scipy", "joblib", "datasets", "pandas", "matplotlib"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    return versions


def save_model(pipeline: Pipeline, metadata: dict, artifact_dir: Path) -> dict:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=artifact_dir, suffix=".joblib", delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        joblib.dump(pipeline, temporary_path, compress=3)
        metadata = {**metadata, "artifact_sha256": file_sha256(temporary_path)}
        temporary_path.replace(artifact_dir / MODEL_FILENAME)
    finally:
        temporary_path.unlink(missing_ok=True)
    with NamedTemporaryFile(
        dir=artifact_dir, suffix=".json", mode="w", encoding="utf-8", delete=False
    ) as temporary:
        json.dump(metadata, temporary, indent=2)
        temporary.write("\n")
        metadata_path = Path(temporary.name)
    metadata_path.replace(artifact_dir / METADATA_FILENAME)
    return metadata


def load_model(artifact_dir: Path) -> tuple[Pipeline, dict]:
    """Load only artifacts from a trusted training run. Checksums do not establish trust."""
    metadata = json.loads((artifact_dir / METADATA_FILENAME).read_text(encoding="utf-8"))
    trained_version = metadata["dependencies"]["scikit-learn"]
    if trained_version != version("scikit-learn"):
        raise ValueError(
            f"Model requires scikit-learn {trained_version}; sync the recorded uv lockfile"
        )
    path = artifact_dir / MODEL_FILENAME
    if file_sha256(path) != metadata["artifact_sha256"]:
        raise ValueError(
            "Model checksum does not match its metadata; restore a matching artifact pair"
        )
    pipeline = joblib.load(path)
    if not isinstance(pipeline, Pipeline) or set(pipeline.classes_) != set(LABEL_NAMES):
        raise ValueError("Expected a fitted three-class SciCite sklearn Pipeline")
    return pipeline, metadata
