# Milestone 6 — Selected-edge OpenAlex TEI fallback

## Delivered behavior

The existing `POST /api/v1/citation-contexts/classify` now supports **Semantic Scholar → OpenAlex TEI → explicit unavailable**. Request fields and classifier output remain unchanged. No second OpenAlex-specific endpoint is needed.

The coordinator first uses the existing primary retrieval mode and caches. A verified primary passage within the inference length limit returns immediately. Otherwise, an enabled TEI service with a nonempty backend OpenAlex key independently reads the citing work's OpenAlex metadata and requires the exact cited ID in `referenced_works`. It verifies both work identities, confirms structured content availability and the official work-specific content URL, then downloads/parses the citing document. Missing Semantic Scholar evidence is never treated as a negative OpenAlex relationship.

The source's absence of a header DOI is accepted only through the authenticated official work-specific content binding with no contradictory explicit header identifiers. Present DOI/arXiv/PMID/PMCID/MAG identifiers must agree with authoritative work metadata and explicit aliases. BART uses this documented provider-binding trust boundary; BioBERT additionally has a matching header DOI. Titles/authors are not used to choose or match a reference.

`examples` remains offline and never invokes fallback. GET retrieval does not initiate TEI downloads, but its `auto` mode can return evidence previously cached by classification. If TEI is disabled or no key is configured, old primary behavior is preserved. Database access and installed artifacts are not required for retrieval; explicit classification still returns the existing model-unavailable error when artifacts are missing.

## Files created and modified

- New `apps/api/app/services/openalex_tei.py`: authenticated bounded transport, safe parser, exact bibliography/marker index, evidence extraction and provider caches.
- `app/services/citation_contexts.py`: selected-classification coordinator and bounded final fallback-result cache. Milestone 4 matching, primary limiter and retries remain intact.
- `app/api/v1/citation_contexts.py`: existing classification POST uses the coordinator.
- `app/schemas/citation_contexts.py`: additional source enum values and optional provenance/diagnostic fields.
- `app/core/config.py` and `.env.example`: `OPENALEX_TEI_ENABLED=true`, with the existing backend key setting reused.
- `apps/api/pyproject.toml` and `uv.lock`: added only `defusedxml==0.7.1` as a runtime XML safety dependency; trained-model dependencies/artifact unchanged.
- New `apps/api/tests/test_openalex_tei.py` and `tests/fixtures/tei/`: offline regression/safety/workflow tests, original recorded BART/BioBERT XML, attributed fixture metadata and README.
- `docs/API_CONTRACT.md`, `CITATION_CONTEXTS.md`, this report, and separate [live](reports/openalex_fallback_live.json) / [offline cohort](reports/openalex_fallback_offline.json) evidence.

All uncommitted Milestone 4/5 work is retained. No frontend or database files were modified. The primary HTTP client lifecycle is reused: one service/cache per application lifespan. No training, data download, model replacement, commit, branch switch, merge, rebase or push occurred.

## Verification and filtering rules

A bibliography entry matches only if it shares an exact DOI, arXiv, PMID, PMCID, MAG or explicit authoritative metadata URL with the target work. Identifier parsing reuses Milestone 4 helpers. Multiple matching bibliography entries, duplicate local bibliography IDs or contradictory comparable identifiers fail closed. Metadata URLs are compared conservatively; no publisher website is scraped and no title similarity is used.

The selected entry must be referenced by an actual local `ref type="bibr" target="#..."` marker inside a body sentence. The parser keeps the original decoded sentence text, selected marker text, bibliography ID/text, other linked citation targets and section path. Multiple citations do not become an exclusive single-paper claim. Unknown linked local bibliography IDs make a sentence ineligible; unlinked citation text remains in its original sentence.

Abstracts, headers, back matter, bibliography, notes, figures, tables/cells and explicit abstract/reference sections are excluded. Eligible sentences must have terminal punctuation, length 30–20,000 characters, no control/replacement characters and no nested sentence ambiguity. Numeric/table signatures conservatively reject flattened dataset-table artifacts, including the actual BioBERT cases. This is a narrow policy: legitimate quantitative sentences may be rejected, and universal table or OCR understanding is not claimed. No truncation or reconstruction of sentence text occurs. At most three unique passages are returned.

