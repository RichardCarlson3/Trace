# Authenticated live citation verification — 2026-11-14

Authenticated retrieval works for previously unrecorded papers. The current service supports selected-edge integration with explicit unavailable states. Uniform arbitrary-paper coverage and predictable cold-request latency remain limited by upstream throttling and DOI coverage. No frontend, database or model-training changes were made.

## Method and evidence

The primary follow-up ran **09:31:53–09:35:44 UTC**, using a real configured Semantic Scholar key in `x-api-key`, public OpenAlex access, the existing saved SciCite model and cold process-local caches. It resolved four publication DOIs through OpenAlex and selected the **first seven outbound reference IDs in each returned list before inspecting Semantic Scholar coverage**. All 28 directed pairs were outside the three bundled SciBERT examples. Their membership in OpenAlex `referenced_works` independently establishes OpenAlex citation direction; the service additionally requires exact DOI agreement and the citing paper's Semantic Scholar outbound reference record before classifying.

The seeds were Sentence-BERT (`W2970641574`), ELMo / Deep Contextualized Word Representations (`W2787560479`), BART (`W2982399380`) and BioBERT (`W2911489562`). This convenience sample covers NLP and biomedical NLP, not all scientific disciplines. It is an integration check, not a new labeled classifier evaluation.

[Machine-readable evidence](reports/live_citation_verification.json) retains paper mappings, DOI/Semantic Scholar IDs, source URLs, timestamps, request accounting, predictions and passage checksums. Exact untouched passages remain locally in ignored `.cache/live-citations/report.json` and `http_smoke.json`. The report contains no credentials or upstream error bodies. Reproduce explicitly with `uv run --project apps/api python apps/api/scripts/verify_live_citations.py`; provider data and quotas can change.

## Results

| Measure | Follow-up result |
| --- | ---: |
| Unique previously unrecorded relationships | 28 |
| Both paper mappings verified on the initial pass | 18 |
| Verified relationship with genuine passages | 14 |
| Relationships successfully classified | 14 |
| Actual passages returned / classified | 28 / 28 |
| Retrieval coverage across all selected pairs | 50.0% |
| Context coverage among mapped pairs | 77.8% (14/18) |
| Verified relationship with no passages | 4 |
| Unresolved mapping | 8 |
| Exhausted upstream rate limiting | 2 |
| Incomplete reference scans | 0 |
| Actual Semantic Scholar requests, including repeat pass | 56 |
| HTTP 429 responses | 25 |
| Minimum measured request-start spacing | 1.500 seconds |
| Median / maximum provider response-header latency | 0.156 / 0.390 seconds |
| Median / maximum completed retrieval latency | 4.563 / 27.828 seconds |
| Median / maximum end-to-end classification operation | 4.602 / 27.828 seconds |

The classification timing includes retrieval, scheduling, retries and lazy model loading, with no inference for unavailable passages. Times are approximate Windows monotonic-clock measurements. The initial pass used 55 Semantic Scholar calls: 29 HTTP 200, 25 HTTP 429 and one HTTP 404. The repeat pass added one successful metadata call. All 56 calls carried the authentication header. Scheduling waits and retry delays dominate network latency; model prediction adds milliseconds after the first load.

There were **three successful reference-page downloads** serving all 18 mapped initial-pass relationships, plus four failed reference attempts. The reference cache recorded 17 hits and four loads (one load exhausted retries). The mapping cache recorded 28 hits and 32 loads. Repeating all 28 pairs in `auto` required only **two total upstream calls** (one OpenAlex, one Semantic Scholar) in 4.516 seconds, to retry a previous failure; other results used cached evidence. This repeats unavailable mapping results truthfully as well as successful passages. A cache origin describes the reference evidence: mapping a new target can still make a live metadata call.

OpenAlex search through the existing `OpenAlexService` succeeded, returning `W2970641574` and `W2971193649`. Its previously configured credential returned HTTP 401; the user cleared it locally. Provider search code was preserved.

## Per-relationship outcomes

`Mapped/found` means both DOI mappings verified / outbound Semantic Scholar reference observed. `Unknown` preserves missing evidence. `Passages/classified` counts actual contexts, not titles. Request counts are Semantic Scholar / OpenAlex, excluding four initial OpenAlex discovery calls and the repeat/search phases. All available cases have complete reference scans. HTTP 429 entries include recovered retries. A missing relationship in one provider does not disprove the OpenAlex edge.

