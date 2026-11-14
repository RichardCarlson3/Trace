# Milestone 7 ? Gemini-assisted citation recovery experiment

## Result and decision

**No new verified citation passage was recovered from the four BioBERT targets.** One bounded PDF analysis returned four bibliography candidates: one had no body passage, and three supplied table material. Independent PDF text/layout and internal-link checks confirmed the table locations; none was eligible for SciCite. No classifier call was made. A production Gemini fallback is not justified by this experiment; proceed with the existing selected-edge frontend integration.

This was an isolated experiment. Production Semantic Scholar/OpenAlex services, endpoints, frontend, database, model and dependency lockfiles were not changed. Only the standalone experimental script and this report were added. Work remains uncommitted on `dev-ml`; no branch switch, merge, rebase, commit or push occurred.

## Configuration, model and request limits

The initial missing-key checkpoint was cleared when the user configured `GEMINI_API_KEY` locally. The user subsequently confirmed **verified free-tier-only use; do not upgrade**. No billing activation or upgrade was performed. Billing status was confirmed by the user, not independently queried through a billing API.

- Model requested and returned: **`gemini-3.5-flash-lite`**.
- Official Google GenAI Python SDK: **`google-genai==3.3.0`**, installed in an isolated uv environment.
- PDF verification libraries in the same isolated environment: PyMuPDF 2.1 and pypdf 7.1.0. Production dependencies were not modified.
- One token-count call and one generation call: **2 Gemini API operations**, below the six-call cap. No retries, Files API uploads, grounding, tools, model-generated intent labels or automatic function calls were used. PDF bytes were supplied inline in the generation request.
- JSON output used a Pydantic response schema, temperature 0 and maximum 8,192 output tokens. Large documents, responses, metadata and page renders remain ignored under `.cache/m7/`.
- The SDK receives the key from the process environment or ignored `apps/api/.env`. Keys were not printed, written into prompts, passed in command arguments or included in saved responses/reports.

Google's current documentation recommends the Google GenAI SDK and lists Gemini 3.5 Flash-Lite as a cost-efficient model supporting PDF input and structured output. Gemini 2.5 Flash-Lite was not selected because current documentation restricts access for new projects. [Official SDK](https://ai.google.dev/gemini-api/docs/libraries), [selected model](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite), [PDF input](https://ai.google.dev/gemini-api/docs/document-processing), [structured output](https://ai.google.dev/gemini-api/docs/structured-output).

## Authorized source and authoritative metadata

The BioBERT PDF was downloaded once through the authenticated official endpoint:

`https://content.openalex.org/works/W2911489562.pdf`

OpenAlex's cached metadata records CC BY. Attribution: Jinhyuk Lee et al., BioBERT, DOI `10.1093/bioinformatics/btz682`. No arbitrary publisher scrape or unverified copy was used.

- PDF size: **1,390,189 bytes**, **7 physical pages**.
- SHA-256: `1c127a4ec8163a002b0cecf5d18ee8915789d4dc4a83503d496d2dd741d99d45`.
- MD5: `0fb85ee4e9da7eb926e359ac867e767b` ? exactly matches the source-PDF MD5 embedded in the previously verified BioBERT TEI.
- The expected BioBERT DOI is present in extracted PDF text.
- PyMuPDF and pypdf extracted page text independently. Relevant pages were rendered and visually inspected, especially physical pages **4** (printed page 1237) and **7** (printed page 1240).

One OpenAlex batch retrieved current title, authors, publication year, DOI, IDs and locations for the four targets. Preparation therefore used **two new OpenAlex requests**: one PDF GET and one metadata batch. The source PDF and extracted page data are cached and reused. These preparation calls are separate from the two Gemini operations.

| Citing ID | Cited ID | Authoritative title / year | DOI |
| --- | --- | --- | --- |
| `W2911489562` | `W2047782770` | Introduction to the bio-entity recognition task at JNLPBA / 2004 | `10.3115/1567594.1567610` |
| `W2911489562` | `W2052217781` | The EU-ADR corpus: Annotated drugs, diseases, targets, and their relationships / 2012 | `10.1016/j.jbi.2012.04.004` |
| `W2911489562` | `W2071879021` | The SPECIES and ORGANISMS Resources for Fast and Accurate Identification of Taxonomic Names in Text / 2013 | `10.1371/journal.pone.0065390` |
| `W2911489562` | `W2136437513` | Extraction of relations between genes and diseases from text and large-scale data analysis: implications for translational research / 2015 | `10.1186/s12859-015-0472-9` |

Full authoritative author lists were supplied to Gemini. They were treated as target metadata, not proof that every author name appears in the citing document's abbreviated bibliography.

## Gemini proposals and independent verification

