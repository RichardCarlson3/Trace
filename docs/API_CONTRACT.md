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
| GET | `/papers/{id}/neighbors?direction=both&limit=10&cursor=*` | Bounded graph expansion, NeighborResponse |
| POST | `/classify` | 503 without artifact, Classification response when installed |
| GET | `/citation-contexts` | Directed citation evidence, verified examples by default |
| POST | `/citation-contexts/classify` | Retrieve evidence for one pair and explicitly classify available passages |
| POST | `/graphs` | 501, validates intended save request |
| GET | `/graphs` | 501, intended saved-graph summaries |
| GET | `/graphs/{id}` | 501, intended saved snapshot, UUID path parameter |

Paper path IDs use uppercase `W` plus ASCII digits (`^W[0-9]+$`). Provider IDs and input schemas normalize bare/full OpenAlex IDs case-insensitively, trim surrounding whitespace, and emit uppercase `W` plus ASCII digits. This does not relax the path format. Search requires a nonblank query of at most 300 characters, page at least 1, per_page between 1 and 25, and `page * per_page <= 10000`. Search matches title/keyword/DOI text through the provider's search parameter.

## Health

```json
{"status":"ok","service":"researchgraph-api"}
```

## Paper and search response

| Paper field | Type |
| --- | --- |
| `id` | Normalized OpenAlex work ID string |
| `doi` | string or null, normalized `https://doi.org/` URL with ASCII case folding |
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
`openalex_unavailable` after retries (or immediately when the provider requests a long wait).
Each network attempt has both a 10-second HTTPX operation timeout and a 10-second absolute
deadline. There are at most three attempts, with 0.25- and 0.5-second minimum backoffs.
For 429/5xx responses, `Retry-After` may lengthen these waits up to two seconds; a longer
requested wait fails fast with 503 instead of retrying early. Keys remain backend-only.

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
envelope, batch larger than its requested size, or invalid seed/reference list returns 502
`openalex_invalid_response`. A missing seed returns
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

## Graph neighbors (Task 4)

`GET /papers/{id}/neighbors` combines the reference and incoming-citation services into one
bounded graph response. It uses the existing `papers` and `citations` names (not `nodes` and
`edges`). The frontend can merge papers by `id` and edges by directed relationship `id`.

| Query parameter | Default | Accepted values |
| --- | --- | --- |
| `direction` | `both` | `incoming`, `outgoing`, `both` |
| `limit` | 10 | integer 1–50, across both directions combined |
| `cursor` | `*` | `*` for a new traversal, otherwise the returned neighbors token (up to 8192 URL-safe characters) |

`NeighborResponse` extends `RelationshipResponse` and always contains:

| Field | Meaning |
| --- | --- |
| `seed_paper_id` | Canonical normalized seed ID |
| `papers` | Seed first, then unique neighbor Paper records |
| `citations` | Unique directed Citation records with both endpoints in `papers` |
| `next_cursor` | Opaque combined continuation token, or null when finished |
| `has_more` | Whether either selected direction has continuation state |
| `unresolved_reference_ids` | Outgoing IDs consumed on this page whose metadata could not be resolved |
| `skipped_record_count` | Invalid incoming records and seed self-links omitted on this page |

The seed does not count toward `limit`: at most `limit + 1` papers and `limit` edges are
returned. Incoming edges run `citing -> seed`; outgoing edges run `seed -> referenced`.
A neighbor appearing on both sides is one paper with two distinct opposite-direction edges.
Intent, confidence, context text, and context source URL remain null. No classifier runs.

Single-direction queries spend the entire budget on that direction. While both directions
have work, `both` assigns `ceil(limit / 2)` outgoing slots and `floor(limit / 2)` incoming
slots. With `limit=1`, pages alternate outgoing and incoming, starting outgoing. Once one
direction is exhausted, the other gets the entire budget on subsequent pages. A page may be
smaller than its budget (or empty except for the seed) due to exhaustion or unavailable
metadata; the service does not make refill requests. Follow `has_more`/`next_cursor`, not the
number of returned neighbors, to determine whether to continue.

