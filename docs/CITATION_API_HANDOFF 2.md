# Citation API handoff: Tasks 1–6

## Delivered backend behavior

The OpenAlex service now supports paper details, outgoing references, incoming citations,
and bounded graph expansion. Routes preserve the existing Graph names (`papers`, `citations`)
and snake_case JSON. Metadata and relationships come from OpenAlex. No citation-context
retrieval or classifier call occurs during expansion. PostgreSQL and trained artifacts are
not required for these endpoints. Persistence endpoints remain HTTP 501 pending authenticated
ownership. See [the API contract](API_CONTRACT.md) for the complete schemas and error policies.

| Task | Implemented capability |
| --- | --- |
| 1 | Details with normalized metadata, venue, and reference count |
| 2 | Batched outgoing references with local offset pagination |
| 3 | Incoming citations using OpenAlex cursor pagination |
| 4 | One-hop neighbors: incoming, outgoing, or both, with a combined budget |
| 5 | Hard network deadlines, bounded retries/Retry-After waits, concurrent directions and cancellation cleanup |
| 6 | DOI/ID and missing-metadata normalization, graph/direction validation, request error handling, key-isolation tests |

## Endpoint examples

Start from the repository root with `npm run dev` (both servers) or `npm run dev:api`
(API only). Swagger is at `http://localhost:8000/docs`.

```bash
curl --fail-with-body 'http://localhost:8000/api/v1/papers/search?q=open%20access&per_page=5'
curl --fail-with-body 'http://localhost:8000/api/v1/papers/W2741809807'
curl --fail-with-body 'http://localhost:8000/api/v1/papers/W2741809807/references?limit=5&offset=0'
curl --fail-with-body 'http://localhost:8000/api/v1/papers/W2741809807/citations?limit=5&cursor=*'
curl --fail-with-body 'http://localhost:8000/api/v1/papers/W2741809807/neighbors?direction=both&limit=6&cursor=*'
```

The detail lookup was checked live and returned the following excerpt. Other Paper fields
are omitted here; this is not the full response. Provider values can change.

```json
{
  "id": "W2741809807",
  "title": "The state of OA: a large-scale analysis of the prevalence and impact of Open Access articles",
  "doi": "https://doi.org/10.7717/peerj.4375",
  "publication_venue": "PeerJ",
  "reference_count": 46
}
```

The outgoing graph also contained this real directed relationship (excerpt only; additional
papers, edges, Paper fields, and pagination fields are omitted):

```json
{
  "seed_paper_id": "W2741809807",
  "papers": [
    {"id": "W2741809807", "title": "The state of OA: a large-scale analysis of the prevalence and impact of Open Access articles"},
    {"id": "W1560783210", "title": "Anatomy of green open access"}
  ],
  "citations": [
    {
      "id": "W2741809807->W1560783210",
      "source": "W2741809807",
      "target": "W1560783210",
      "intent": null,
      "confidence": null,
      "context_text": null,
      "context_source_url": null
    }
  ]
}
```

## Connecting the frontend (Developer 1)

The current UI still uses search metadata and shows one selected paper with no edges.
Backend completion does not connect the canvas automatically. Implement browser requests
through `apps/web/src/lib/api.ts` and hooks, using the existing loading, error, cancellation,
and empty states. Keep the key exclusively in backend `apps/api/.env`. The public frontend
configuration is only `NEXT_PUBLIC_API_BASE_URL`.

Add response types alongside the existing Paper/Graph definitions when integrating, matching
the runtime OpenAPI schema. For neighbors, the needed TypeScript shape is:

```typescript
interface NeighborResponse extends Graph {
  seed_paper_id: string;
  has_more: boolean;
  next_cursor: string | null;
  unresolved_reference_ids: string[];
  skipped_record_count: number;
}
```

The response's `papers` are ordinary Paper objects. The detail endpoint additionally returns
`publication_venue: string | null` and `reference_count: number | null`.

Recommended integration sequence:

1. When expanding a selected node, request `/papers/{id}/neighbors` with the chosen direction,
   limit, and `cursor=*`. Keep the ID uppercase with ASCII digits.
