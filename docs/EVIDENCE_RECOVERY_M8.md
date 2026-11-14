# Milestone 8 — Evidence recovery feasibility and Gemini comparison

## Decision

Missing citation evidence had three distinct causes, and only one of them can be fixed:

1. **No legitimate full text.** For example, the 2005 ACM SIGKDD Explorations papers. Unrecoverable without a licensed copy.
2. **Full text available, but the cited paper's bibliography entry has no exact identifier.** This is the dominant cause.
3. **The cited paper appears only in tables or captions.** Correctly not recoverable as a citation sentence.

We implemented **deterministic closed-set reference-list alignment** inside the existing OpenAlex TEI fallback (see [OPENALEX_FALLBACK.md](OPENALEX_FALLBACK.md)). Gemini recovered no verified passage that the deterministic method missed, so no Gemini integration was built. No new provider or dependency was added.

## Measured improvement

All four documents we could legitimately access were replayed offline through the production `OpenAlexTEIService`, using recorded live OpenAlex metadata and GROBID TEI. The same code was run with alignment disabled ("before") and enabled ("after").

| Citing document | OpenAlex edges | Before: edges / passages | After: edges / passages |
| --- | ---: | ---: | ---: |
| BART `W2982399380` | 40 | 19 / 32 | 28 / 43 |
| BioBERT `W2911489562` | 46 | 3 / 3 | 18 / 32 |
| Link-mining survey `W2323610191` | 98 | 1 / 1 | 25 / 29 |
| Link-mining survey `W2332982894` | 98 | 1 / 1 | 20 / 24 |
| **Total** (5 targets no longer served by OpenAlex) | 282 | **24 / 37** | **91 / 128** |

- **Net gain: 67 additional relationships with a verified body passage, and 91 additional passages.** The two surveys are near-duplicate texts by the same authors, so 20 of the survey gains repeat each other. Counting only unique source text, the gain is 47 relationships.
- **Identity precision was audited manually.** We compared every aligned entry with its OpenAlex record (title, authors, venue, year) and found no wrong identity. One survey entry reproduces the authors' own citation error, crediting "Lin et al. 2007" for a time-series claim. We report the document as written.
- **Correct refusals:**
  - 19 edges where OpenAlex lists duplicate records for one paper (BERT, GLUE, Pointer-Generator, several outlier papers).
  - Chandola's "Anomaly detection: a survey", which shares its exact title with an unrelated 2021 record in the same reference list.
  - Title collisions with different authors (e.g. "Data Mining: Concepts and Techniques").
  - A misspelled first author ("Aggarwal" for Agrawal).
- **Live check** against real OpenAlex on 2026-11-14 (production service, no Semantic Scholar calls). Cold retrieval took 0.4–0.7 s with 3–4 OpenAlex requests; warm retrieval took 0.07–0.2 s.

## Per-relationship comparison

FT = legitimate full text available. Gemini rows used the original PDFs. All "verified" judgments are independent of Gemini's own claims.

| Relationship | FT | Bibliography entry | Cited identity verified | Deterministic passage | Gemini passage | Extra from Gemini | Failure reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BART → Word2Vec `W1614298861` (control) | Yes | b17 | Yes, exact arXiv | Yes (unchanged, `background` 0.884) | Not tested | — | — |
| BART → Teaching Machines `W1544827683` | Yes | b10 | Yes, aligned (Hermann, 2015) | **Yes (new)**: "CNN/DM (Hermann et al., 2015), a news summarization dataset." | Same sentence plus the next sentence appended | 0 | — |
| BART → MRPC `W131533222` | Yes | b4 | Yes, aligned via printed author segment | **Yes (new)** | Yes, same sentence | 0 | — |
| BART → Pointer-Generator `W2606974598` | Yes | Yes (See et al.) | No: two OpenAlex records share the title | No | Table row (labelled as table) | 0 | `tei_ambiguous_reference_list`; only a table occurrence |
| Survey `W2323610191` → Anomalous link discovery `W2140584250` | Yes | b68 | Yes, aligned (Rattigan, 2005) | **Yes (new, 2 passages)** | Rejected: text not contiguous in the PDF; marker absent | 0 | — |
| Survey `W2332982894` → `W2140584250` | Yes | b68 | Yes, aligned | **Yes (new, 2 passages)** | Not tested | — | — |
| Survey → CLIQUE `W1977496278` (printed "Aggarwal") | Yes | [4], misspelled | No (first author differs) | No | **False positive**: claimed body passage lacks the marker | 0 | No body citation exists |
| Survey → Perner `W208128215` (generic title) | Yes | Han & Kamber, a different work | No (correct) | No | Said `different_work` (correct); its passage lacked the marker | 0 | Different work |
| BioBERT → JNLPBA `W2047782770` | Yes | b8 | Yes, aligned | No | Table (M7) | 0 | Table-only citation |
| `W2140584250` → `W1534255704` (and `W1571571249`, `W1577789831`) | No | — | — | No | Not tested | — | Closed; Semantic Scholar withholds references |
| Link mining `W2017102965` → `W2140584250` | No | — | — | No | Not tested | — | Closed |