The neighbors token tracks an outgoing offset, an incoming OpenAlex cursor, and the
one-slot turn. It is specific to this endpoint: keep the same requested ID, direction, and
limit when following it. Tokens from `/citations` cannot be used directly here. Invalid,
unsupported-version, exhausted, or query-mismatched tokens return 422 `invalid_cursor` before
any provider request. Invalid direction/limit/query syntax returns 422 `validation_error`.
Tokens contain pagination state only, with no credentials. They are stateless encodings, not
authentication or authorization. Do not edit them. Start again with `*` to change the query.

Each call fetches the seed exactly once, followed by at most one outgoing metadata batch and
one incoming page, excluding retries. When both directions have work, these two requests run
concurrently. There is no recursive expansion, per-reference fetch,
database access, or persistent graph mutation. Existing provider timeout/retry, partial-record,
missing-seed, and API-key rules still apply. If either requested direction fails, the entire
request returns a structured error; callers can safely retry the same token. OpenAlex updates
may affect the ordering between requests. Clients should deduplicate by stable IDs across
pages and previously expanded seeds.

Manual checks with the API running:

```bash
curl --fail-with-body 'http://localhost:8000/api/v1/papers/W2741809807/neighbors?direction=outgoing&limit=6'
curl --fail-with-body 'http://localhost:8000/api/v1/papers/W2741809807/neighbors?direction=incoming&limit=6'
curl --fail-with-body 'http://localhost:8000/api/v1/papers/W2741809807/neighbors?direction=both&limit=6'
```

In Swagger, copy `next_cursor` without quotes into the same endpoint's cursor input and
execute again with the same ID, direction, and limit. Incoming continuation requires the
backend OpenAlex key. With `both&limit=6`, expect up to three outgoing and three incoming
edges while both sides remain active, with at most seven unique papers. Check that every
edge includes the seed, uses citing-to-cited direction, and has null classification fields.
Invalid `direction=sideways` and `limit=51` should return 422. This adds backend expansion;
the frontend canvas does not yet call it.

## Pagination and performance policy (Task 5)

The public response shapes and neighbors token format are unchanged. Limits remain
conservative: up to 50 neighbors per request (combined across directions), one bounded
outgoing bulk query, and one incoming cursor page. These are below OpenAlex's supported
100-record page and bulk-ID limits. References use local offsets over the deduplicated
`referenced_works` list; they are not presented as a provider cursor. Search uses basic
pages and rejects `page * per_page > 10000` with 422 before provider I/O. Incoming citations
use cursor paging instead, including beyond the basic paging window.

After the single seed fetch, active incoming/outgoing neighbor operations run concurrently,
without changing their page budgets or result order. If either direction fails, the sibling
operation is cancelled and awaited before returning the error. Cancelling the service call
also cancels/awaits both children. There are no background refill or traversal requests.

Every provider attempt has a 10-second absolute network deadline in addition to HTTPX's
per-operation timeouts. Stalled attempts are cancelled and follow the same bounded transport
retry path (three total attempts, ending in 502 `openalex_unavailable`). Caller cancellation
propagates; it is not retried as a transport failure. This is a per-attempt limit, not a
10-second overall endpoint deadline: multiple attempts and the sequential seed phase can
take longer. With waits capped at two seconds and three attempts, a provider operation has
at most 34 seconds of network/wait budget; a seed plus its concurrent neighbor phase has at
most 68 seconds, excluding local scheduling and normalization.

For HTTP 429 and 5xx responses, retry delays are the larger of the normal exponential
backoff (0.25 then 0.5 seconds) and the provider's `Retry-After`. Both delta-seconds and HTTP
dates are accepted. Past dates/negative delays become zero; malformed or non-finite headers
fall back to normal backoff. If the required delay exceeds two seconds, return the existing
503 `openalex_unavailable` immediately: do not sleep for a long rate-limit reset or retry
before it. The final failed attempt never sleeps or issues another request. Permanent
4xx errors are not retried. No global rate limiter or persistent cache is introduced.