The prompt requested verbatim quotations, source-present bibliographic fields, a citation marker connected to the reference, section/physical PDF page, uncertainty and not-found outcomes. It explicitly distinguished body text from tables/captions/reference lists, prohibited reconstructed quotations and requested no final intent classification. No LLM confidence score was used.

| Target | Gemini proposal | Independently observed source | Final passage outcome |
| --- | --- | --- | --- |
| `W2047782770` | Kim et al. (2004), bibliography on page 7; `passage_found=false` | Parenthetical marker in the JNLPBA row of Table 3 on page 4; abbreviated Kim reference on page 7 | **Not found**: no body passage supplied |
| `W2136437513` | Bravo et al. (2015), Table 4 heading and GAD row | Table 4 on page 4; reference on page 7. Whitespace-normalized quoted text was located | **Rejected**: table material, not an eligible citation sentence |
| `W2071879021` | Pafilis et al. (2013), Table 3 heading plus Species-800 row | Components are in Table 3 on page 4. Model concatenated the header and a later row; strict contiguous quote matching failed | **Rejected**: table composite; verbatim contiguous quote not established |
| `W2052217781` | Van Mulligen et al. (2012), Table 4 heading plus EU-ADR row | Components are in Table 4 on page 4. Model skipped intervening row content; strict contiguous quote matching failed | **Rejected**: table composite; verbatim contiguous quote not established |

All four apparent bibliography entries exist on PDF page 7. Their titles and publication years agree with the target metadata after conservative bibliographic punctuation/case normalization. The author abbreviations are compatible with the corresponding metadata, but the references do not print the full author lists returned by Gemini. None prints the target DOI as part of the supplied bibliography quotation. Bibliographic resemblance was not silently promoted to an exact-identifier match.

### Verification methods

1. **Source integrity:** matched the PDF's MD5 to the TEI source-PDF MD5 and confirmed the expected document DOI.
2. **Quote existence:** compared whitespace-normalized quotations against independently extracted page text, without repairing wording, punctuation, spelling or line-wrap hyphenation. Some bibliography quotations were dehyphenated by the model and therefore did not pass this strict automated check; visual review distinguished real reference content from exact verbatim quotation claims.
3. **Marker linkage:** inspected the PDF's actual internal link annotations. All four page-4 table markers point to physical page 7. Their destination coordinates, interpreted in PDF coordinates, lead to the corresponding Kim, Pafilis, Bravo and Van Mulligen reference paragraphs. Source rectangles/destination points and local destination text excerpts are saved in `.cache/m7/pdf_marker_links.json`.
4. **Layout verification:** rendered and inspected pages 4 and 7. The candidate markers occur in dataset tables, not regular body sentences. The table layout explains GROBID's misleading `<s>` fragments; Gemini did not reveal missing body evidence.
5. **Metadata checks:** compared source titles/years with the authoritative target records and reviewed authors/identifiers. The source lacks the printed exact target identifiers needed for automatic identity promotion under the existing strict pipeline.
6. **Classification gate:** **zero verified body passages ? zero `InferenceService` calls**. No citation intent or confidence was invented, and no Gemini-generated classification was accepted.

Outcome counts for passage recovery are **0 verified**, **0 plausible body passages pending review**, **3 rejected**, **1 not found**. Four bibliography associations remain plausible as bibliographic matches, rather than new verified passage recoveries. These are different metrics.

## Model limitations observed

- The model identified the table setting, but still returned `found=true` / `passage_found=true` for three table candidates despite the body-only instructions. A boolean success field alone would have produced false recoveries.
- It supplied expanded author lists not actually printed in the abbreviated source references. Those names are compatible with target metadata, but labeling them as source-present fields violates the evidence contract. This is unsupported source attribution, not proof that the author identities themselves are false.
- Two table quotations combine noncontiguous source components. Some reference text also repairs line-wrap hyphenation. Such output cannot automatically count as an exact original passage.
- `ambiguity="none"` appeared in all four records; it was not treated as verification.
- No wholly invented body narrative was accepted or observed. The failure was primarily source type, quotation fidelity and evidence attribution, rather than discovering a genuine sentence that the deterministic parser missed.

The optional BART phase was skipped: BioBERT did not yield a verified recovery, and additional requests would not be warranted by this result. The already recovered BART `W1614298861` was not counted again as a Gemini discovery.

## Usage, latency and cost

The live request began **November 14, 2026 at 12:10:36 p.m. EST (17:10:36 UTC)**. The generation request took **8.271 seconds**; token-count/preparation latency is not included in that number.

| Measure | Actual recorded result |
| --- | ---: |
| Gemini API operations | 2: one count, one generation |
| Preflight token count | 5,092 |
| Generation prompt tokens | 4,812: 3,640 image + 1,172 text |
| Output candidate tokens | 1,613 |
| Total generation tokens | 6,425 |
| Thinking/tool token counts | Not reported / no tools requested |
| Output cap | 8,192 tokens |
| Provider errors | 0 |
| Paid-equivalent estimate | **$0.0054761** |