The parser supports standard TEI and the documented older embedded/lowercase layout. `defusedxml` forbids DTDs, entities and external resource resolution. Incremental parse events enforce at most 50,000 nodes and depth 64 while parsing. No XInclude processing, XML network lookup, PDF download or arbitrary URL fetch is performed. [Parser security documentation](https://pypi.org/project/defusedxml/)

## Bounds, transport and caching

| Resource / operation | Policy |
| --- | --- |
| XML body | Maximum 10,000,000 decoded bytes; streamed and size checked |
| Metadata body | Maximum 2,000,000 decoded bytes |
| Parsed index | Bounded text/index budget, at most 2,000 bibliography entries and 5,000 safe indexed sentences; references exceeding 4,000 characters cannot match |
| Parsed documents | LRU/TTL cache, maximum 16 citing work IDs, 24-hour successful lifetime |
| Metadata | Maximum 64 work IDs, 24-hour successful lifetime |
| Unavailable results | Five-minute negative cache, including access failures, malformed data and transport failures |
| Final selected-pair fallback outcomes | Maximum 128 entries, five minutes; normal evidence cache also remains bounded |
| Concurrent fallback work | Two active operations; same-resource loads coalesced through existing `ResourceCache` |
| Fallback deadline | 30 seconds including queue wait; each HTTP attempt has a 10-second timeout; parsing additionally has explicit structural bounds |
| HTTP attempts | One per resource, no automatic retries and no redirects |
| HTTP 401/403/429 | Shared TEI cooldown of at least five minutes, or longer numeric/date Retry-After |

The service caches parsed bibliography/marker indexes, not a new on-disk full-text library. One downloaded document serves many selected outgoing edges. In-flight/cache copies isolate callers from mutation. Last-waiter cancellation follows existing cache behavior; requests already received upstream cannot be undone. Parsing runs outside the event loop and has fixed size/structure bounds rather than arbitrary execution.

`OPENALEX_API_KEY` is sent only as an Authorization bearer header. Source response bodies, secret headers and redirect destinations are not logged or returned. Only the exact official content URL supplied by OpenAlex is eligible; redirect responses become unavailable rather than forwarding credentials to a new host. These restrictions can reject future provider URL/redirect changes safely. [Official OpenAlex content API](https://help.openalex.org/access/fulltext/)

The existing Semantic Scholar scheduler and its single-worker/instance-per-key restriction remain unchanged. Its primary lookup time precedes the fallback's 30-second budget. Do not assume total cold classification always fits the frontend's existing 35-second search timeout.

## API contract and frontend consumption

Use the same POST for either evidence source:

```powershell
$body = @{
  citing_paper_id = "W2982399380"
  cited_paper_id = "W1614298861"
  mode = "auto"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/citation-contexts/classify" -ContentType "application/json" -Body $body
```

Successful response excerpt (additional existing fields omitted):

```json
{
  "citing_paper_id": "W2982399380",
  "cited_paper_id": "W1614298861",
  "status": "available",
  "available": true,
  "source": "openalex_tei",
  "origin": "live",
  "relationship_found": true,
  "contexts": [{
    "source": "openalex_tei",
    "source_url": "https://content.openalex.org/works/W2982399380.grobid-xml",
    "source_url_scope": "document",
    "bibliography_id": "b17",
    "citation_marker": "(Mikolov et al., 2013;",
    "section": ["Introduction"],
    "identity_evidence": ["ARXIV:1301.3781"],
    "document_identity_method": "authenticated_provider_binding",
    "classification": {
      "intent": "background",
      "confidence": 0.8843842684202584,
      "model_version": "scicite-tfidf-logreg-v1"
    }
  }]
}
```

The complete response retains the original `context_text`, bibliography text, other local citation targets, document hash and capture time. The live evidence file contains the exact captured API response and original source sentence. The same sentence/score as Milestone 5 was reproduced. Scores remain uncalibrated model predictions, not a new labeled accuracy evaluation.

When both sources fail after an enabled/keyed fallback attempt, POST can return HTTP 200 with an explicit unavailable object:

```json
{
  "status": "provider_unavailable",
  "available": false,
  "reason": "semantic_scholar_rate_limited",
  "fallback_reason": "tei_bibliography_not_verified",
  "contexts": []
}
```

That is an illustrative unavailable response excerpt from the offline scenario, not another live result. A primary `no_context`, `unresolved_identifiers`, `incomplete` or other no-usable-evidence result is retained when TEI fails, with the TEI reason added. Model failures retain HTTP 503/500; validation remains 422. Without a configured/enabled fallback, previous primary HTTP errors remain unchanged. Consumers must inspect `available`/`status`, not just HTTP 200.

New optional passage fields default to null for existing Semantic Scholar/example evidence. Source enums now include `openalex_tei`; the source scope includes `document`. `PaperMapping.verified` for TEI indicates provider-bound OpenAlex identity, not a Semantic Scholar mapping; its Semantic Scholar ID can be null. `reference_scan_complete=false` does not claim a completed Semantic Scholar reference-list scan.

For frontend integration, add the source/provenance types to the existing single classification request path, render source/section/marker as plain text, show capture time/cache origin and model version, preserve null classification when unavailable, and retain loading/cancellation/error states. Avoid automatic retry loops and all-edge classification on expansion. Account for cold primary-plus-fallback latency. No new UI or separate provider-specific workflow is implemented here.

## Offline verification

The unchanged recorded Milestone 5 XML and selected metadata are attributed in the fixture README. Metadata fixture reference lists contain only independently verified selected edges from the historical cohort; they are not full live reference lists. All upstream calls in the tests are mocked.

The eleven-pair HTTP replay used the actual classification endpoint and saved model, with Semantic Scholar failure simulated:

| Cohort | Recovered automatically | Remaining result |
| --- | ---: | --- |
| Four BioBERT no-context pairs | 0/4 | No exact bibliography identity; actual table fragments are also rejected |
| Seven BART pairs | 1/7 | Six lack exact verifiable bibliography identifiers |
| Total | 1/11, one classified sentence | Ten explicit unavailable results |

Only two mocked content downloads served all eleven POSTs. The successful pair is BART `W2982399380` → `W1614298861`, bibliography `b17`, arXiv `1301.3781`, Introduction. The other target IDs and full reason codes are retained in [offline evidence](reports/openalex_fallback_offline.json). This is the same scientific recovery as Milestone 5, now through the automatic backend workflow—not a new ten-pair coverage gain.

The new tests cover the real BART score, BioBERT negatives/table artifacts, all supported exact namespaces, contradictions/ambiguity/missing IDs, body exclusions, multiple markers, malformed/DTD/entity XML, missing/contradictory header IDs, size/depth/node/deadline bounds, disabled/missing credentials, HTTP 401/403/404/429/5xx, transport failures, positive/negative cache and expiry, concurrent document reuse, primary success, primary failures, and HTTP-level failover/unavailable responses.

## Limited live verification

One new live verification ran **November 14, 2026 at 11:28:26 a.m. EST (16:28:26 UTC)** through an owned temporary Uvicorn server. Semantic Scholar exhausted throttling was simulated deliberately; **zero real Semantic Scholar calls** were made. OpenAlex metadata and content requests were real and authenticated.

Three HTTP 200 upstream calls fetched BART metadata (including outgoing IDs), the cited work metadata and BART TEI. The API returned HTTP 200 with `source="openalex_tei"`, the real original sentence and `background` confidence **0.8843842684202584**. End-to-end time was **1.055 seconds**. A repeated POST used **zero upstream calls**, returned `origin="memory_cache"`, and took **0.0078 seconds**. The temporary server was stopped.

The downloaded XML hash matches Milestone 5's source. The model SHA-256 remains `cb798df60c932deeeff4c15f8760c2de9fc27be07e6be95c6f3e403f02893d96`. This verifies independent OpenAlex fallback behavior, not present-day Semantic Scholar availability. Three live requests are the entire new provider volume for this milestone.

## Checks and readiness

Commands executed from the repository root with workspace-local uv/Python paths:

```powershell
npm run lint
npm run typecheck
npm run test
npm run build
uv run --project apps/api pytest apps/api/tests -q
uv run --project apps/api pytest apps/api/tests/test_openalex_tei.py -q
```

Final backend result: **473 passed**, including 44 new TEI tests. Frontend: **6 passed**. ESLint, Ruff lint/format, TypeScript and production build passed. The existing Starlette/httpx TestClient deprecation warning remains. The final full backend run includes three added safety/cache/limit cases after the root run's earlier 470-test pass. No failures remain.

Research commands used ignored local runners `.cache/m6/live_http.py` (one live HTTP check) and `.cache/m6/offline_cohort.py` (eleven-pair mocked HTTP replay); the resulting sanitized evidence files are retained for review. The unit tests are the reproducible offline integration harness for future checkouts.

The backend is ready for a selected-edge frontend integration using the existing POST and the updated source types. Keep the strict unavailable results; do not relax identity checks to increase demo coverage. Broader evaluation should precede more permissive extraction. The historical Semantic Scholar **14/28** baseline has not been rerun, and no comparable new 28-pair coverage claim is made.

Changes remain uncommitted on `dev-ml`, alongside the preserved earlier milestones. No credentials were changed by the agent or written into Git-visible files, and nothing was pushed.
