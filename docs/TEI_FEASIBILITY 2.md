# Milestone 5 ? OpenAlex citation extraction feasibility

## Result

**Real extraction works for a narrow exact-identifier subset.** Two authenticated OpenAlex TEI downloads succeeded. Of the eleven prioritized previously unsuccessful relationships, one BART relationship yielded one verified body sentence, which the existing SciCite service classified. None of the four BioBERT relationships was recovered under the strict identity rules.

The initial missing-key blocker was cleared by the user configuring the key locally. A metadata request and both content requests then returned HTTP 200. No credentials were printed, modified by the agent, or included in the evidence. No Semantic Scholar requests were made.

[Machine-readable evidence](reports/tei_feasibility.json) includes source URLs, XML hashes, bibliography XML, in-text marker XML, exact extracted text, section and model output. Full documents remain ignored under `.cache/m5/`. This is a feasibility experiment, not a new API fallback or a representative coverage benchmark. The historical Semantic Scholar baseline remains 14/28; it was not rerun.

## Download and source verification

The live download ran November 14, 2026, **11:06:46?11:06:47 a.m. EST** (16:06:46?16:06:47 UTC). Two documents were fetched once and cached by OpenAlex work ID. There were no redirects or retries. A single additional metadata batch covered all eleven target works.

| Document | XML bytes | Metadata + XML retrieval | Source identity |
| --- | ---: | ---: | --- |
| BioBERT `W2911489562` | 81,723 | 0.629 seconds | Authenticated work-specific endpoint plus matching header DOI `10.1093/bioinformatics/btz682` |
| BART `W2982399380` | 92,627 | 0.282 seconds | Authenticated work-specific endpoint; title/authors corroborate, but the header contains no DOI/arXiv identifier |

BART source identity therefore relies on OpenAlex's authoritative work-to-content binding, rather than independent agreement with a header identifier. This trust boundary is explicit in the evidence; the title was not used to select a candidate paper or bibliography entry. The cited target is independently matched by its exact arXiv ID.

Source endpoints:

- `https://content.openalex.org/works/W2911489562.grobid-xml`
- `https://content.openalex.org/works/W2982399380.grobid-xml`

Both current metadata records report `best_oa_location.license=cc-by`. The cached XML SHA-256 values are:

- BioBERT: `afb7276ffdda9b1dec00614fa1e02100f81d6fa0f048a8ca3e8ddfa27742d16f`
- BART: `8017bc8c16466aedbd7544a117b8d7b06f9cecbf9da985ff2d9c0e7e91848650`

