# Citation-intent model development

Training and evaluation run explicitly. Installing the normal backend dependencies downloads no dataset or trained model. The API boots with an empty artifact directory.

## Install training tools

```text
uv sync --project apps/api --locked --group dev --group training
```

This adds Hugging Face datasets, Pandas and Matplotlib. scikit-learn, NumPy and joblib are available for serving the trained sklearn pipeline. Keep training and inference environments synchronized with `uv.lock`.

## Obtain SciCite explicitly

The Hugging Face SciCite card describes its citation contexts and official train/validation/test splits. Its legacy loading script is incompatible with current datasets releases that removed dataset scripts. Obtain the original `train.jsonl`, `dev.jsonl` and `test.jsonl` from the linked AllenAI project and place them in the ignored `apps/api/data/scicite/` directory. The dataset's string labels are `background`, `method` and `result`. The JSON loader in this repository uses those labels directly and reads citation passages from `string`.

[SciCite dataset card](https://huggingface.co/datasets/allenai/scicite)

[AllenAI SciCite repository and data instructions](https://github.com/allenai/scicite)

Do not tune using the test split. Use dev for iteration and the untouched official test split for the final evaluation. SciCite identifiers refer to its source corpus and require mapping before integration with canonical OpenAlex graph IDs.

## Train and evaluate from the root

```text
uv run --project apps/api --group training python -m ml.train --train-file apps/api/data/scicite/train.jsonl
uv run --project apps/api --group training python -m ml.evaluate --train-file apps/api/data/scicite/train.jsonl --test-file apps/api/data/scicite/test.jsonl
```

The initial pipeline uses TF-IDF unigrams/bigrams and logistic regression with a fixed random seed. Training writes `citation_pipeline.joblib` containing both fitted stages to the configured artifact directory. Evaluation writes `evaluation.json` and `confusion_matrix.png` with accuracy, macro F1, per-class precision/recall/F1, and a majority-class baseline chosen from training labels.

## Serving interface

Set `MODEL_ARTIFACT_DIR` when artifacts live outside `apps/api/artifacts`. Relative directories resolve from `apps/api`. The inference service expects a trusted `citation_pipeline.joblib` sklearn Pipeline with `predict_proba` and string `classes_` drawn from the three canonical labels. Replace the artifact and restart FastAPI to reload. The API accepts actual citation-context text through `/api/v1/classify` and returns intent plus the highest class probability. This probability is the model score and has not been calibrated.

Keep original evidence and its source URL with graph classifications. OpenAlex search metadata does not provide a citation passage. Never infer intent from paper titles or manufacture context.

Joblib artifacts must originate from trusted team training runs. Keep datasets, caches, model binaries, evaluation outputs and virtual environments out of Git. This initialization does not train a model or assess its real-world quality.
