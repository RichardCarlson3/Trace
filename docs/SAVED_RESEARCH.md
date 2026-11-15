# Browser saved graphs and recent searches

This feature saves research in the current browser profile using `localStorage`. No authentication, database, API contract changes, or backend graph persistence endpoints are involved.

## Using it

1. Open a paper and choose **Save graph** in the top toolbar beside **Filters**, **Details**, and **Saved**.
2. Give the graph a name and save. Reopening and saving it again updates that snapshot.
3. After a refresh, open **Saved** and choose the saved graph. **Delete** removes an individual saved graph.
4. Focus or click the search field to see recent searches. The browser retains the latest 20 unique queries and shows up to eight matching the text you have typed, ignoring capitalization. Clear the field to see the newest queries. Choose one to run it again, or use **Clear history**. Arrow keys move through visible suggestions, Tab reaches the controls, and Escape closes the history. Moving focus outside the search area closes it too.

Snapshots restore loaded papers, citation branches (including hidden branches), selection, node positions, viewport and filters without fetching the graph again. New expansion and rerunning searches require the API. Sample preview graphs cannot be saved as research.

Keep using the same browser profile and website address, including the port. Clearing site data or ending a private browsing session can remove saves. There is no cross-device sync. Storage failures show an error and retain previous saves.

## Ownership and integration for Dev 1

Storage, validation, UI controls, CSS, controller logic and feature tests live in separate files. The controls now sit in the top toolbar with dropdown styles scoped to `saved-research.module.css`. The search bar retains its original placement and responsive styles. Global styles, shared API types and dependency manifests are unchanged.

Three existing frontend files have integration changes:

- `apps/web/src/components/layout/research-workspace.tsx`: uses `useSavedResearch`, records searches, resets the save session when switching papers, restores filters, passes the saved layout to the canvas, and renders `SavedResearchControls`.
- `apps/web/src/hooks/use-citation-graph.ts`: exposes `edgeGroups` and adds `restore(snapshot)` to load saved state while cancelling earlier requests. Existing graph expansion behavior is retained.
- `apps/web/src/components/graph/citation-canvas.tsx`: accepts an optional initial layout and a ref exposing `getLayout()`. Existing callers can omit both. Reopening preserves saved positions; Dev 1's overlap spacing resumes when the focus or visible graph changes, and drag behavior is retained. Changing focus leaves already spaced nodes in place.

`SavedResearchControls` is a separate toolbar component with a dropdown panel and styles scoped to `saved-research.module.css`. **Saved** remains available before opening a paper. `PaperSearch` owns the history suggestions, using the same library data and unchanged storage keys. Keep the integration changes together in review; conflicts remain possible if these three files change concurrently. No Dev 3 backend or ML files are modified.

The stored data format is version 1, under `trace.saved-graphs.v1` and `trace.recent-searches.v1`. Keep these keys and snapshot fields compatible when adjusting the UI.

## Search matching

Plain-text searches normalize capitalization and repeated whitespace. OpenAlex's default search performs stemming, including singular/plural matching. If a normal search returns zero results, the frontend makes at most one additional request to the same API with OpenAlex's documented fuzzy syntax: one character edit for alphabetic words of four or five characters, two for words of six or more characters. Both requests share the existing 35-second timeout and are cancelled when a newer search starts, a saved graph opens, or the workspace resets.

Close-match results are labeled explicitly and contain only paper records returned by the API. The typed query and its original spelling remain in browser history. Existing matches are not replaced by a fuzzy search; provider errors are not treated as empty results. No local dictionary, model, research corpus, generated titles or new dependencies are used.

DOIs, URLs, work IDs and explicit Boolean/quoted/operator searches retain their original syntax and do not get an automatic fuzzy retry. Fuzzy expansion is limited to 24 terms and a 300-character API query. It is best effort: typos outside the edit budget, queries that already match unrelated papers, irregular word forms and missing provider records may still need a revised search. Provider ranking determines which real titles appear; the app cannot guarantee the intended paper.

See [OpenAlex search documentation](https://help.openalex.org/api/searching/) for stemming and fuzzy-search syntax. Offline tests validate query construction, retry bounds, cancellation and presentation with synthetic responses; they do not emulate or establish the quality of OpenAlex's live search index.

## Verification

Run the repository lint, typecheck, test and build commands. The new `browser-library`, `saved-research-workspace` and `saved-research-canvas` tests use offline synthetic fixtures and cover persistence across mounts, update/delete, history replay/clearing, storage failure, hidden branches, stale requests and layout restoration.