OpenAlex documents keyed, metered XML downloads through `content_urls.grobid_xml`; the authenticated bearer header worked in this experiment. HTTPX handled the content decoding. Public metadata access alone had not established download access. [Official content documentation](https://help.openalex.org/access/fulltext/), [authentication](https://help.openalex.org/api/authentication/).

## Verified recovery and classifier output

**BART `W2982399380` ? Efficient Estimation of Word Representations in Vector Space `W1614298861`.**

1. Current target OpenAlex metadata explicitly links arXiv `1301.3781`; its DOI is `10.48550/arxiv.1301.3781`.
2. BART bibliography entry `b17` contains `<idno type="arXiv">arXiv:1301.3781</idno>`. No title matching was required.
3. An Introduction body sentence contains `<ref type="bibr" target="#b17">`; the marker targets exactly that entry.
4. The original decoded sentence text, including adjacent citation formatting, is preserved below. It is not an abstract, bibliography entry, invented reconstruction or table row.
5. The existing `InferenceService` loaded the saved pipeline and classified that exact text.

> Self-supervised methods have achieved remarkable success in a wide range of NLP tasks (Mikolov et al., 2013;Peters et al., 2018;Devlin et al., 2019;Joshi et al., 2019;Yang et al., 2019;Liu et al., 2019).

Attribution: Mike Lewis et al., BART, [publication](https://aclanthology.org/2020.acl-main.703/), source XML served by OpenAlex, CC BY according to current OpenAlex metadata. This is a multi-citation sentence; the selected Mikolov marker is retained rather than rewriting it into a single-citation passage.

| Intent | Confidence | Model version |
| --- | ---: | --- |
| `background` | 0.8843842684202584 | `scicite-tfidf-logreg-v1` |

The prediction is consistent with a manual reading of this introductory sentence. It is an uncalibrated model score, not a measured accuracy result or independent ground-truth label. No retraining or label changes occurred. Offline parsing plus lazy model loading/inference took approximately **0.553 seconds** in the first inspection.

## Outcomes for the eleven targets

| Citing work | Target | Exact bibliography match | Verified sentence / classification | Outcome |
| --- | --- | --- | --- | --- |
| BioBERT | `W2047782770` | No | No | Explicit ACL pointer exists, but current target metadata does not provide the same URL/ID; not accepted by title |
| BioBERT | `W2052217781` | No | No | Apparent bibliography entry lacks exact target identifiers |
| BioBERT | `W2071879021` | No | No | Apparent bibliography entry lacks exact target identifiers |
| BioBERT | `W2136437513` | No | No | Apparent bibliography entry lacks exact target identifiers |
| BART | `W131533222` | No | No | No exact linked target identifier; target DOI absent |
| BART | `W1544827683` | No | No | Bibliography lacks target arXiv/DOI identifier |
| BART | `W1599016936` | No | No | No exact linked target identifier; target DOI absent |
| BART | `W1614298861` | Yes, `b17`, arXiv `1301.3781` | Yes / `background` | Recovered |
| BART | `W2130158090` | No | No | No exact target DOI/URL in bibliography |
| BART | `W2251939518` | No | No | No exact target DOI/URL in bibliography |
| BART | `W2418388682` | No | No | No exact target DOI/arXiv identifier in bibliography |

All four BioBERT targets were previously Semantic Scholar `no_context` cases. Manual XML inspection found plausible entries `b8`, `b30`, `b19`, `b2`, respectively, but these were not verified target identities. The apparent in-text markers occur in flattened dataset tables. GROBID placed these fragments inside `<s>` nodes under a section labeled Discussion. Merely trusting `<s>` would incorrectly classify table contents as citation sentences. None was passed to the model.

The explicit BioBERT ACL pointer was checked against the official [ACL W04-1213 record](https://aclanthology.org/W04-1213/). That page supplies an ACL identifier but no DOI tying it to the target's OpenAlex DOI. Similar titles were not treated as an exact identifier bridge. This was one extra external bibliographic-page lookup, not another OpenAlex download.

BioBERT has 38 bibliography entries, only four with explicit `idno` elements; BART has 35, of which 23 have `idno`. Some additional entries contain URL pointers. Counts of `idno` elements alone are not counts of all matchable references. The ten failed target matches remain unverified; absence of identifiers does not disprove the citation relationships.

## Usage and caching

- **2** documents downloaded successfully.
- **1/11** selected previously unsuccessful relationships recovered: **0/4 BioBERT**, **1/7 BART**.
- **1** exact target bibliography match, **1** verified body sentence, **1** model prediction.
- **5 OpenAlex API requests**: two citing-work metadata requests, two content GETs, one target metadata batch. All returned HTTP 200. No retries, redirects or provider errors occurred.
- One additional ACL bibliographic webpage was inspected. Documentation browsing is separate from API usage.
- Raw XML and metadata are cached locally; subsequent parser runs use no network. The positive timing is for a tiny two-document sample and does not establish typical provider latency or availability.

## Experiment artifacts and verification

Added only `apps/api/scripts/inspect_tei_feasibility.py`, this report, and `docs/reports/tei_feasibility.json` for Milestone 5. Milestone 4 work remains preserved. No app route, response schema, model, Semantic Scholar implementation, frontend or database was changed.

The standalone script reads cached inputs only. It checks download hashes and source metadata IDs, rejects declarations/entities and oversized documents, checks exact bibliography identifiers/explicit metadata URLs, follows bibliography markers only in the body, preserves XML/section provenance, and calls the existing inference service. It does not implement downloading, orchestration or a reusable automatic fallback. Its sentence punctuation guard is deliberately conservative and **is not a general table detector**; manual review of accepted output is part of this experiment.

Reproduce locally from the repository root using the cached documents:

```powershell
uv run --project apps/api python apps/api/scripts/inspect_tei_feasibility.py
npm run lint
npm run typecheck
npm run test
npm run build
```

The one-time research downloader is ignored at `.cache/m5/download.py`. Inputs live at `.cache/m5/{work_id}.xml`, corresponding `.metadata.json` files, `targets.json` and `downloads.json`; the latter preserves capture time, source URLs, sizes and hashes. A fresh clone needs explicit authenticated downloads before running the inspector. Model artifact SHA-256 remains `cb798df60c932deeeff4c15f8760c2de9fc27be07e6be95c6f3e403f02893d96`.

Current regression results: **429 backend tests and 6 frontend tests passed**. ESLint, Ruff lint/format, TypeScript and production build passed. One existing Starlette/httpx deprecation warning remains. The standalone inspector was executed against the real cached XML; its accepted sentence was manually checked against the marker and bibliography XML. These checks establish this example, not production parser coverage.

## Concrete next milestone

A narrow automatic fallback is practical for exact-ID cases, but this experiment does **not** support expecting recovery of all missing passages. Most selected BioBERT failures would remain unavailable under the demonstrated method. Proceed with a bounded backend-only implementation rather than title guessing or automatic reference consolidation:

1. On an explicit selected-edge classification request, try Semantic Scholar through its existing service. For eligible unavailable/missing-context results, attempt TEI only when an OpenAlex key and structured content are available. Preserve the original provider outcome if fallback also fails; do not turn unavailable evidence into a negative citation relationship.
2. Cache metadata, XML and parsed bibliography/marker indexes per citing OpenAlex ID. Coalesce concurrent downloads and reuse one document across edges. Suggested pilot limits: 16 documents, 10 MB/document, 30-second attempt timeout, 24-hour positive cache and five-minute unavailable cache; tune after broader measurement. Stop on access/quota errors rather than retrying repeatedly.
3. Use a hardened XML parser with entity/network resolution disabled. Verify the provider work-to-content binding, check header identifiers for contradictions, and document when a header identifier is absent. Support known namespace/layout variants. Match cited identities only through exact IDs or explicitly verified URLs. Reject ambiguous bibliography entries and unlinked markers.
4. Extract bounded body sentences/paragraphs while excluding abstracts, bibliography, figures and table-like fragments. Add regression fixtures for the demonstrated BioBERT table artifacts. Keep exact original text, bibliography ID, marker, section path, capture time and document hash. Do not repair OCR or invent sentence text.
5. Extend the existing citation evidence contracts deliberately: represent `openalex_tei` as its own source and add document-level provenance without labeling it Semantic Scholar. Coordinate source enums/optional evidence fields with API consumers. Do not add database persistence or frontend features as part of this step.
6. Reuse `InferenceService.classify` unchanged. Add offline tests for exact/mismatched/ambiguous IDs, absent header IDs, sentence/table separation, entity rejection, download limits, cache/coalescing and provider failures, plus both existing citation APIs. Re-evaluate the same eleven pairs before making wider coverage claims.

Estimate: roughly **one focused developer day** for this restricted backend pilot including contract changes and tests; broader citation consolidation, fuzzy matching, PDF extraction and universal table handling are outside scope. No full fallback was implemented here.

Stay on `dev-ml`; all changes remain uncommitted. No merge, push, rebase or branch switch occurred.