2. Merge `papers` by stable `paper.id`; preserve existing node positions. Position only new
   nodes using the frontend's chosen layout. Map each paper to a React Flow node with that ID
   and its Paper data. The API does not supply positions.
3. Merge `citations` by `citation.id` (or directed source/target pair). Map to React Flow edges
   using `id`, `source`, and `target` unchanged. Never reverse incoming edges to make all arrows
   point out of the selected node. Opposite-direction edges are distinct relationships.
4. Store `next_cursor` with the requested seed, direction, and limit. Follow it unchanged for
   that query; reset to `*` when those controls change. Maintain separate state per expansion.
5. Continue while `has_more` is true even if a page is short/empty after filtering. Display
   unresolved-reference and skipped-record information as partial-data feedback. Merge by ID
   across pages and seeds because responses can overlap.
6. On errors, retain the existing graph and show the error. Retry the same token if appropriate;
   do not advance it on a failed request. Aborting the browser request should remain supported.

For standalone outgoing references, follow `next_offset`; for standalone incoming citations,
follow its raw OpenAlex `next_cursor`. These tokens are not interchangeable with neighbors
tokens. `limit` is 1–50 total neighbors, excluding the seed. `both` splits the budget; with a
limit of one it alternates directions. No classification should be displayed for null intent.

## Verification

Run the required offline checks from the repository root:

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```

Tests use labeled synthetic fixtures and mocked HTTP calls. `test_paper_details.py`,
`test_references.py`, `test_incoming_citations.py`, `test_neighbors.py`,
`test_pagination_performance.py`, and `test_api_reliability.py` cover this work. Existing
inference/ML tests remain part of the full backend suite. The optional datasets/plot checks
skip without the training dependency group. Installing that group does not train a model;
training and dataset downloads remain explicit developer commands.

At the Task 6 checkpoint, lint, type checking, frontend build, all six frontend tests, and
317 backend tests passed. Two optional ML integration tests skipped without training-group
packages. The existing Starlette/HTTPX TestClient deprecation warning remains; it did not
fail verification. No dependency or lockfile changes were made for these API tasks.

Live checks during the reliability audit verified paper details and two pages in all three
neighbor directions, with normalized IDs/DOIs, unique nodes/edges, valid endpoints, no page
overlap in those samples, and null classification fields. The configured backend key allowed
incoming continuation. This is a smoke check, not a guarantee of upstream availability.

## Implementation map

- `apps/api/app/api/v1/papers.py`: routes and query/path validation.
- `apps/api/app/services/openalex.py`: HTTP requests, normalization, batching, pagination,
  retry/deadline policy, and neighbor merging.
- `apps/api/app/services/neighbor_cursor.py`: versioned stateless neighbors continuation state.
- `apps/api/app/schemas/contracts.py`: response models and normalization/graph invariants.
- `apps/api/tests/`: offline provider, graph, pagination, and reliability tests.
- `docs/API_CONTRACT.md`: detailed network contract and manual verification commands.

## Limitations and future coordination

- No persistent metadata cache, graph saving, ownership/authentication, or year filtering.
  A cache strategy is documented in the API contract but no database dependency was added.
- Incoming cursor continuation requires a valid backend OpenAlex key and available quota.
- Search is limited to the provider's basic 10,000-result window. Citation cursors support
  larger neighborhoods, fetched one bounded page at a time.
- OpenAlex can omit abstracts/metadata or change records between requests. Offset traversal
  is not a frozen snapshot. Missing/merged reference metadata is reported without invented
  replacements or inferred relationships.
- The frontend must merge stable IDs across pages and expansion queries. Per-response
  deduplication cannot guarantee exactly-once results across a changing upstream dataset.
- Graphs currently allow one edge per directed pair. Supporting multiple citation passages
  per pair requires an agreed contract change with frontend and inference owners.
- Backend response semantics now canonicalize DOIs and enforce graph invariants. Coordinate
  frontend response types and any saved-data migration before extending those contracts.
- Genuine citation-context retrieval and classifier integration into graphs remain separate
  work. Model scores are uncalibrated; this API does not invent contexts or predictions.

No push or merge is part of this handoff. Review and commit the Task 6 changes separately.
