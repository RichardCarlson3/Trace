# Browser saved graphs and recent searches

This feature saves research in the current browser profile using `localStorage`. No authentication, database, API contract changes, or backend graph persistence endpoints are involved.

## Using it

1. Open a paper and choose **Save graph** in the top toolbar beside **Filters**, **Details**, and **Saved & recent**.
2. Give the graph a name and save. Reopening and saving it again updates that snapshot.
3. After a refresh, open **Saved & recent** and choose the saved graph.
4. Recent searches lists the latest 20 unique searches. Choose one to run it again, or use **Clear history**. **Delete** removes an individual saved graph.

Snapshots restore loaded papers, citation branches (including hidden branches), selection, node positions, viewport and filters without fetching the graph again. New expansion and rerunning searches require the API. Sample preview graphs cannot be saved as research.

Keep using the same browser profile and website address, including the port. Clearing site data or ending a private browsing session can remove saves. There is no cross-device sync. Storage failures show an error and retain previous saves.

## Ownership and integration for Dev 1

Storage, validation, UI controls, CSS, controller logic and feature tests live in separate files. The controls now sit in the top toolbar; responsive toolbar/search spacing is scoped to `saved-research.module.css`. Global styles, shared API types and dependency manifests are unchanged.

Three existing frontend files have integration changes:

- `apps/web/src/components/layout/research-workspace.tsx`: uses `useSavedResearch`, records searches, resets the save session when switching papers, restores filters, passes the saved layout to the canvas, and renders `SavedResearchControls`.
- `apps/web/src/hooks/use-citation-graph.ts`: exposes `edgeGroups` and adds `restore(snapshot)` to load saved state while cancelling earlier requests. Existing graph expansion behavior is retained.
- `apps/web/src/components/graph/citation-canvas.tsx`: accepts an optional initial layout and a ref exposing `getLayout()`. Existing callers can omit both. Reopening preserves saved positions; Dev 1's overlap spacing resumes when the focus or visible graph changes, and drag behavior is retained. Changing focus leaves already spaced nodes in place.

`SavedResearchControls` is a separate toolbar component with a dropdown panel and styles scoped to `saved-research.module.css`. **Saved & recent** remains available before opening a paper. Keep the integration changes together in review; conflicts remain possible if these three files change concurrently. No Dev 3 backend or ML files are modified.

The stored data format is version 1, under `trace.saved-graphs.v1` and `trace.recent-searches.v1`. Keep these keys and snapshot fields compatible when adjusting the UI.

## Verification

Run the repository lint, typecheck, test and build commands. The new `browser-library`, `saved-research-workspace` and `saved-research-canvas` tests use offline synthetic fixtures and cover persistence across mounts, update/delete, history replay/clearing, storage failure, hidden branches, stale requests and layout restoration.
