# SciCite baseline training

Milestone 1 trains a TF-IDF and logistic regression classifier for citation intent. It uses the existing uv project and writes a single fitted sklearn Pipeline to the configured artifact directory. Run all commands below from the repository root in Windows PowerShell.

## Install and inspect

```powershell
uv sync --project apps/api --locked --group dev --group training
uv run --project apps/api --group training python -m ml.data
```

For this checkout's portable uv installation, add it to the current PowerShell session when needed.

```powershell
$env:Path = "$PWD\.tools\uv;$env:Path"
```

The data command downloads the official archive explicitly into ignored `apps/api/data/scicite/`, verifies its SHA-256, and writes `dataset_report.json` under the artifact directory. `--data-dir` accepts a directory containing `train.jsonl`, `dev.jsonl` and `test.jsonl`. Local file hashes are recorded for reproducibility. The report includes original field types, loaded Hugging Face features, split sizes, distributions, missing/blank contexts, character/word statistics and overlap counts.

The verified Hugging Face schema maps `0` to `method`, `1` to `background`, and `2` to `result`. Citation text comes from `string`. The original archive stores label names as strings, which the loader encodes using that mapping. The official loader retains the first row for each `unique_id` within a split, and this implementation preserves that behavior.

The established `load_dataset("allenai/scicite")` call fails with the locked datasets 4.8.5 release because dataset scripts are unsupported. The replacement uses the exact archive referenced by the SciCite loader at revision `4c40e64d8eebd9c0a8f27bb630cfbaeffc01c941`, projects the context/label/identifier fields into JSONL, and reads them with `load_dataset("json", ...)` and explicit features. Original citation text is preserved. Ancillary raw fields have inconsistent types and are recorded in the audit report rather than used as model inputs.

