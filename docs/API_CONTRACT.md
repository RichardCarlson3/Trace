# API contract v1

Base URL `http://localhost:8000/api/v1`. JSON fields use snake_case. Runtime OpenAPI documentation is available at `/docs` and `/openapi.json`.

## Routes

| Method | Route | Current behavior |
| --- | --- | --- |
| GET | `/health` | 200 independent of database, model and external APIs |
| GET | `/papers/search?q=...&page=1&per_page=10` | Real OpenAlex search |
| GET | `/papers/{id}` | Real OpenAlex lookup, PaperDetails response |
| GET | `/papers/{id}/references?limit=10&offset=0` | Bounded outgoing references, ReferenceResponse |
| GET | `/papers/{id}/citations?limit=10&cursor=*` | Paginated incoming citations, IncomingCitationResponse |
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

## Paper details (Task 1)

`GET /papers/{id}` accepts an uppercase `W` followed by digits and returns `PaperDetails`,
which extends `Paper` with the following fields. Search responses remain unchanged.

| Additional field | Type and source |
| --- | --- |
| `publication_venue` | string or null, `primary_location.source.display_name` |
| `reference_count` | nonnegative integer or null, `referenced_works_count`, falling back to the length of `referenced_works` when present |

Reference counts describe OpenAlex's indexed references, which may differ from the reference
list in the paper itself. Missing reference data remains null; an explicitly empty reference
list yields zero. Missing authors produce an empty array; missing citation counts retain the
existing Paper default of zero. Missing venue, DOI, year, abstract, and landing-page URL remain
null. Abstract text is reconstructed only from the provider's inverted index.

An invalid path ID returns 422 `validation_error` without contacting OpenAlex. A provider 404
returns 404 `paper_not_found`. Invalid JSON/metadata returns 502 `openalex_invalid_response`;
other rejected requests return 502 `openalex_error`. Transport failures return 502
`openalex_unavailable` after retries. Rate limits and upstream 5xx responses return 503
`openalex_unavailable` after retries. Requests use a 10-second timeout per network operation
and at most three attempts, with 0.25- and 0.5-second backoffs. Keys remain backend-only.

The endpoint needs neither PostgreSQL nor a model artifact. For an optional live check,
start `npm run dev` from the root, then run:

```bash
curl --fail-with-body http://localhost:8000/api/v1/papers/W2741809807
```

The response is a single JSON object with all Paper fields plus `publication_venue` and
`reference_count`. Values can change as OpenAlex updates its records. The frontend can consume
the Paper fields as before; a future detail-view integration should extend its TypeScript
type with these two nullable fields. Task 1 does not change frontend behavior.

Provider requests and normalization live in `OpenAlexService`. A future cache can wrap its
detail lookup, keyed by normalized OpenAlex ID, storing provider provenance, fetch time, and
schema version. Use a bounded TTL with refresh on expiry, short negative caching for 404s,
and invalidate on normalization/schema changes. Do not cache transient failures. No cache or
database requirement is introduced in Task 1.

