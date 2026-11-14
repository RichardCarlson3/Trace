"""Synthetic fixtures exercise ML behavior without network access or downloaded data."""

import json

import numpy as np
import pytest

from ml.artifacts import (
    METADATA_FILENAME,
    MODEL_FILENAME,
    dependency_versions,
    load_model,
    save_model,
)
from ml.data import (
    LABEL_NAMES,
    SciCiteData,
    encode_label,
    load_scicite,
    prepare_splits,
    split_arrays,
    split_statistics,
)
from ml.evaluate import classification_metrics, evaluate_saved_model, save_confusion_matrix
from ml.train import build_pipeline, train_baseline


def row(identifier, text, label=0):
    return {"unique_id": identifier, "string": text, "label": label}


@pytest.fixture
def fitted_pipeline():
    # These strings are test fixtures and are unrelated to real research papers.
    texts = (
        ["method algorithm procedure"] * 3
        + ["background prior literature"] * 3
        + ["result findings comparison"] * 3
    )
    labels = ["method"] * 3 + ["background"] * 3 + ["result"] * 3
    return build_pipeline().fit(texts, labels)


@pytest.mark.parametrize("number,name", list(enumerate(LABEL_NAMES)))
def test_verified_scicite_label_mapping(number, name):
    assert encode_label(number) == number
    assert encode_label(name) == number


@pytest.mark.parametrize("value", [-1, 3, True, None, "unknown", 1.0])
def test_invalid_labels_are_rejected(value):
    with pytest.raises(ValueError, match="Invalid SciCite label"):
        encode_label(value)


def test_overlap_audit_preserves_test_and_excludes_held_out_contexts():
    splits = {
        "train": [
            row("keep", "A scientific train context"),
            row("shared-id", "Alternate passage"),
            row("different-id", "TEST   context"),
        ],
        "validation": [
            row("val", "Validation context", 1),
            row("shared-test-id", "Other validation passage"),
        ],
        "test": [
            row("shared-id", "A held-out passage", 2),
            row("test", "Test context"),
            row("shared-test-id", "Final passage", 1),
        ],
    }
    cleaned, audit = prepare_splits(splits)
    assert cleaned["test"] == splits["test"]
    assert len(splits["train"]) == 3
    assert cleaned["train"] == [splits["train"][0]]
    assert cleaned["validation"] == [splits["validation"][0]]
    assert audit["excluded_rows"] == {"train": 2, "validation": 1, "test": 0}
    assert all(
        values == {"shared_unique_ids": 0, "shared_contexts": 0}
        for values in audit["effective_overlap"].values()
    )


def test_statistics_report_missing_and_blank_contexts():
    stats = split_statistics([row("a", None), row("b", " ", 1), row("c", "Text with 3 tokens", 2)])
    assert stats["missing_contexts"] == 1
    assert stats["empty_contexts"] == 1
    assert stats["words"]["mean"] == 4
    assert stats["class_counts"] == {"method": 1, "background": 1, "result": 1}


@pytest.mark.parametrize("rows", [[], [row("a", None)], [row("a", "")], [row("a", " ")]])
def test_model_inputs_reject_missing_and_blank_contexts(rows):
    with pytest.raises(ValueError, match="nonblank citation contexts"):
        split_arrays(rows)


def test_supported_json_loader_deduplicates_ids_and_preserves_text(tmp_path):
    pytest.importorskip("datasets")
    fixtures = {
        "train.jsonl": [
            row("a", "Scientific α context stays unchanged.", "method"),
            row("a", "Duplicate ID is ignored.", "result"),
        ],
        "dev.jsonl": [row("b", "A validation citation.", 1)],
        "test.jsonl": [row("c", "A test citation.", 2)],
    }
    for filename, rows in fixtures.items():
        (tmp_path / filename).write_text(
            "".join(json.dumps(value) + "\n" for value in rows), encoding="utf-8"
        )
    data = load_scicite(tmp_path)
    assert data.splits["train"][0]["string"] == fixtures["train.jsonl"][0]["string"]
    assert data.splits["train"][0]["label"] == 0
    assert data.report["official_splits"]["train"]["duplicate_ids_removed"] == 1
    assert data.report["features"]["label"]["names"] == list(LABEL_NAMES)


