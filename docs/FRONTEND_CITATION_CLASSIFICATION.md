# Frontend citation classification: minimal integration fix

The previous frontend never called `POST /api/v1/citation-contexts/classify`.
Clicking an edge selected its ID and opened the existing citation panel, which
read null `intent`, `confidence`, and context fields from graph metadata. The
current source called this state “Unclassified”; the literal “No classification”
was absent. Direction was already correct: citing/source -> cited/target. The
backend base URL, `/api/v1` prefix, and POST CORS support were also correct.
There was no evidence of a model or backend retrieval defect.

After scope refinement, production changes are limited to three existing files:

- `apps/web/src/lib/api.ts`: add a typed classification POST with `mode: "auto"`,
  a 120-second deadline, relationship-ID validation, and distinct timeout errors.
- `apps/web/src/components/papers/citation-details.tsx`: request evidence when
  the existing selected-edge popup opens. Keep its markup/classes and show loading,
  API errors, or the returned passage and its nested classification. Display the
  first classified passage (or first unclassified passage), with its index when
  multiple passages exist. Show intent, confidence percentage, original full text,
  evidence source, retrieval origin, source link, and model version.
- `apps/web/src/components/layout/research-workspace.tsx`: one added prop passes
  the existing preview flag, preventing API requests for sample graph edges.

One new focused test file, `apps/web/src/__tests__/citation-classification.test.tsx`,
contains nine offline regression tests. This report is the only new documentation.
The earlier separate hook, frontend cache, shared-type additions, CSS changes,
and popup-position changes were removed from the final diff. A local ignored
backup preserves those earlier edits under
`.cache/frontend-classification-before-scope-reduction/`. Prior Gemini work was
preserved. Backend code, model artifacts, animations, styles, graph layout,
project configuration, and unrelated tests are unchanged.

Only selected relationships are classified. Repeated clicks on the active edge
and React Strict Mode's effect probe do not issue duplicate POSTs. Changing edges
or closing the panel cancels transport and ignores late responses. Empty evidence
stays unclassified with no invented intent or confidence; API errors have a
separate message. There are no automatic retries or new cache layers. Reopening
an edge reuses the existing backend retrieval cache; its origin is displayed.

Verification passed: frontend lint, TypeScript, production build, 34 frontend
and 473 backend tests, plus backend lint/format checks. The backend tests emit
one existing Starlette TestClient deprecation warning. The reduced final diff
was reviewed with `git diff --stat` and `git diff`.

The workspace regression uses the genuine recorded BART -> Word2Vec response
from `docs/reports/openalex_fallback_live.json`: Background, 88.44%, the exact
original sentence, and OpenAlex TEI provenance. It exercises the actual workspace,
API client, and panel, with mocked fetch responses and a mocked graph canvas.
Tests also cover unavailable evidence, Semantic Scholar provenance, a ten-second
retrieval, timeouts, failures, stale responses, cancellation, duplicate requests,
backend-cache labels, mismatched relationship IDs, and preview suppression.

Live-browser rendering and React Flow hit testing were not verified in this
session: browser and native computer-use inventory failed because the native
pipe was unavailable. No additional provider requests were made. Work remains
uncommitted on `dev-ml`.

For manual verification, start the existing API and web development servers with
`npm run dev` from the repository root (with uv available). Open
`http://localhost:3000`, enter the workspace, and search for `W2982399380`. Select
BART's directed edge to “Efficient Estimation of Word Representations in Vector
Space” (`W1614298861`); use BART's “Show references” button if necessary. Wait for
the popup result. The known TEI passage should show Background and approximately
88.44%. A newly verified Semantic Scholar passage may have a different prediction.
