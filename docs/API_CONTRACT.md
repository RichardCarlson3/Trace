# API contract v1

Base URL `http://localhost:8000/api/v1`. JSON fields use snake_case. Runtime OpenAPI documentation is available at `/docs` and `/openapi.json`.

## Routes

| Method | Route | Current behavior |
| --- | --- | --- |
| GET | `/health` | 200 independent of database, model and external APIs |
| GET | `/papers/search?q=...&page=1&per_page=10` | Real OpenAlex search |
| GET | `/papers/{id}` | 501, intended Paper response |
| GET | `/papers/{id}/neighbors` | 501, intended Graph response |
| POST | `/classify` | 503 without artifact, Classification response when installed |
| POST | `/graphs` | 501, validates intended save request |
| GET | `/graphs` | 501, intended saved-graph summaries |
| GET | `/graphs/{id}` | 501, intended saved snapshot, UUID path parameter |

Paper path IDs use normalized `W` plus digits. Input schemas also normalize full `https://openalex.org/W...` IDs. Search requires a nonblank query of at most 300 characters, page at least 1 and per_page between 1 and 25. Search matches title/keyword/DOI text through the provider's search parameter.

## Health

```json
{"status":"ok","service":"researchgraph-api"}
```

## Paper and search response

| Paper field | Type |
| --- | --- |
| `id` | Normalized OpenAlex work ID string |
| `doi` | string or null, provider DOI URL |
| `title` | string |
| `year` | integer or null |
| `authors` | array of display-name strings |
| `abstract` | string or null |
| `cited_by_count` | nonnegative integer |
| `landing_page_url` | string or null |

Search returns `{papers: Paper[], total: integer, page: integer, per_page: integer}`. An empty result contains an empty papers array and a zero total. Unavailable abstracts remain null. A missing provider title displays the explicit missing-title label `Untitled work`.

## Citation and graph

| Citation field | Type and meaning |
| --- | --- |
| `id` | Stable relationship identifier string, future context-aware IDs should distinguish multiple passages |
| `source` | Citing OpenAlex work ID |
| `target` | Cited OpenAlex work ID |
| `intent` | `background`, `method`, `result`, or null |
| `confidence` | number in [0,1] or null |
| `context_text` | Genuine citation passage string or null |
| `context_source_url` | Source of the passage string or null |

If Paper B cites Paper A, the edge is `B -> A`. Never reverse source and target. Unclassified edges have null intent and confidence. A classified edge requires nonblank context text and confidence. Context-source provenance should be retained when supplied. Metadata titles alone cannot establish citation intent.

Graph returns `{papers: Paper[], citations: Citation[]}`. All citation endpoints must appear in papers, and paper IDs must be unique. Neighbor traversal direction/year query parameters will be agreed when expansion is implemented.

## Classification

Request body contains `context_text` with 1 to 20,000 characters, including non-whitespace text, and optional nullable `context_source_url`. Callers are responsible for supplying a genuine passage.

Response type is `{intent: CitationIntent, confidence: number}`. The installed pipeline predicts from the context only. Model versioning and inference batch contracts can be added when required. Missing/incompatible artifacts return HTTP 503 and `model_unavailable`.

## Intended graph persistence

`SaveGraphRequest` contains `name` (1–200 characters), normalized `seed_paper_id`, `graph`, `positions` keyed by paper ID with x/y numbers, `expanded_nodes`, `settings` and `filters`. Positions and settings preserve frontend state. An eventual saved snapshot adds `id`, `created_at` and `updated_at`. List summaries should contain `id`, `name`, `seed_paper_id`, `created_at` and `updated_at`. Authentication and authorization are required before these responses are implemented. Never accept caller-provided owner identity as proof of ownership.

## Errors

```json
{"error":{"code":"model_unavailable","message":"No trained citation model is installed"}}
```

422 validation errors add `details`, an array containing `loc` and `msg`. Service errors use 502 for unreachable/rejected/invalid provider responses and 503 for exhausted transient retries or missing models. Planned features use 501 with `not_implemented`. Standard missing routes use `http_error`. Unexpected failures return HTTP 500 with `internal_error` and a generic message, with diagnostic details in backend logs.
