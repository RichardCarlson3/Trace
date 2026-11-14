# Milestone 4 — Citation identifier resolution

## Implementation

Citation mapping previously used only the work's primary DOI and `ids.doi`. It did not examine repository locations, PMID, PMCID or MAG. Milestone 4 adds at most five prioritized exact lookups: **DOI → arXiv → PMID → PMCID → MAG**, one value per namespace. No title matching or identifier search is used.

- `apps/api/app/services/citation_identifiers.py`: citation-scoped DOI and alternative-ID parsing, extraction of explicit OpenAlex identifiers, and exact returned-identity checks. DOI punctuation and Unicode are preserved, with ASCII case folding, strict single URL decoding and rejection of malformed encodings/control characters. arXiv versions map to the work-level ID; PMID, PMCID and MAG use validated numeric forms. Conflicting identifiers fail closed.
- `apps/api/app/services/citation_contexts.py`: requests OpenAlex `locations`, uses the bounded fallback sequence and existing coalescing cache keyed by identifier namespace/value. The returned Semantic Scholar hash and echoed external ID are checked; comparable known identifiers must agree. Explicit OpenAlex location DOI aliases can verify another version of the same work. Successful work mappings retain their existing 24-hour cache, unresolved mappings five minutes; HTTP 404 metadata is cached for five minutes. Errors and rate limits retain existing behavior and do not trigger additional namespaces. Known DOI aliases are retained in a bounded 512-entry map for reference verification.
- Reference matching now requires an actual non-null DOI for DOI-only matching, preventing two missing DOIs from matching unrelated records. A verified Semantic Scholar hash can match a DOI-less target; known contradictory DOIs still fail closed.
- `apps/api/tests/test_citation_identifiers.py`: 33 synthetic offline regression cases covering parsing, alternatives, echoed identity, conflicting IDs, missing DOI reference matching, negative/success caches and bounded retries. Existing context tests remain unchanged.
- Documentation: this report, `CITATION_CONTEXTS.md`, `API_CONTRACT.md` and [sanitized live evidence](reports/identifier_resolution.json).

The request/response schemas, trained model, inference logic, resource-cache implementation, throttling scheduler, frontend and database are unchanged. Developer 2's normalization helpers are preserved; the new parsing is scoped to citation retrieval.

Official documentation confirms OpenAlex work identifiers and repository location IDs, and Semantic Scholar's DOI/ARXIV/PMID/PMCID/MAG lookup formats. These are exact provider identifiers, not title-derived candidates. [OpenAlex attributes](https://help.openalex.org/data/works/attributes/), [OpenAlex locations](https://help.openalex.org/data/locations/), [Semantic Scholar specification](https://api.semanticscholar.org/graph/v1/swagger.json).

## All eight baseline mapping failures

| Citing work | Cited work | Baseline cause |
| --- | --- | --- |
| ELMo `W2787560479` | `W581956982` | Target had no DOI; its explicit MAG ID was ignored |
| BART `W2982399380` | `W131533222` | BART ACL DOI lookup returned 404; target also lacked DOI |
| BART | `W1544827683` | Shared citing-paper DOI lookup failure; target DOI mapping was verified |
| BART | `W1599016936` | Shared citing-paper DOI lookup failure; target also lacked DOI |
| BART | `W1614298861` | Shared citing-paper DOI lookup failure; target DOI mapping was verified |
| BART | `W2130158090` | Shared citing-paper DOI lookup failure; target DOI mapping was verified |
| BART | `W2251939518` | Shared citing-paper DOI lookup failure; target DOI mapping was verified |
| BART | `W2418388682` | Shared citing-paper DOI lookup failure; target DOI mapping was verified |

Thus seven failures share a citing-paper problem, but resolving BART alone cannot guarantee seven contexts. Three target records in the failed cohort have no DOI. Current OpenAlex metadata supplies their MAG identifiers; it supplies no arXiv/PMID/PMCID in those inspected records. No alternative identifier is guessed from their titles or publisher PDFs.

## BART live investigation

OpenAlex `W2982399380` identifies the ACL publication DOI as `10.18653/v1/2020.acl-main.703`. Its repository locations explicitly include `pmh:oai:arXiv.org:1910.13461`, arxiv.org URLs and the DOI alias `10.48550/arxiv.1910.13461`. These are copies associated by OpenAlex with the requested work, not a separate title search.

