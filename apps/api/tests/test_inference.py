"""Inference tests use isolated model doubles and never fit or download a model."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version
from time import sleep
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sklearn.pipeline import Pipeline

from app.core.config import Settings
from app.main import create_app
from app.services.inference import InferenceService
from ml.artifacts import METADATA_FILENAME, MODEL_FILENAME


@pytest.fixture
def loaded_model(monkeypatch):
    # Deliberately use a different ordering from the real artifact and label mapping.
    pipeline = SimpleNamespace(
        classes_=np.array(["result", "background", "method"]),
        predict_proba=Mock(return_value=np.array([[0.15, 0.25, 0.60]])),
    )
    loader = Mock(return_value=(pipeline, {"model_version": "isolated-fixture-v1"}))
    monkeypatch.setattr("app.services.inference.load_model", loader)
    return pipeline, loader


def test_valid_passage_uses_the_model_score_and_metadata(client, loaded_model):
    pipeline, loader = loaded_model
    context = "  Synthetic citation fixture with original spacing.\n"
    response = client.post(
        "/api/v1/classify",
        json={"context_text": context, "context_source_url": "https://example.test/source"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "intent": "method",
        "confidence": 0.6,
        "model_version": "isolated-fixture-v1",
    }
    pipeline.predict_proba.assert_called_once_with([context])
    loader.assert_called_once_with(client.app.state.settings.model_artifact_dir)


@pytest.mark.parametrize(
    "scores,label,expected_score",
    [
        ([0.8, 0.15, 0.05], "result", 0.8),
        ([0.1, 0.7, 0.2], "background", 0.7),
        ([0.2, 0.15, 0.65], "method", 0.65),
    ],
)
def test_scores_follow_actual_class_order(client, loaded_model, scores, label, expected_score):
    loaded_model[0].predict_proba.return_value = np.array([scores])
    response = client.post("/api/v1/classify", json={"context_text": "Synthetic citation fixture."})
    assert response.status_code == 200
    assert response.json()["intent"] == label
    assert response.json()["confidence"] == pytest.approx(expected_score)


def test_repeated_requests_reuse_a_single_loaded_model(client, loaded_model):
    for _ in range(3):
        assert (
            client.post("/api/v1/classify", json={"context_text": "Synthetic fixture."}).status_code
            == 200
        )
    assert loaded_model[1].call_count == 1
    assert loaded_model[0].predict_proba.call_count == 3


def test_concurrent_first_requests_load_once(tmp_path, loaded_model):
    pipeline, loader = loaded_model

    def delayed_load(directory):
        sleep(0.01)
        return pipeline, {"model_version": "concurrent-fixture-v1"}

    loader.side_effect = delayed_load
    service = InferenceService(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(service.classify, ["Synthetic fixture."] * 8))
    assert loader.call_count == 1
    assert all(result.model_version == "concurrent-fixture-v1" for result in results)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"text": "Wrong field name"},
        {"context_text": ""},
        {"context_text": " \n\t"},
        {"context_text": "\u00a0"},
        {"context_text": None},
        {"context_text": 123},
        {"context_text": True},
        {"context_text": []},
        {"context_text": {}},
        {"context_text": "x" * 20001},
        [],
        "wrong root type",
        {"context_text": "Synthetic fixture.", "artifact_dir": "untrusted-location"},
    ],
)
def test_invalid_requests_return_422_before_loading(client, loaded_model, body):
    response = client.post("/api/v1/classify", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    loaded_model[1].assert_not_called()


def test_maximum_length_input_is_accepted(client, loaded_model):
    response = client.post("/api/v1/classify", json={"context_text": "x" * 20000})
    assert response.status_code == 200


def test_invalid_json_returns_422(client, loaded_model):
    response = client.post(
        "/api/v1/classify", content="{", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    loaded_model[1].assert_not_called()


@pytest.mark.parametrize(
    "scores",
    [
        [[float("nan"), 0.5, 0.5]],
        [[float("inf"), 0.0, 0.0]],
        [[-0.1, 0.5, 0.6]],
        [[1.1, 0.0, 0.0]],
        [[0.2, 0.2, 0.2]],
        [[0.4, 0.6]],
        [],
        [[0.2, 0.3, 0.5], [0.2, 0.3, 0.5]],
    ],
)
def test_invalid_model_scores_return_500_without_a_prediction(client, loaded_model, scores):
    loaded_model[0].predict_proba.return_value = scores
    response = client.post("/api/v1/classify", json={"context_text": "Synthetic fixture."})
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "inference_error", "message": "Citation intent prediction failed"}
    }


def test_prediction_failure_is_logged_and_the_cached_model_can_retry(client, loaded_model, caplog):
    pipeline, loader = loaded_model
    pipeline.predict_proba.side_effect = [
        RuntimeError("private diagnostic C:/private/model.joblib"),
        np.array([[0.15, 0.25, 0.60]]),
    ]
    response = client.post("/api/v1/classify", json={"context_text": "Synthetic fixture."})
    assert response.status_code == 500
    assert "C:/private" not in response.text
    assert "private diagnostic" in caplog.text
    assert (
        client.post("/api/v1/classify", json={"context_text": "Synthetic fixture."}).status_code
        == 200
    )
    assert loader.call_count == 1


@pytest.mark.parametrize("present_file", [MODEL_FILENAME, METADATA_FILENAME])
def test_missing_artifact_pair_is_unavailable(client, present_file):
    directory = client.app.state.settings.model_artifact_dir
    (directory / present_file).write_text("{}", encoding="utf-8")
    response = client.post("/api/v1/classify", json={"context_text": "Synthetic fixture."})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_unavailable"
    assert str(directory) not in response.text


@pytest.mark.parametrize(
    "failure", ["sklearn_version", "checksum", "serialization", "metadata_json"]
)
def test_incompatible_artifacts_are_unavailable(client, monkeypatch, failure):
    directory = client.app.state.settings.model_artifact_dir
    payload = b"invalid serialized pipeline"
    (directory / MODEL_FILENAME).write_bytes(payload)
    metadata = {
        "model_version": "broken-fixture-v1",
        "dependencies": {"scikit-learn": version("scikit-learn")},
        "artifact_sha256": hashlib.sha256(payload).hexdigest(),
    }
    if failure == "sklearn_version":
        metadata["dependencies"]["scikit-learn"] = "incompatible-version"
    if failure == "checksum":
        metadata["artifact_sha256"] = "wrong-checksum"
    content = "{" if failure == "metadata_json" else json.dumps(metadata)
    (directory / METADATA_FILENAME).write_text(content, encoding="utf-8")
    deserialize = Mock(side_effect=AssertionError("Must reject before deserializing"))
    if failure != "serialization":
        monkeypatch.setattr("ml.artifacts.joblib.load", deserialize)
    response = client.post("/api/v1/classify", json={"context_text": "Synthetic fixture."})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_unavailable"
    assert str(directory) not in response.text
    if failure != "serialization":
        deserialize.assert_not_called()


@pytest.mark.parametrize("model_version", [None, "", " ", 42])
def test_invalid_recorded_model_version_is_unavailable(client, loaded_model, model_version):
    pipeline, loader = loaded_model
    loader.return_value = (pipeline, {"model_version": model_version})
    response = client.post("/api/v1/classify", json={"context_text": "Synthetic fixture."})
    assert response.status_code == 503
    pipeline.predict_proba.assert_not_called()


def test_model_without_probability_inference_is_unavailable(client, loaded_model):
    loaded_model[0].predict_proba = None
    response = client.post("/api/v1/classify", json={"context_text": "Synthetic fixture."})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_unavailable"


def test_restored_artifacts_can_load_on_a_later_request(client, loaded_model):
    pipeline, loader = loaded_model
    loader.side_effect = [
        FileNotFoundError("private artifact path"),
        (pipeline, {"model_version": "restored-v1"}),
    ]
    assert (
        client.post("/api/v1/classify", json={"context_text": "Synthetic fixture."}).status_code
        == 503
    )
    response = client.post("/api/v1/classify", json={"context_text": "Synthetic fixture."})
    assert response.status_code == 200
    assert response.json()["model_version"] == "restored-v1"
    assert loader.call_count == 2


def test_startup_never_loads_or_trains_and_health_works(tmp_path, monkeypatch):
    loader = Mock(side_effect=AssertionError("Startup must not load model artifacts"))
    fit = Mock(side_effect=AssertionError("Startup must not fit a model"))
    monkeypatch.setattr("app.services.inference.load_model", loader)
    monkeypatch.setattr(Pipeline, "fit", fit)
    settings = Settings(_env_file=None, database_url="", model_artifact_dir=tmp_path)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/health").status_code == 200
    loader.assert_not_called()
    fit.assert_not_called()


def test_health_and_paper_search_work_after_model_load_failure(client, mock_provider):
    assert client.app.state.settings.database_url == ""
    assert (
        client.post("/api/v1/classify", json={"context_text": "Synthetic fixture."}).status_code
        == 503
    )
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/papers/search", params={"q": "fixture"}).status_code == 200


def test_classification_contract_is_documented(client):
    assert client.get("/docs").status_code == 200
    document = client.get("/openapi.json").json()
    route = document["paths"]["/api/v1/classify"]["post"]
    assert {"200", "422", "503", "500"} <= route["responses"].keys()
    request = document["components"]["schemas"]["ClassifyRequest"]
    assert request["required"] == ["context_text"]
    assert request["properties"]["context_text"]["maxLength"] == 20000
    response = document["components"]["schemas"]["Classification"]
    assert set(response["required"]) == {"intent", "confidence", "model_version"}
    assert "Uncalibrated" in response["properties"]["confidence"]["description"]