| Citing ID | Cited ID | Mapped/found | Outcome | Passages/classified | Evidence origin | Requests S2/OA | HTTP errors | Total seconds | Reason |
| --- | --- | --- | --- | ---: | --- | ---: | --- | ---: | --- |
| W2970641574 | W1486649854 | yes/yes | available | 1/1 | live | 3/2 | - | 4.016 | - |
| W2970641574 | W1840435438 | yes/yes | available | 6/6 | memory_cache | 1/1 | - | 0.703 | - |
| W2970641574 | W1980776243 | yes/yes | available | 1/1 | memory_cache | 1/1 | - | 1.718 | - |
| W2970641574 | W2014902591 | yes/yes | available | 2/2 | memory_cache | 3/1 | 429,429 | 7.625 | - |
| W2970641574 | W2070246124 | yes/yes | available | 4/4 | memory_cache | 1/1 | - | 3.407 | - |
| W2970641574 | W2096733369 | yes/yes | available | 1/1 | memory_cache | 1/1 | - | 3.344 | - |
| W2970641574 | W2114524997 | yes/yes | available | 1/1 | memory_cache | 3/1 | 429,429 | 12.688 | - |
| W2787560479 | W6908809 | yes/yes | available | 1/1 | live | 6/2 | 429,429,429 | 27.828 | - |
| W2787560479 | W581956982 | no/unknown | unresolved_identifiers | 0/0 | live | 0/1 | - | 0.140 | missing_doi |
| W2787560479 | W1026270304 | yes/yes | available | 3/3 | memory_cache | 3/1 | 429,429 | 13.563 | - |
| W2787560479 | W1522301498 | yes/yes | available | 1/1 | memory_cache | 3/1 | 429,429 | 13.781 | - |
| W2787560479 | W1539309091 | yes/yes | available | 3/3 | memory_cache | 1/1 | - | 4.484 | - |
| W2787560479 | W1632114991 | unknown/unknown | upstream_error | 0/0 | unavailable | 3/1 | 429,429,429 | 13.766 | semantic_scholar_rate_limited |
| W2787560479 | W1840435438 | yes/yes | available | 2/2 | memory_cache | 0/0 | - | 0.016 | - |
| W2982399380 | W131533222 | no/unknown | unresolved_identifiers | 0/0 | live | 2/2 | 429,404 | 9.609 | semantic_scholar_work_not_found, missing_doi |
| W2982399380 | W1544827683 | no/unknown | unresolved_identifiers | 0/0 | live | 2/1 | 429 | 8.953 | semantic_scholar_work_not_found |
| W2982399380 | W1599016936 | no/unknown | unresolved_identifiers | 0/0 | live | 0/1 | - | 0.125 | semantic_scholar_work_not_found, missing_doi |
| W2982399380 | W1614298861 | no/unknown | unresolved_identifiers | 0/0 | live | 1/1 | - | 4.360 | semantic_scholar_work_not_found |
| W2982399380 | W2130158090 | no/unknown | unresolved_identifiers | 0/0 | live | 1/1 | - | 4.359 | semantic_scholar_work_not_found |
| W2982399380 | W2251939518 | no/unknown | unresolved_identifiers | 0/0 | live | 1/1 | - | 4.594 | semantic_scholar_work_not_found |
| W2982399380 | W2418388682 | no/unknown | unresolved_identifiers | 0/0 | live | 3/1 | 429,429 | 13.734 | semantic_scholar_work_not_found |
| W2911489562 | W1981208470 | unknown/unknown | upstream_error | 0/0 | unavailable | 6/2 | 429,429,429,429 | 27.563 | semantic_scholar_rate_limited |
| W2911489562 | W2047782770 | yes/yes | no_context | 0/0 | live | 3/1 | 429 | 13.937 | - |
| W2911489562 | W2052217781 | yes/yes | no_context | 0/0 | memory_cache | 2/1 | 429 | 9.172 | - |
| W2911489562 | W2071879021 | yes/yes | no_context | 0/0 | memory_cache | 1/1 | - | 4.531 | - |
| W2911489562 | W2100627415 | yes/yes | available | 1/1 | memory_cache | 2/1 | 429 | 9.141 | - |
| W2911489562 | W2136437513 | yes/yes | no_context | 0/0 | memory_cache | 1/1 | - | 4.609 | - |
| W2911489562 | W2149369282 | yes/yes | available | 1/1 | memory_cache | 1/1 | - | 4.375 | - |