Search pages, outgoing batches, and incoming pages larger than their requested size return
502 `openalex_invalid_response`, rather than processing arbitrary oversized lists. Within
valid batches, existing partial-response behavior is retained: skip/report malformed or
unresolved metadata, deduplicate, consume the selected slice, and never invent nodes or
create dangling edges. A whole direction failing remains an error, not a partial success.

Offline tests in `test_pagination_performance.py` cover Retry-After parsing and bounded
waits, hard timeout cancellation, the search paging boundary, oversized pages, concurrent
neighbor operations, and sibling/caller cancellation. Existing relationship tests cover
complete traversal, slice/cursor progress, total limits, deduplication, and missing records.
Manual smoke checks remain the two-page examples in the preceding sections. To verify the
basic-search guard without a large download, request
`/papers/search?q=test&page=401&per_page=25` and expect 422.

Provider references: [paging limits](https://help.openalex.org/api/paging/),
[bulk-ID retrieval](https://help.openalex.org/api/get-single-entities/), and
[rate-limit guidance](https://help.openalex.org/api/errors/).

## API reliability policy (Task 6)

All paper retrieval uses the same Paper normalization. Bare DOIs, `doi:`-prefixed values,
and HTTP/HTTPS `doi.org` or `dx.doi.org` resolver URLs normalize to `https://doi.org/` links.
ASCII letters in the DOI are lowercased; non-ASCII identifier characters are preserved.
URL-encoded suffixes are decoded and safely re-encoded, so reserved identifier punctuation
is not mistaken for a query or fragment. Null/blank DOIs remain null. Resolver URLs with
unencoded query/fragment components or invalid DOI syntax are rejected rather than guessed.
Normalization checks syntax, not whether a DOI has been registered. No DOI is generated
from a title or other metadata. See [Crossref display guidance](https://www.crossref.org/display-guidelines/).

Title and author whitespace is trimmed. A blank display name falls back to the provider's
title; if both are missing/blank, the existing explicit label `Untitled work` is used. Blank
author names are omitted. Blank venue and landing-page strings become null. Existing missing
year/abstract/DOI/reference-count nulls and missing citation-count default zero are preserved.
Abstracts are reconstructed only from valid provider positions: nonnegative integer positions,
unique across words and contiguous from zero. Empty/missing indexes yield null. Invalid indexes
are treated as malformed metadata rather than repaired with invented text. A malformed seed or
detail record returns 502 `openalex_invalid_response`; malformed neighbor records are omitted
using the documented partial-response reporting.

Graph validation now enforces unique paper IDs, unique directed paper pairs, unique citation
IDs, and existing endpoints. Reciprocal edges remain distinct. Relationship responses must
include their seed, and every edge must touch that seed. References additionally require
`source == seed_paper_id`; incoming citations require `target == seed_paper_id`. Services
deduplicate before building these validated responses. Multiple context-specific edges for
the same directed pair would require a future contract change; this API returns one per pair.

HTTP decoding failures return 502 `openalex_invalid_response`; other non-transport request
errors return 502 `openalex_error` without retrying. Transport failures keep the bounded retry
policy from Task 5. Unexpected programming/runtime failures remain generic 500 `internal_error`
responses with diagnostics confined to backend logs, and do not stop the application. Error
responses do not reflect provider response bodies or raw exception strings.

OpenAlex credentials are sent only as backend `Authorization: Bearer ...` headers, never query
parameters or response fields. The frontend reads only its public API base URL. Local backend
and frontend environment files stay Git-ignored. Tests use synthetic credentials and confirm
header-only use across search, details, references, incoming citations, and neighbors. Retrieval
continues to work with no database and no model artifact; expansion never calls inference.

Tests in `test_api_reliability.py` cover normalization, duplicate/seed/direction constraints,
missing metadata, abstract positions, request errors, key isolation, and health after failures.
For frontend integration and the final backend handoff, see [Citation API handoff](CITATION_API_HANDOFF.md).

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

Graph returns `{papers: Paper[], citations: Citation[]}`. All citation endpoints must appear in papers, and paper IDs must be unique. Neighbors adds the pagination metadata documented above; year filtering is not implemented.

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