[SciCite dataset and schema](https://huggingface.co/datasets/allenai/scicite)

[Pinned official loader and archive reference](https://huggingface.co/datasets/allenai/scicite/blob/4c40e64d8eebd9c0a8f27bb630cfbaeffc01c941/scicite.py)

[Hugging Face JSON loading documentation](https://huggingface.co/docs/datasets/loading#json)

## Split audit from the executed run

| Split | Official rows | Rows used | Method | Background | Result |
| --- | ---: | ---: | ---: | ---: | ---: |
| Train | 8,194 | 8,172 | 2,257 | 4,832 | 1,083 |
| Validation | 916 | 916 | 255 | 538 | 123 |
| Test | 1,859 | 1,859 | 604 | 996 | 259 |

The raw archive contains 8,243 training rows, 916 validation rows and 1,861 test rows. Removing repeated `unique_id` entries accounts for the official counts. All three official splits contain zero missing or blank contexts.

The audit found six shared citation IDs and 14 whitespace/case-normalized contexts between training and validation, plus three shared citation IDs between training and test. Their union excludes 22 training rows. Validation and test have no shared IDs or normalized contexts. The official test set is retained in full. Remaining cross-split ID/context overlap is zero. Whitespace/case normalization is used only for this audit. Model fitting receives the original text.

Effective mean text lengths are 33.92 words / 220.26 characters for training, 34.14 / 221.52 for validation, and 34.05 / 221.91 for test. Median word lengths are 31, 32 and 31 respectively. The report also records minima and maxima.

## Train and finalize

```powershell
uv run --project apps/api --group training python -m ml.train --c-values 1 4 --seed 42
```

Training fits each candidate on the effective training split and selects by validation macro F1. Ties retain the first candidate. The two planned candidates use C values 1 and 4. Their validation macro F1 scores were 0.800325 and 0.810039, selecting C=4. The selected model is retained from training-only fitting.

The vectorizer uses unigrams/bigrams, `min_df=2`, `max_features=50000` and sklearn's default lowercase/tokenization/TF-IDF settings. The selected model fitted 47,192 vocabulary features. Logistic regression uses `solver="lbfgs"`, `max_iter=1000`, C=4, no class weights and seed 42. There is no extra stemming, citation-marker removal or scientific-text rewriting.

The default model version is `scicite-tfidf-logreg-v1`. Override it with `--model-version`. Both training and evaluation accept `--artifact-dir`; its default comes from backend `MODEL_ARTIFACT_DIR`, resolving to `apps/api/artifacts` when unset. Training immediately reloads the saved artifact and verifies a validation prediction.

## Final test evaluation

Finalize candidate selection before running the test evaluation command.

```powershell
uv run --project apps/api --group training python -m ml.evaluate
```

Evaluation checks the dataset file fingerprint against the training metadata and uses the training majority class for its baseline. It generates `evaluation.json` and `confusion_matrix.png`. Confusion-matrix rows are true labels and columns are predicted labels, ordered method, background, result. Plotting uses the Agg backend and a writable artifact-local Matplotlib cache, including in headless environments. Optional `--split validation` writes separately named validation outputs.

The following results came from executing the finalized model on all 1,859 test contexts.

| Model | Accuracy | Macro F1 |
| --- | ---: | ---: |
| TF-IDF + logistic regression | 0.834857 | 0.815307 |
| Training-majority baseline, background | 0.535772 | 0.232574 |

| Class | Precision | Recall | F1 | Support |
| --- | ---: | ---: | ---: | ---: |
| Method | 0.856624 | 0.781457 | 0.817316 | 604 |
| Background | 0.842105 | 0.883534 | 0.862322 | 996 |
| Result | 0.760456 | 0.772201 | 0.766284 | 259 |

These are measurements of the baseline on SciCite. The effective training and test splits share 226 citing-paper IDs, so this evaluation measures context-level generalization within the official split design. The audit checks exact normalized contexts and citation IDs. It does not detect every near-duplicate passage. Model probabilities are uncalibrated, and performance on other research domains requires separate evaluation.

## Artifacts and independent loading

| File in the artifact directory | Contents |
| --- | --- |
| `citation_pipeline.joblib` | Fitted TF-IDF vectorizer and logistic regression classifier |
| `model_metadata.json` | Model version, dependency versions, artifact checksum, dataset audit and validation selection |
| `dataset_report.json` | Dataset inspection output from `ml.data` |
| `evaluation.json` | Final test metrics, baseline, configuration and provenance |
| `confusion_matrix.png` | Test confusion matrix |
| `sample_predictions.json` | Three real test passages used during verification, with labels and class probabilities |

The executed environment used Python 3.12.16, scikit-learn 1.9.1, NumPy 2.5.4, SciPy 1.18.1, joblib 1.6.0, datasets 4.8.5, Pandas 3.1.1 and Matplotlib 3.11.2. `load_model` checks the exact sklearn version and artifact checksum before deserializing. Keep the recorded lockfile and dependency versions with the artifact pair. A checksum detects mismatched files and does not establish trust. Load joblib files only from trusted team training runs.

This PowerShell command loads the fitted artifact independently of `ml.train` and predicts from three existing test passages.

```powershell
@'
from app.core.config import get_settings
from ml.artifacts import load_model
from ml.data import load_scicite

model, metadata = load_model(get_settings().model_artifact_dir)
contexts = [row["string"] for row in load_scicite().splits["test"][:3]]
print(metadata["model_version"])
print(model.classes_)
print(model.predict(contexts))
print(model.predict_proba(contexts))
'@ | uv run --project apps/api --group training python -
```

The saved Pipeline exposes `predict`, `predict_proba` and string `classes_`. FastAPI uses the same artifact loader through its cached inference service. Citation passages must remain linked to their actual source when integrated with graph edges. SciCite's source identifiers require mapping to OpenAlex IDs for that integration.

## FastAPI inference

Install the existing runtime/development dependencies and start the backend from the root.

```powershell
uv sync --project apps/api --locked --group dev
npm run dev:api
```

The API requires both `citation_pipeline.joblib` and `model_metadata.json` from the same trusted training run. Their default directory is `apps/api/artifacts`. Set backend `MODEL_ARTIFACT_DIR` in `apps/api/.env` to select another directory. Relative paths resolve from `apps/api`. Restore the matching files from a trusted team artifact copy or explicitly run the Milestone 1 training command above when generating a new model.

The application creates an inference service during app initialization. The first valid classification request loads through `ml.artifacts.load_model`, which checks the exact sklearn version and artifact SHA-256 before deserialization. The metadata must also contain a nonblank model version. A lock ensures concurrent first requests share one successful load. Later requests reuse that Pipeline and version for the lifetime of the process. Restart the API after replacing a loaded artifact pair. Failed loads are retried on a later request, allowing restored artifacts to become available.

In another PowerShell terminal, submit a passage using the established `context_text` field. This example uses the illustrative passage provided for Milestone 2.

```powershell
$body = @{
  context_text = "We adopt the architecture introduced by Vaswani et al. for our experiments."
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/classify" -ContentType "application/json" -Body $body
```

The trained artifact returned this response during verification.

```json
{
  "intent": "method",
  "confidence": 0.9047205612733114,
  "model_version": "scicite-tfidf-logreg-v1"
}
```

`intent` comes from the fitted class ordering, `confidence` is its `predict_proba` score, and `model_version` comes from metadata. Scores are uncalibrated and do not establish the probability that a prediction is correct. Callers must supply actual citation-context text for research use. Optional `context_source_url` remains accepted for provenance. It is not fetched by the service.

The request accepts 1–20,000 characters, including non-whitespace text. Invalid or missing passages return HTTP 422. Missing/incompatible artifacts return HTTP 503 with `model_unavailable`, while health and paper search remain operational. Unexpected prediction failures return HTTP 500 with `inference_error`. API errors contain generic messages, and ordinary Python logs retain diagnostic exceptions.

The interactive schema is available at `http://localhost:8000/docs`. The request schema exposes no model-file selection. Artifact configuration is controlled by the backend operator. Backend startup and classification are independent of TigerData, and model training is invoked separately.

Run the deterministic inference tests without the training dependency group.

```powershell
uv run --project apps/api pytest apps/api/tests/test_inference.py
```

They use isolated model doubles and temporary invalid-artifact fixtures without fitting models or downloading SciCite. Separate verification with the real saved Pipeline checked three existing SciCite passages and the illustrative passage above, repeated HTTP requests, metadata version and scores against direct sklearn predictions. One successful model load served all eight application requests.

## Tests and formatting

```powershell
uv run --project apps/api --group training pytest apps/api/tests/test_ml.py
uv run --project apps/api --group training pytest apps/api/tests
uv run --project apps/api --group training ruff check apps/api
uv run --project apps/api --group training ruff format --check apps/api
```

Tests use synthetic fixtures and local temporary files. They cover label mapping, duplicate handling, context preservation, split overlap, vocabulary isolation, validation selection, metric calculation, version compatibility, checksum integrity, independent reload and PNG rendering. Without the optional training group, dataset/plot integration tests skip while runtime-only tests continue to run.

Dataset caches and generated evaluation outputs are covered by Git ignore rules. The current checkout includes the model and metadata pair for API inference. Training remains an explicit developer operation.