## Separate runs and final HTTP checks

The earlier baseline run tested 21 of these same pairs at a fixed 1.5-second interval: 13 mapped, 12 had passages, and all 26 passages were classified; coverage was 57.1%. It made 39 Semantic Scholar requests including repeats, received 17 HTTP 429 responses and measured a 1.500-second minimum gap. The follow-up added BioBERT and adaptive pacing up to 4.5 seconds. **It did not establish a reduction in throttling**: provider conditions and sample composition changed, and HTTP 429 persisted. The two runs overlap and must not be counted as 49 distinct relationships.

The final implementation was also exercised through an owned temporary Uvicorn server over real local HTTP. Two concurrent Sentence-BERT relationships returned HTTP 200 with seven genuine passages, all classified. They shared one successful reference response, requiring eight Semantic Scholar attempts total (four HTTP 429), and completed in 25.378 seconds. Repeating both used zero upstream calls. Disabling the provider then classified all three recorded examples with HTTP 200 and zero upstream calls; health and OpenAPI also returned HTTP 200. The temporary server was stopped.

Across both verification runs and the final HTTP smoke check, **103 Semantic Scholar requests** were recorded, with **46 HTTP 429 responses**. Two earlier credential-status probes add two Semantic Scholar requests (one HTTP 429, one HTTP 200), giving **105 total actual Semantic Scholar requests for this task**, of which 47 returned HTTP 429. Offline fixtures and recorded examples generated no provider requests and are excluded. Local evidence files retain the two runs separately.

## Full-text fallback decision

A full-text system is **not required to integrate selected-edge classification for the hackathon**. Broad coverage is materially incomplete: four of six mapped BioBERT edges had no Semantic Scholar passages, and all seven BART pairs were blocked by the citing DOI lookup's HTTP 404. More scheduling cannot supply absent passages or resolve missing DOI records.

A metadata-only live check found `has_content.grobid_xml=true`, a TEI URL and `cc-by` for all four citing works, including BioBERT and BART. No full-text files were downloaded and no extractor was implemented. OpenAlex documents keyed, metered TEI downloads and warns about parsing errors and differing XML layouts. Its content API requires a valid key, which is currently absent locally. [Official full-text documentation](https://help.openalex.org/access/fulltext/)

Recommend a **bounded TEI feasibility follow-up** if biomedical/BART coverage is required, after investigating the still-persistent Semantic Scholar quota responses. It would download and cache a citing document once, verify its identity, resolve bibliography DOIs to selected cited IDs, extract only linked citation sentences, and retain section/source provenance. This can bypass missing Semantic Scholar passages but adds download latency, usage cost, XML/version handling, bibliography ambiguity, licensing checks and a second failure path. Estimate **2–4 developer days** for a tested DOI-only fallback and another day of cross-paper evaluation; this is an engineering estimate, not measured work. Start with the four demonstrated missing BioBERT contexts. Do not fall back to titles, abstracts or fuzzy reference guesses.

## Regression and integration readiness

- Backend: **177 tests passed**, including training, inference, contexts and cache/concurrency tests; one existing Starlette/httpx deprecation warning.
- Frontend: **6 tests passed**; ESLint, Ruff lint/format, TypeScript checks and production build passed. No frontend files were edited.
- Saved model SHA-256 remains `cb798df60c932deeeff4c15f8760c2de9fc27be07e6be95c6f3e403f02893d96`.
- Deployment is constrained to **one backend worker and one instance per API key**. The lifespan service owns all Semantic Scholar requests; multiple processes or outside callers require shared coordination.
- API shapes and inference contracts are preserved. `live` now excludes examples and the pair cache while reusing provider resource caches; this behavior change is documented in `API_CONTRACT.md`. Cached capture times and provenance are retained.
- Before Developer 1 integrates: show origin/capture time, selected passage and source; keep intent/confidence null when unavailable; support loading and retry for slow cold lookups. Do not classify all graph edges on expansion. Persistent upstream 429s mean consistently fast arbitrary-paper retrieval is not yet demonstrated.

Files changed for this follow-up: `app/services/citation_contexts.py`, new `app/services/resource_cache.py`, `app/core/config.py`, `.env.example`, new explicit `scripts/verify_live_citations.py`, citation-context/cache tests, and retrieval/API/report documentation. Existing Milestones 1–3 work remains in place on `dev-ml`; no branch switch, merge, commit or push was performed.