Provider field definitions: [OpenAlex work attributes](https://help.openalex.org/data/works/attributes/)
and [single-entity lookup](https://help.openalex.org/api/get-single-entities/).

## Outgoing references (Task 2)

`GET /papers/{id}/references?limit=10&offset=0` returns `ReferenceResponse`, extending
the existing Graph shape (`papers` and `citations`) with:

| Field | Meaning |
| --- | --- |
| `seed_paper_id` | Canonical normalized ID from the seed record |
| `next_offset` | Next offset into the unique reference list, or null |
| `has_more` | Whether additional reference IDs remain after this slice |
| `unresolved_reference_ids` | IDs in this slice whose metadata was missing or malformed in the batch response |

`limit` defaults to 10 and accepts 1–50; `offset` defaults to 0 and must be nonnegative.
Invalid bounds/IDs return 422 before any provider request. The service fetches the seed's
`referenced_works`, normalizes IDs, removes duplicates and self-links, and slices in provider
order. It then performs one bulk metadata request using `filter=ids.openalex:W...|W...`, with
`per_page` equal to the slice size. There is no individual request for each reference and no
recursive traversal. Normal execution uses two provider requests, or one for an empty slice;
each request uses the existing bounded retry/timeout policy.

`papers` includes the seed first, followed by resolved references in slice order. Each
reference has exactly one citation with `source` equal to the seed ID and `target` equal to
the referenced paper ID. Citation IDs use `source->target`. Intent, confidence, context text,
and context source URL are all null. No classifier is called. The frontend can merge records
by paper ID and directed citation ID when expansion is integrated later.

Missing/null reference lists return only the seed and no edges; this means no references
were available from this provider response, not proof that the paper has no bibliography.
Missing metadata records (including merged IDs that the batch does not return under the
requested ID) and malformed batch records are omitted and reported in `unresolved_reference_ids`.
Unrequested batch IDs are ignored; no relationship is inferred from them. An invalid batch
envelope or seed/reference list returns 502 `openalex_invalid_response`. A missing seed returns
404 `paper_not_found`. Whole-request provider failures use the same errors as paper details,
not a misleading successful empty graph.

Pagination is a local offset over the unique, non-self `referenced_works` list, not an OpenAlex
cursor. Follow `next_offset` with the same limit. Offsets advance by the number of IDs consumed,
even if some metadata cannot be resolved. `has_more` refers to unconsumed IDs, not the number of
successfully returned papers. Beyond the end, the response contains only the seed. Each call
refetches the list; results can shift if OpenAlex changes it between calls. No snapshot cache
or database is required.

For a live manual check with the API running:

```bash
curl --fail-with-body 'http://localhost:8000/api/v1/papers/W2741809807/references?limit=5&offset=0'
```

Expect at most six papers (seed plus five references), at most five outgoing citations, and
no assigned citation intent. For every edge, verify that `source` is `seed_paper_id` and that
both endpoint IDs exist in `papers`. Compare each target with the seed's `referenced_works`
from `https://api.openalex.org/works/W2741809807`. To test the next slice, pass the returned
`next_offset`; to test validation, set `limit=51` and expect 422. Unit tests use offline synthetic
fixtures and also cover batching, deduplication, partial records, and retry failures.

Batch-query reference: [OpenAlex single-entity and bulk-ID lookups](https://help.openalex.org/api/get-single-entities/).

## Incoming citations (Task 3)

`GET /papers/{id}/citations?limit=10&cursor=*` retrieves papers citing the selected work.
The service looks up the seed, then requests one page of `filter=cites:{canonical_seed_id}`
from OpenAlex. Each relationship runs **citing paper -> selected paper**. There are no
per-paper metadata requests, recursive traversal, database operations, or classifier calls.

Both relationship endpoints extend `RelationshipResponse`: the existing Graph fields
`papers` and `citations`, plus `seed_paper_id` and `has_more`. Outgoing responses retain
`next_offset` and `unresolved_reference_ids`. Incoming responses add:

| Field | Meaning |
| --- | --- |
| `next_cursor` | Opaque OpenAlex continuation token, or null at the end |
| `skipped_record_count` | Malformed records and seed self-links omitted from this provider page; duplicate valid records are deduplicated without increasing this count |

`limit` defaults to 10 and accepts 1–50. Start with `cursor=*` (the default), then pass
`next_cursor` unchanged with the same seed and limit. Use a URL-query encoder for tokens
containing `+`, `/`, or `=`. Cursors accept 1–2048 non-whitespace characters; other input
returns 422 before contacting the provider. They are opaque, not page numbers or offsets.
If OpenAlex rejects a cursor with 400, the API returns 422 `invalid_cursor`.

The response contains the seed first, then unique citing papers in provider order, with at
most `limit` citing papers and edges. IDs normalize to `W` plus digits. Edge IDs are
`source->target`; intent, confidence, context text, and context source URL remain null.
Missing abstracts and optional fields use the same defaults as search. Malformed records and
self-links are skipped, with no fabricated replacement nodes. `has_more` follows whether
`next_cursor` is non-null, even if a page becomes empty after filtering. Clients must follow
the token rather than infer exhaustion from the number of returned papers. Deduplication is
per response; clients should merge by stable paper/edge IDs across pages. Provider updates
can affect paging; this is not a frozen snapshot.

Missing/invalid pagination metadata, a repeated/non-progressing cursor, or an oversized page
returns 502 `openalex_invalid_response`. A missing seed returns 404 `paper_not_found`.
Timeouts, transient failures, and rate limits retain the existing retry/error policy.

OpenAlex currently requires an API key to follow a cursor after the initial page. Set
`OPENALEX_API_KEY` in the ignored backend `apps/api/.env` and restart FastAPI if required.
It must never be placed in frontend variables. If a cursor query returns 401 and no backend
key is configured, the API returns 503 `openalex_key_required`. A rejected configured key
returns 502 `openalex_error`. No provider error is represented as a successful empty graph.

With the API running, an optional live check is:

```bash
curl --fail-with-body 'http://localhost:8000/api/v1/papers/W2741809807/citations?limit=5'
```

Verify every citation has `target` equal to `seed_paper_id`, its source exists in `papers`,
and classification fields are null. Copy the returned cursor into Swagger's `cursor` field
for the next request, keeping the same ID and limit. When following it with curl, encode it:

```bash
curl --fail-with-body --get \
  'http://localhost:8000/api/v1/papers/W2741809807/citations' \
  --data-urlencode 'limit=5' \
  --data-urlencode 'cursor=PASTE_THE_RETURNED_NEXT_CURSOR_HERE'
```

Provider references: [cited-by filter recipe](https://help.openalex.org/how-to/api-recipes/)
and [cursor paging and API-key requirements](https://help.openalex.org/api/paging/).

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