The estimate uses the currently published standard rates of $0.30/million input tokens and $2.50/million output tokens for the selected model. The preflight maximum-output reservation was $0.0220076; that is a conservative software reservation, not an actual bill. The user confirmed free-tier-only use, and no paid upgrade occurred. Billing statements were not queried, so actual billed charges are not independently reported. [Official pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite).

The count-token API and generation usage metadata returned different input counts; both are retained rather than substituted. The cost estimate uses generation usage. The ignored ledger records **2 of at most 6** operations. No additional Gemini calls were made after the unsuccessful result.

## Comparison on the same four BioBERT relationships

| Metric | Semantic Scholar | OpenAlex TEI | Gemini experiment |
| --- | --- | --- | --- |
| Exact target relationships tested | 4, historical live run | 4, M6 offline replay using real downloaded XML | 4, new live PDF analysis |
| Genuine eligible passages recovered | 0 | 0 | 0 |
| Independently verified passage matches | 0 | 0 | 0 |
| Unverified candidates | Not separately measured | Four plausible bibliography/table associations excluded | Four bibliography candidates; three table passages rejected, one body not found |
| Provider errors | Two recovered HTTP 429s across the four requests' incremental call accounting | No live calls in replay | 0 |
| Latency | Historical per-pair totals: 13.937, 9.172, 4.531, 4.609 seconds | BioBERT metadata+XML cold retrieval was 0.629s in M5; no separate four-pair replay timing claimed | 8.271s generation, four targets jointly |
| API usage / cost | 7 incremental historical requests for these four pairs, with shared warm resources; no cost estimate | Cached M6 replay; one real BioBERT download in M5 plus metadata | 2 operations; 6,425 generation tokens; ~$0.00548 paid-equivalent, user-confirmed free tier |

These measurements are not a controlled latency benchmark: providers ran at different times with different cache states and request shapes. Historical overall Semantic Scholar coverage remains **14/28**. The separate eleven-pair TEI result remains **1/11**. No aggregate coverage improvement is claimed.

## Script, local artifacts and checks

Added `apps/api/scripts/gemini_citation_experiment.py`; no production service imports it. It requires explicit `--invoke` and confirmed tier, accepts a paid cap only when explicitly authorized, disables SDK retries/tools, reserves estimated cost before generation and enforces a persisted six-operation ledger. It submits one document with four target records, stores structured responses locally, and offers an offline `--audit` mode. The audit is conservative triage, not a general automatic verifier: candidates never become `verified` automatically, and any future positive candidate requires independent marker/layout/identity review before a separate existing-classifier call.

Key local ignored files:

- `.cache/m7/biobert.pdf`, `targets.json`, `pages.json`, page renders: original source and authoritative metadata.
- `proposals.json`: exact four-record Gemini response, including bibliography quotations, source fields and explanations.
- `gemini_run.json`: model/SDK, returned usage, latency and estimated maximum.
- `audit.json`, `pdf_marker_links.json`: automated triage and independent PDF link evidence.
- `ledger.json`: call count and reserved estimate.

Preparation commands used ignored `.cache/m7/prepare.py` and `inspect_pdf.py`. The following generation command was run **only after the user's free-tier confirmation**:

```powershell
uv run --project apps/api --with google-genai==3.3.0 --with pymupdf==2.1 --with pypdf==7.1.0 python apps/api/scripts/gemini_citation_experiment.py --invoke --confirmed-tier free
```

Offline audit:

```powershell
uv run --offline --project apps/api --with google-genai==3.3.0 --with pymupdf==2.1 --with pypdf==7.1.0 python apps/api/scripts/gemini_citation_experiment.py --audit .cache/m7/proposals.json
```

Ruff formatting/lint passed for the experimental script. A synthetic fabricated quotation was rejected by the offline verification guard. The production regression suite was not rerun for this isolated script/report change; the last M6 results remain historical: 473 backend tests and 6 frontend tests passed, with lint/type/build checks passing. No new production behavior or scientific classifier prediction is claimed here.

## Recommendation

**Proceed with frontend integration of the existing two-provider backend. Do not add an automatic Gemini fallback based on this result.** The original document appears to cite these targets in tables rather than eligible body sentences. Gemini cannot supply evidence that is absent under the chosen definition, and relaxing verification to accept table rows or bibliographic similarity would change the task rather than improve verified coverage.

A later research-only candidate-assistance tool might help prioritize human review on a corpus where actual body citations exist but deterministic bibliography linkage is missing. It would still require exact source anchoring, reference-link verification, contradiction checks and a hard refusal to classify table/composite/unverifiable text. This experiment supplies no demonstrated benefit justifying that production scope now.