The controlled authenticated run began November 14, 2026 at **10:52:51 a.m. EST (15:52:51 UTC)**. Attempts were spaced by at least five seconds through the existing service scheduler, with a stop on the second HTTP 429. It prioritized the seven original BART pairs before the rest of the unchanged original 28-pair list.

| Lookup | Actual HTTP result |
| --- | --- |
| BART primary ACL DOI | 404 |
| `ARXIV:1910.13461` | 200; exact returned identity verified |
| Target `MAG:131533222` | 429, then 200; exact returned identity verified |
| BART outgoing references | 429; controlled run stopped |

**BART resolved live to Semantic Scholar `395de0bd3837fdf4b4b5e5f04835bcc69c279481`.** The first target resolved through MAG to `475354f10798f110d34792b6d88f31d6d5cb099e`. The original OpenAlex IDs and primary DOI remain intact in `PaperMapping`. Both identities passed the normal implementation's external-ID checks. The successful mappings are cached once for reuse by other selected edges.

The attempt took approximately **20.469 seconds**, including scheduling and one recovered retry. It made **five actual Semantic Scholar calls**: two HTTP 200, one HTTP 404, and two HTTP 429. All carried the configured key. Two OpenAlex calls were made during retrieval; four earlier public OpenAlex metadata calls investigated BART and the three DOI-less targets. No full text was downloaded. No further live requests were made after the stop condition.

## Coverage comparison and limits

| Measure | Original baseline | Milestone 4 controlled run |
| --- | ---: | --- |
| Cohort | 28 pairs | Same 28 selected; first pair attempted, 27 not tested after stop |
| Both identities verified | 18 pairs | Both verified for first attempted pair, previously unresolved |
| Genuine citation contexts | 14 pairs / 28 passages | No new passages verified; reference retrieval blocked |
| Successful classification | 14 pairs | None in this live run; no context supplied to the model |
| Context coverage | 50% | Updated 28-pair coverage cannot be measured |

**Verified passage improvement is zero; updated overall coverage is unknown.** Do not combine historical successes with new mapping results and label that a fresh live benchmark. Likewise, do not interpret a blocked reference call as `no_context` or an absent relationship. All seven BART pairs can reuse the now-resolved citing identity, but outgoing reference coverage is unverified in this run.

Remaining historical failures were eight unresolved mappings, four missing-context relationships, and two exhausted rate limits. This run confirms a fix for the BART citing identity and the first target mapping only. It does not re-evaluate the other seven baseline unresolved pairs, four missing-context pairs, or two prior rate failures. The evidence JSON preserves all original pair IDs and explicitly labels the untested rows. Synthetic tests establish implementation correctness, not live coverage gains.

## Verification and Git state

Commands from the repository root, with `.tools/uv` on PATH and workspace-local uv cache/Python paths:

```powershell
npm run lint
npm run typecheck
npm run test
npm run build
.tools/uv/uv.exe run --project apps/api pytest apps/api/tests -q
```

The final backend suite passes **429 tests**; the frontend suite passes **6 tests**. Ruff lint/format, ESLint, TypeScript and production build pass. The existing Starlette/httpx deprecation warning remains. The full root test run initially passed 428 backend tests; the final additional bounded-alternative-retry case passes in the final 429-test suite. Existing inference, offline examples, graph endpoints and unavailable-state tests remain included.

The controlled live command was `.tools/uv/uv.exe run --project apps/api python .cache/m4/verify.py`; this local investigation script and raw output are ignored. The sanitized metadata and complete selected cohort are retained in the evidence JSON for review. Keys were never written to source, evidence, logs or API responses, and `.env` was not modified.

Work remains uncommitted on `dev-ml`. No merge, rebase, branch switch, push or commit occurred. The model artifact SHA-256 remains `cb798df60c932deeeff4c15f8760c2de9fc27be07e6be95c6f3e403f02893d96`.

## Recommendation

Keep this exact-identifier improvement: it repairs a demonstrated shared BART mapping issue with no model or transport redesign. Avoid further speculative Semantic Scholar work while throttling blocks measurable coverage. Proceed next with a **small OpenAlex TEI feasibility experiment** targeting demonstrated missing contexts and the original unresolved cohort, validating bibliography identifiers and source attribution before building a fallback service. No full-text extraction is implemented in this milestone, and BART passage recovery remains unverified.
