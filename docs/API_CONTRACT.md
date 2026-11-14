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
| GET | `/citation-contexts` | Directed citation evidence, verified examples by default |
| POST | `/citation-contexts/classify` | Retrieve evidence for one pair and explicitly classify available passages |
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

## Citation contexts

`GET /citation-contexts` accepts query fields `citing_paper_id`, `cited_paper_id` and optional `mode` (`auto`, `examples`, `live`). `POST /citation-contexts/classify` accepts the same fields as JSON. IDs use the existing OpenAlex normalization. The citing ID is the source and the cited ID is the target. The interface accepts paper identities rather than caller-supplied passages.

The result includes both canonical IDs, `status`, computed `available`, `origin`, `retrieved_at`, `evidence_urls`, verified `citing_mapping`/`cited_mapping`, nullable `relationship_found`, `reference_scan_complete`, `reason`, `observed_context_count` and `contexts`.

Each context has `context_text`, `source="semantic_scholar"`, `source_url`, `source_url_scope="paper"`, nullable `classification` and nullable `classification_unavailable_reason`. The classification object uses the existing intent/score/model-version fields. Retrieval produces empty classification fields. Explicit classification runs only on verified retrieved evidence. Oversized contexts remain available with an explicit unclassified reason.

Statuses distinguish `available`, `no_context`, `relationship_not_found`, `unresolved_identifiers`, `incomplete`, `provider_unavailable` and `example_not_found`. A provider failure or missing passage does not establish that a scientific citation is absent. Origins distinguish `live`, `memory_cache`, `verified_example` and `unavailable`. Recorded examples contain a representative passage and the full observed source count.

Live Semantic Scholar access is disabled by default. `auto` uses fresh cached evidence or a verified example before considering an enabled live provider. It reports source failures as `provider_unavailable` with a reason code. `examples` performs no provider HTTP requests. `live` excludes recorded examples and bypasses the final relationship cache, but now reuses fresh provider mapping/reference caches to conserve the approved quota. This changes the earlier cache-bypass behavior without changing request or response shapes. A reused reference response reports `origin="memory_cache"` and preserves its capture timestamp, even if resolving a new target required a live metadata call. Mixed cached/fresh reference pages report `live`, with the oldest page capture time. `live` returns HTTP 503 when disabled, rate limited or its bounded queue is busy, and HTTP 502 for transport/protocol failures. Invalid input returns HTTP 422. Missing model artifacts affect explicit classification with HTTP 503.

All Semantic Scholar endpoints share one scheduler per lifespan service, with at least 1.5 seconds between request starts, adaptive slowdown after HTTP 429, bounded retries and a shared `Retry-After` cooldown. The supported hackathon deployment is exactly one backend worker and one instance per API key. See [citation retrieval operations](CITATION_CONTEXTS.md) for cache lifetimes, deployment restrictions and live verification.

See [citation-context configuration, examples and graph integration](CITATION_CONTEXTS.md) for PowerShell commands, mapping details, source limitations and the three real verified demo relationships.

## Intended graph persistence

`SaveGraphRequest` contains `name` (1–200 characters), normalized `seed_paper_id`, `graph`, `positions` keyed by paper ID with x/y numbers, `expanded_nodes`, `settings` and `filters`. Positions and settings preserve frontend state. An eventual saved snapshot adds `id`, `created_at` and `updated_at`. List summaries should contain `id`, `name`, `seed_paper_id`, `created_at` and `updated_at`. Authentication and authorization are required before these responses are implemented. Never accept caller-provided owner identity as proof of ownership.

## Errors

```json
{"error":{"code":"model_unavailable","message":"No trained citation model is installed"}}
```

422 validation errors add `details`, an array containing `loc` and `msg`. Service errors use 502 for unreachable/rejected/invalid provider responses and 503 for exhausted transient retries or missing models. Planned features use 501 with `not_implemented`. Standard missing routes use `http_error`. Unexpected failures return HTTP 500 with `internal_error` and a generic message, with diagnostic details in backend logs.
