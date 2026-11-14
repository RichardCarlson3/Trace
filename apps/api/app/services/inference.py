from pathlib import Path
from threading import Lock

from app.core.errors import ServiceError
from app.schemas.contracts import Classification


class InferenceService:
    """Lazily load a trusted, locally trained pipeline, with no startup dependency."""

    def __init__(self, artifact_dir: Path):
        self.artifact_dir = artifact_dir
        self._pipeline = None
        self._lock = Lock()

    def classify(self, context_text: str) -> Classification:
        with self._lock:
            if self._pipeline is None:
                artifact = self.artifact_dir / "citation_pipeline.joblib"
                if not artifact.is_file():
                    raise ServiceError(
                        503, "model_unavailable", "No trained citation model is installed"
                    )
                try:
                    import joblib

                    self._pipeline = joblib.load(artifact)
                except Exception:
                    raise ServiceError(
                        503, "model_unavailable", "The model artifact could not be loaded"
                    ) from None
        try:
            probabilities = self._pipeline.predict_proba([context_text])[0]
            index = probabilities.argmax()
            return Classification(
                intent=str(self._pipeline.classes_[index]), confidence=float(probabilities[index])
            )
        except Exception:
            raise ServiceError(
                503, "model_unavailable", "The model artifact is incompatible"
            ) from None