def test_selection_never_fits_held_out_vocabulary_or_reads_test_labels():
    class UnreadableTestSplit:
        def __iter__(self):
            pytest.fail("Training read test labels")

    train = [
        row(f"{label}-{i}", f"{label} training scientific context", number)
        for number, label in enumerate(LABEL_NAMES)
        for i in range(3)
    ]
    validation = [
        row(f"val-{label}", f"{label} validationonlytoken", number)
        for number, label in enumerate(LABEL_NAMES)
    ]
    data = SciCiteData(
        {"train": train, "validation": validation, "test": UnreadableTestSplit()}, {}
    )
    pipeline, information = train_baseline(data, [1.0, 4.0])
    assert "validationonlytoken" not in pipeline.named_steps["tfidf"].vocabulary_
    assert (
        information["selected_C"]
        == max(information["candidates"], key=lambda item: item["macro_f1"])["C"]
    )
    assert set(pipeline.classes_) == set(LABEL_NAMES)
    assert np.allclose(pipeline.predict_proba([validation[0]["string"]]).sum(axis=1), 1)


def test_metrics_use_fixed_class_order_and_training_majority():
    metrics = classification_metrics(
        list(LABEL_NAMES), ["method", "background", "background"], "method"
    )
    assert metrics["accuracy"] == pytest.approx(2 / 3)
    assert metrics["macro_f1"] == pytest.approx(5 / 9)
    assert metrics["confusion_matrix"] == [[1, 0, 0], [0, 1, 0], [0, 1, 0]]
    assert metrics["per_class"]["result"]["recall"] == 0
    assert metrics["majority_baseline"]["accuracy"] == pytest.approx(1 / 3)
    assert metrics["majority_baseline"]["macro_f1"] == pytest.approx(1 / 6)


def test_saved_pipeline_round_trip_preserves_probabilities(fitted_pipeline, tmp_path):
    metadata = {"model_version": "test-fixture-v1", "dependencies": dependency_versions()}
    saved = save_model(fitted_pipeline, metadata, tmp_path)
    reloaded, loaded_metadata = load_model(tmp_path)
    assert loaded_metadata == saved
    assert np.allclose(
        fitted_pipeline.predict_proba(["method procedure"]),
        reloaded.predict_proba(["method procedure"]),
    )


def test_incompatible_sklearn_is_rejected_before_deserialization(
    fitted_pipeline, tmp_path, monkeypatch
):
    save_model(
        fitted_pipeline, {"dependencies": {"scikit-learn": "incompatible-version"}}, tmp_path
    )
    monkeypatch.setattr(
        "ml.artifacts.joblib.load", lambda *args: pytest.fail("Deserialized incompatible artifact")
    )
    with pytest.raises(ValueError, match="requires scikit-learn"):
        load_model(tmp_path)


def test_artifact_checksum_mismatch_is_rejected(fitted_pipeline, tmp_path):
    save_model(fitted_pipeline, {"dependencies": dependency_versions()}, tmp_path)
    with (tmp_path / MODEL_FILENAME).open("ab") as artifact:
        artifact.write(b"corruption")
    with pytest.raises(ValueError, match="checksum"):
        load_model(tmp_path)


def test_evaluation_rejects_different_dataset_files(fitted_pipeline, tmp_path):
    metadata = {"dependencies": dependency_versions(), "dataset": {"fingerprint": "training-data"}}
    save_model(fitted_pipeline, metadata, tmp_path)
    data = SciCiteData({}, {"fingerprint": "different-data"})
    with pytest.raises(ValueError, match="Dataset files differ"):
        evaluate_saved_model(data, tmp_path)
    assert (tmp_path / METADATA_FILENAME).is_file()


def test_confusion_matrix_json_lists_render_to_png(tmp_path):
    pytest.importorskip("matplotlib")
    destination = tmp_path / "confusion_matrix.png"
    save_confusion_matrix([[2, 0, 0], [1, 2, 0], [0, 1, 3]], destination, "test")
    assert destination.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
