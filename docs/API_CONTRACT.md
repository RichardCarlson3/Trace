# API contract v1

Base URL `http://localhost:8000/api/v1`. JSON fields use snake_case. Runtime OpenAPI documentation is available at `/docs` and `/openapi.json`.

## Routes

| Method | Route | Current behavior |
| --- | --- | --- |
| GET | `/health` | 200 independent of database, model and external APIs |
| GET | `/papers/search?q=...&page=1&per_page=10` | Real OpenAlex search |
| GET | `/papers/{id}` | 501, intended Paper response |
| GET | `/papers/{id}/neighbors` | 501, intended Graph response |
| POST | `/classify` | 503 without artifact, Classification response when installed |
| POST | `/graphs` | 501, validates intended save request |
| GET | `/graphs` | 501, intended saved-graph summaries |
| GET | `/graphs/{id}` | 501, intended saved snapshot, UUID path parameter |

Paper path IDs use normalized `W` plus digits. Input schemas also normalize full `https://openalex.org/W...` IDs. Search requires a nonblank query of at most 300 characters, page at least 1 and per_page between 1 and 25. Search matches title/keyword/DOI text through the provider's search parameter.

## Health

```json
{"status":"ok","service":"researchgraph-api"}
```

## Paper and search response

| Paper field | Type |
| --- | --- |
| `id` | Normalized OpenAlex work ID string |
| `doi` | string or null, provider DOI URL |
| `title` | string |
| `year` | integer or null |
| `authors` | array of display-name strings |
| `abstract` | string or null |
| `cited_by_count` | nonnegative integer |
| `landing_page_url` | string or null |

Search returns `{papers: Paper[], total: integer, page: integer, per_page: integer}`. An empty result contains an empty papers array and a zero total. Unavailable abstracts remain null. A missing provider title displays the explicit missing-title label `Untitled work`.

## Citation and graph

| Citation field | Type and meaning |
| --- | --- |
| `id` | Stable relationship identifier string, future context-aware IDs should distinguish multiple passages |
| `source` | Citing OpenAlex work ID |
| `target` | Cited OpenAlex work ID |
| `intent` | `background`, `method`, `result`, or null |
| `confidence` | number in [0,1] or null |
| `context_text` | Genuine citation passage string or null |
| `context_source_url` | Source of the passage string or null |

If Paper B cites Paper A, the edge is `B -> A`. Never reverse source and target. Unclassified edges have null intent and confidence. A classified edge requires nonblank context text and confidence. Context-source provenance should be retained when supplied. Metadata titles alone cannot establish citation intent.

Graph returns `{papers: Paper[], citations: Citation[]}`. All citation endpoints must appear in papers, and paper IDs must be unique. Neighbor traversal direction/year query parameters will be agreed when expansion is implemented.

## Classification

Request body contains a strict string `context_text` with 1 to 20,000 characters, including non-whitespace text, and optional nullable `context_source_url`. Callers are responsible for supplying a genuine passage. The established `context_text` field is required. Additional request fields are rejected, including artifact paths. The service uses the original passage without stripping or rewriting it.

Response type is `{intent: CitationIntent, confidence: number, model_version: string}`. Milestone 2 adds `model_version`, read from the loaded artifact metadata. Existing intent and confidence fields retain their meaning and names. The shared TypeScript `Classification` type includes the added field.

The intent is the highest-scoring class from the fitted Pipeline's `predict_proba` output. Class scores are associated using its actual `classes_` ordering. `confidence` is that class's finite score in [0,1]. These are uncalibrated logistic-regression scores. A score of 0.9 does not establish a 90% probability that the classification is correct.

The following request uses the illustrative passage supplied for Milestone 2. The response was measured using the project's trained artifact.

```json
{"context_text":"We adopt the architecture introduced by Vaswani et al. for our experiments."}
```

```json
{"intent":"method","confidence":0.9047205612733114,"model_version":"scicite-tfidf-logreg-v1"}
```

Empty, whitespace-only, missing, oversized or incorrectly typed passages return HTTP 422 with `validation_error`. Missing metadata/model files, checksum failures, incompatible sklearn versions, invalid model metadata and unreadable artifacts return HTTP 503 with `model_unavailable`. Unexpected prediction failures or invalid model scores return HTTP 500 with `inference_error`. Responses contain generic messages. Diagnostic exceptions are logged server-side.

The application creates an inference service at startup and lazily loads `citation_pipeline.joblib` plus `model_metadata.json` on the first valid classification request. Loading uses `ml.artifacts.load_model`, including its exact sklearn-version check and artifact checksum. Successful loads are cached once per application process, with a lock coordinating concurrent first requests. Failed loads can retry on a later request after the artifact pair is restored. Restart each application process after replacing a successfully cached model.

`MODEL_ARTIFACT_DIR` selects the trusted server-side artifact directory and defaults to `apps/api/artifacts`. Relative overrides resolve from `apps/api`. Backend startup, health and paper search work without artifacts or a database. Training remains an explicit developer command. See `apps/api/ml/README.md` for PowerShell startup, invocation, restoration and test commands.

## Intended graph persistence

`SaveGraphRequest` contains `name` (1–200 characters), normalized `seed_paper_id`, `graph`, `positions` keyed by paper ID with x/y numbers, `expanded_nodes`, `settings` and `filters`. Positions and settings preserve frontend state. An eventual saved snapshot adds `id`, `created_at` and `updated_at`. List summaries should contain `id`, `name`, `seed_paper_id`, `created_at` and `updated_at`. Authentication and authorization are required before these responses are implemented. Never accept caller-provided owner identity as proof of ownership.

## Errors

```json
{"error":{"code":"model_unavailable","message":"No trained citation model is installed"}}
```

422 validation errors add `details`, an array containing `loc` and `msg`. Service errors use 502 for unreachable/rejected/invalid provider responses and 503 for exhausted transient retries or missing models. Planned features use 501 with `not_implemented`. Standard missing routes use `http_error`. Unexpected failures return HTTP 500 with `internal_error` and a generic message, with diagnostic details in backend logs.