## Gemini comparison

- **Setup:** model `gemini-3.5-flash-lite`, SDK `google-genai==3.3.0`, free tier as previously confirmed. Two generation calls (one per PDF), with the ledger capped at 4. Temperature 0, structured output, no tools and no SDK retries.
- **Usage:**

  | Call | Prompt tokens | Output tokens | Time |
  | --- | ---: | ---: | ---: |
  | BART | 5,838 | 814 | 4.8 s |
  | Survey | 9,830 | 877 | 76.4 s |

  Paid-equivalent cost was about **$0.0089** at the published rates; actual use was free tier.
- **Verification:** each claim was checked against the PDF text extracted with PyMuPDF (whitespace and line-wrap normalization only), against the production TEI body-sentence index, and against the TEI marker → bibliography link.
- **Results on the 6 relationships:**
  - 1 fully valid (MRPC), which deterministic alignment also recovers.
  - 1 correct sentence with the following sentence appended.
  - 1 honestly labelled table row.
  - 3 claimed "body" passages that do not contain the claimed marker; one of them is not contiguous text in the PDF.
- **Identity judgments were better than passage extraction:**
  - Gemini correctly called the generic-title collision a different work.
  - It correctly treated the misspelled "Aggarwal" entry as the same work.
  - It could not detect duplicate OpenAlex records.
  - None of these judgments was used as evidence.
- **Conclusion:** Gemini recovered no additional verified evidence, so it is not justified as a fallback. Its identity judgments might later help prioritize manual review, but they are not verification.

## ACM 2005 papers

`W2140584250` and `W2017102965` are `oa_status: closed` with `any_repository_has_fulltext: false` and no OpenAlex PDF or GROBID content. Their only non-publisher locations are a CiteSeerX summary page and a Wayback Machine snapshot of a PDF on a third-party university page. Neither is an open-access location OpenAlex recognizes, so neither was used.

A Semantic Scholar `openAccessPdf` check was attempted once and returned HTTP 429. As established earlier, Semantic Scholar returns `data: null` for `W2140584250`'s reference list. **These relationships remain unrecoverable.**

**`W2140584250` as the cited paper is now recoverable** from two open-access 2016 surveys that discuss it in body text.

## Changes

- `apps/api/app/services/openalex_tei.py`:
  - Bibliography alignment keys and `bibliography_agrees`.
  - Closed-set `_align`, plus a cached `_titles` lookup of the referenced works.
  - `publication_year,authorships` added to the metadata selection.
  - Two narrow sentence rejections: a leading digit, and `Note:`.
- `apps/api/tests/test_openalex_tei.py`: 19 tests. They use recorded documents and metadata, and label any altered or synthetic inputs.
- `apps/api/tests/fixtures/tei/alignment_metadata.json`: recorded OpenAlex years and first two authors for the 11 fixture targets.
- `docs/OPENALEX_FALLBACK.md`: alignment and filter rules.

No API schema, frontend file, Semantic Scholar behavior, rate limit or classifier changed. Experiment scripts and raw responses stay in the session scratch area and are not committed.

## Tests

- Backend suite: **526 passed**. Ruff lint and format are clean.
- On the `HEAD` version of `openalex_tei.py`, 13 of the new tests fail. The 8 rejection tests pass on both versions, which shows every previously refused case is still refused.
- The BART → Word2Vec control and its classifier score (0.8843842684202584) are unchanged.
- Frontend checks were not run, because another agent is editing that code.

## Limitations

- Alignment depends on OpenAlex's `referenced_works` being correct. A wrongly linked edge whose title, first author and year all coincide with a real entry would be accepted. We observed none, but the guard is the closed-set check, not proof.
- GROBID's marker → bibliography links are trusted, as before.
- The leading-digit rule rejects headings merged into sentences (one observed: "4.2 Tasks SQuAD (…)").
- 48 aligned entries had no eligible body sentence, mostly table or abstract citations.
- At most 3 passages per edge.
- Closed papers remain out of reach.

## Next step

Run a live sample of user-clicked edges and record the `fallback_reason` distribution. That will show how often `tei_bibliography_not_verified` and `openalex_tei_content_unavailable` occur in practice, and whether full-text coverage or identity is now the binding constraint.
