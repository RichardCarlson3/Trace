import logging
import math
from pathlib import Path
from threading import Lock

from app.core.errors import ServiceError
from app.schemas.contracts import Classification
from ml.artifacts import load_model

logger = logging.getLogger(__name__)


class InferenceService:
    """Cache a verified local pipeline after the first classification request."""

    def __init__(self, artifact_dir: Path):
        self.artifact_dir = artifact_dir
        self._pipeline = None
        self._model_version = None
        self._lock = Lock()

    def classify(self, context_text: str) -> Classification:
        with self._lock:
            if self._pipeline is None:
                try:
                    pipeline, metadata = load_model(self.artifact_dir)
                    model_version = metadata["model_version"]
                    if not isinstance(model_version, str) or not model_version.strip():
                        raise ValueError("Model metadata requires a nonblank model_version")
                    if not callable(getattr(pipeline, "predict_proba", None)):
                        raise ValueError("Model must support probability inference")
                except Exception:
                    logger.exception("Citation model artifacts could not be loaded")
                    raise ServiceError(
                        503,
                        "model_unavailable",
                        "Citation model artifacts are missing or incompatible",
                    ) from None
                self._model_version = model_version
                self._pipeline = pipeline
        try:
            batch = self._pipeline.predict_proba([context_text])
            if len(batch) != 1:
                raise ValueError("Expected one prediction row")
            scores = [float(value) for value in batch[0]]
            classes = [str(label) for label in self._pipeline.classes_]
            if len(classes) != 3 or set(classes) != {"background", "method", "result"}:
                raise ValueError("Unexpected citation classes")
            if len(scores) != len(classes) or any(
                not math.isfinite(score) or not 0 <= score <= 1 for score in scores
            ):
                raise ValueError("Invalid class scores")
            if not math.isclose(sum(scores), 1.0, rel_tol=1e-6, abs_tol=1e-8):
                raise ValueError("Class scores must sum to one")
            index = max(range(len(scores)), key=scores.__getitem__)
            return Classification(
                intent=classes[index],
                confidence=scores[index],
                model_version=self._model_version,
            )
        except Exception:
            logger.exception("Citation intent prediction failed")
            raise ServiceError(
                500, "inference_error", "Citation intent prediction failed"
            ) from None
