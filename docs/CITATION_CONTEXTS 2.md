# Citation contexts and the hackathon demo

ResearchGraph keeps OpenAlex as its scholarly-data integration. Citation passages come from an optional Semantic Scholar provider or a small set of recorded, verified examples. The main application starts and paper search operates with Semantic Scholar disabled, without a key or model artifacts.

The repository default is `SEMANTIC_SCHOLAR_ENABLED=false`. Configure a backend-only API key and enable the provider locally for authenticated retrieval. The three bundled examples work offline. Their contexts were captured from successful live API responses on 2026-11-14. Later anonymous requests returned HTTP 429, so identifier and reference matching were also verified by replaying those recorded responses through the service. A replay is recorded evidence and is labeled `verified_example` in the API. Authenticated verification of previously unrecorded pairs is reported separately in [the live retrieval report](LIVE_CITATION_VERIFICATION.md).

## Run the demo in PowerShell

From the repository root, start the existing backend command. The existing artifact pair enables classification.

```powershell
npm run dev:api
```

Retrieve the recorded SciBERT -> BERT passage without classification.

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/citation-contexts?citing_paper_id=W2970771982&cited_paper_id=W2963341956&mode=examples" | ConvertTo-Json -Depth 10
```

Explicitly classify the retrieved passage using the existing local SciCite model.

```powershell
$body = @{
  citing_paper_id = "W2970771982"
  cited_paper_id = "W2963341956"
  mode = "examples"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/citation-contexts/classify" -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 10
```

Both interfaces accept canonical OpenAlex work IDs. Full OpenAlex work URLs are normalized using the existing contract helper. The direction is always `citing_paper_id -> cited_paper_id`. The request accepts IDs and a retrieval mode. Passages are obtained by the service.

## Source and retrieval modes

| Mode | Behavior |
| --- | --- |
| `auto`, default | Use a fresh memory-cache result, then a matching verified example, then optional live retrieval |
| `examples` | Use the recorded examples only, with no provider HTTP requests |
| `live` | Exclude recorded examples and the final relationship cache; reuse fresh provider mappings and reference pages, requiring enabled live-provider configuration |

Every result has an `origin` field with `live`, `memory_cache`, `verified_example` or `unavailable`. `retrieved_at` records when evidence was captured. `evidence_urls` records the references request. Each passage has a `source_url` and `source_url_scope="paper"`, identifying the citing paper. The source does not supply a precise passage anchor through this interface.

Live results use the bounded process-local caches below. Cached results preserve the original evidence capture timestamp. Copies prevent a caller's classification or UI changes from modifying cached evidence. Classifications are generated through the existing inference service when explicitly requested, only for the selected relationship.

| Resource | Capacity | Lifetime | Cache key |
| --- | ---: | --- | --- |
| Verified paper mappings | 512 | 24 hours; unresolved mappings 5 minutes | OpenAlex work ID |
| Semantic Scholar DOI metadata | 512 | 24 hours; missing records 5 minutes | Normalized DOI |
| Reference pages | 128 | 15 minutes | Citing Semantic Scholar ID, fields, limit and offset |
| Final relationship evidence | 128 | 5 minutes | Directed OpenAlex ID pair |

Concurrent lookups for the same pair, mapping, DOI metadata or reference page share one in-flight operation. Each cache limits distinct pending resources to 128. Capacity pressure returns a truthful HTTP 503 `citation_context_busy`. Provider errors are not stored as successful resource-cache values. Cancelling one waiter preserves other waiters; cancelling the last waiter cancels queued I/O and retries. Cancellation cannot undo a request already received upstream.

`live` now means live-provider evidence, with normal provider caches, rather than an unconditional refresh of every upstream resource. It never uses the three bundled examples. A fully cached reference scan has `origin="memory_cache"`, including when mapping a previously unseen target required a metadata request. Mixed cached and fresh pages have `origin="live"` and the oldest page capture time. Provider caches are refreshed after TTL expiry or process restart. The final pair cache can retain evidence for up to another five minutes. An unrelated cited-paper edge reuses the citing paper's reference pages and does not download its entire reference list again.

To opt into live calls, configure the backend environment and restart the API.

```dotenv
SEMANTIC_SCHOLAR_ENABLED=true
SEMANTIC_SCHOLAR_BASE_URL=https://api.semanticscholar.org/graph/v1
SEMANTIC_SCHOLAR_API_KEY=
```

A key is sent only in the `x-api-key` header; the local verification command requires it. Anonymous access remains optional and uses shared quotas. The approved key limit is one request per second cumulatively across endpoints, matching the official introductory quota. All Semantic Scholar calls go through the lifespan service's shared async lock and scheduler, with at least **1.5 seconds between starts**. HTTP 429 raises the spacing by a factor of 1.5 up to 4.5 seconds, with gradual recovery after eight successful responses. This reduces pressure but does not guarantee that the provider will never throttle. [Semantic Scholar API overview](https://webflow.semanticscholar.org/product/api)

Requests use a 10-second HTTP timeout, a 30-second scheduler/attempt deadline and at most three attempts. Transport failures, HTTP 429 and HTTP 5xx use exponential backoff plus jitter, capped at five seconds. Numeric/date `Retry-After` is honored as a minimum delay. A cooldown above five seconds returns unavailable immediately and is retained across endpoints, rather than retrying early. The cooldown is published while holding the scheduler lock. Permanent HTTP errors are not retried. Cancellation propagates without restarting the retry loop. In `auto` mode, provider failures become explicit unavailable results; `live` uses the existing HTTP 502/503 envelope. Upstream response bodies, credentials and private transport diagnostics are excluded from service errors.

## Supported deployment

Use **exactly one backend worker and one backend instance per Semantic Scholar key** for this hackathon. All citation retrieval must use `request.app.state.citation_contexts`; creating independent services bypasses shared coordination. The in-memory limiter and caches do not coordinate across processes, machines, developer scripts or other applications using the same key. Run the live verification command while other clients of that key are idle. A scaled deployment needs a shared scheduler/cooldown, such as Redis or a single provider gateway, before increasing workers or replicas.

From the repository root, run the API without reload in a deployed demo:

```powershell
uv run --project apps/api uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

`npm run dev:api` remains the existing single-serving-process development command. It reloads application code and clears caches on restart. Keep both provider keys in ignored `apps/api/.env`. Credential settings are excluded from the settings object's representation. No credentials belong in frontend configuration, report output, URLs or source control.

Explicitly run real-world verification separately from offline tests:

```powershell
uv run --project apps/api python apps/api/scripts/verify_live_citations.py
```

The command requires an enabled provider and a nonempty key. It starts cold caches, resolves four publication DOIs through OpenAlex, selects the first seven outbound reference IDs per seed before checking Semantic Scholar availability, and records 28 pairs. It records exact retrieved passages, model results, provenance, per-pair upstream counts, HTTP statuses, latency and cache reuse in ignored `.cache/live-citations/report.json`. Output never includes request headers or upstream error bodies. These are convenience samples in NLP/biomedical NLP, not an estimate of all scientific disciplines or classification accuracy.

## Identifier and relationship verification

The service reads each requested work's explicit DOI from OpenAlex. It normalizes DOI strings, resolver URLs, case and URL encoding, and detects conflicting DOI fields. It requests the Semantic Scholar record with `DOI:<doi>` and requires its returned `externalIds.DOI` to match. Missing, conflicting or unverified mappings produce `unresolved_identifiers`. This first provider supports DOI-based mappings. Works without a usable DOI remain unresolved.

Once both mappings are verified, the service requests the citing paper's references with `contexts,externalIds`. It matches the cited paper by its verified Semantic Scholar ID or an exact verified DOI when the reference lacks an ID. Conflicting IDs/DOIs remain unresolved. Titles are display metadata and are excluded from matching.

All nonblank matching passages are preserved in source order, with exact duplicates removed. Context strings retain the source's line breaks, spelling and extraction artifacts. Pagination follows the provider's `next` offset, with a cap of five pages of 100 references. Results report `reference_scan_complete`; reaching the cap produces `incomplete` rather than a conclusion that the relationship is absent. [Semantic Scholar references specification](https://api.semanticscholar.org/graph/v1/swagger.json)

The provider also offers a cited paper's `/citations` endpoint with `citingPaper` records and context arrays. This implementation uses outbound `/references` to preserve the requested citing-to-cited direction and avoid scanning a popular paper's incoming citations.

## Response states

| Status | Meaning |
| --- | --- |
| `available` | Verified relationship with one or more nonblank passages |
| `no_context` | Matching relationship with absent, null, empty or blank context entries |
| `relationship_not_found` | No verified matching reference in the completed returned list |
| `unresolved_identifiers` | Publication identity or relationship matching could not be verified |
| `incomplete` | Bounded reference scan ended before the provider's list ended |
| `provider_unavailable` | Live provider is disabled or failed in `auto` mode |
| `example_not_found` | No recorded example for an `examples` request |

`available` is computed from the returned passages. `relationship_found` is true for an observed matching relationship and null when identity or an incomplete scan prevents a determination. A missing context or an unmatched Semantic Scholar record does not disprove an OpenAlex citation edge. `reason` and mapping-specific reasons explain unresolved or unavailable outcomes.

`contexts` contains the exact passage, source attribution, paper-level URL and nullable `classification`. The classification object uses the existing `intent`, `confidence` and `model_version` contract. Scores are uncalibrated. A passage exceeding the existing 20,000-character inference limit is preserved with `classification=null` and `classification_unavailable_reason="context_too_long"`. Empty or unresolved results make no inference calls. Missing model artifacts affect the explicit classification operation with HTTP 503 while retrieval remains usable.

## Verified examples

All three citing records are SciBERT by Iz Beltagy, Kyle Lo and Arman Cohan, OpenAlex `W2970771982`, DOI `10.18653/v1/d19-1371`, Semantic Scholar `156d217b0a911af97fa1b5a71dc909ccef7a8028`. The following passages are reproduced from the provider response with attribution to the paper, published under CC BY 4.0. The citation source URL for each is the citing paper's page. [SciBERT publication and licensing](https://aclanthology.org/D19-1371/), [Semantic Scholar citing-paper page](https://www.semanticscholar.org/paper/156d217b0a911af97fa1b5a71dc909ccef7a8028)

| Cited paper | OpenAlex ID | DOI | Semantic Scholar ID | Source passage count |
| --- | --- | --- | --- | ---: |
| BERT | `W2963341956` | `10.18653/v1/n19-1423` | `df2b0e26d0599ce3e70df8a9da02e51594e0e992` | 7 |
| Attention Is All You Need | `W2626778328` | `10.48550/arxiv.1706.03762` | `204e3073870fae3d05bcbc2f6a8e263d9b72e776` | 1 |
| Adam | `W1522301498` | `10.48550/arxiv.1412.6980` | `cf5cf758f1b00214d70e34f8a57813557dc03e17` | 2 |

Each bundled pair retains the first returned nonblank passage. `observed_context_count` retains the full count observed in the recorded response, making the representative selection explicit. The file `apps/api/app/examples/citation_contexts.json` contains the verified IDs, source URLs, capture timestamps, capture checksums, attribution and original passages. Its classification fields are empty. Predictions below came from executing the existing `scicite-tfidf-logreg-v1` Pipeline.

SciBERT -> BERT returned the following passage and a `method` score of **0.9856118818381374**.

> 3617 Casing We follow Devlin et al. (2019) in using the cased models for NER and the uncased models for all other tasks.

SciBERT -> Attention Is All You Need returned the following passage and a `method` score of **0.5567790219277727**.

> Background The B ERT model architecture (De-vlin et al., 2019) is based on a multilayer bidirectional Transformer (Vaswani et al., 2017).

SciBERT -> Adam returned the following passage and a `method` score of **0.8079501246169966**.

> We optimize cross entropy loss using Adam, but holding B ERT weights frozen and applying a dropout of 0.5.

The three selected passages had zero normalized exact-text matches and zero citing/cited-pair matches against the local SciCite test file. They demonstrate retrieval and inference integration. They do not constitute a labeled accuracy evaluation or exclude every possible near-duplicate.

## Consuming the service from the graph backend

The lifespan-managed instance is `request.app.state.citation_contexts`. Call `await service.retrieve(CitationPair(citing_paper_id=edge.source, cited_paper_id=edge.target))`. `auto` supports the offline demo. Enable the provider and select `live` for a fresh lookup. The graph backend can inspect the result and explicitly call `classify_contexts(result, request.app.state.inference)` using its worker-thread execution path, as the new classification route does.

Keep edge IDs as OpenAlex IDs. Copy a chosen passage's intent, score, exact context and source URL into the corresponding citation evidence fields only after successful classification. Retain model version, origin and capture time alongside the evidence as the graph integration develops. Missing evidence keeps intent and confidence null. The frontend can display `origin` and the citing-paper source link when this interface is connected. Graph expansion has no automatic classification added by this milestone. Use `auto` for normal on-demand edge requests, `live` when recorded examples should be excluded, and `examples` for an explicit offline demo.

## Tests

```powershell
uv run --project apps/api pytest apps/api/tests/test_citation_contexts.py
uv run --project apps/api --group training pytest apps/api/tests
uv run --project apps/api ruff check apps/api
uv run --project apps/api ruff format --check apps/api
```

Unit tests use synthetic HTTP fixtures. Bundled-example tests use recorded verified contexts and block provider HTTP requests. The separate live investigation and captured-response replay are described above to keep their evidence distinct from mocked unit tests. Tests cover matching, DOI normalization, direction, multiple passages, unavailable states, pagination, rate limits, timeouts, private headers, cache behavior and classification gating.
