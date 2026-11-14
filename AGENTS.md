# ResearchGraph repository instructions

## Source and ownership

- `apps/web/src` contains the Next.js App Router UI, React Flow components, hooks and typed API client.
- `apps/api/app` contains FastAPI routes, schemas, services and optional PostgreSQL infrastructure.
- `apps/api/ml` contains explicit training and evaluation commands.
- `docs/API_CONTRACT.md` defines the network contract. Coordinate changes to this file, Pydantic schemas and TypeScript types.
- Follow the ownership boundaries in CONTRIBUTING.md. Keep teammate-owned changes scoped to the task.

## Constraints

- Use npm workspaces and uv with committed lockfiles. Keep dependencies minimal.
- Keep database connectivity optional. Health, search and inference must operate independently of database configuration.
- Use PostgreSQL, SQLAlchemy 2.x, Alembic and psycopg. Create the engine lazily. Run migrations explicitly.
- Persisted graph endpoints remain HTTP 501 until authenticated ownership is designed and enforced.
- Stable OpenAlex work IDs use `W` followed by digits. Use snake_case JSON fields.
- A citation runs from the citing paper to the cited paper. If B cites A, use B -> A.
- Never invent research metadata, citation contexts, confidence scores or model predictions.
- Classify only genuine citation-context text. Unclassified edges have null intent and confidence.
- Training and dataset downloads happen through explicit developer commands. Backend startup must work without artifacts.
- Keep secrets in ignored backend environment files. Only the public API base URL belongs in NEXT_PUBLIC variables.
- Keep provider requests inside services and frontend requests inside `src/lib/api.ts` and hooks.
- Use client components for browser interactions and React Flow. Preserve loading, error and empty states.

## Verification

From the repository root after `npm ci` and `uv sync --project apps/api --locked --group dev`, run the following commands.

```text
npm run lint
npm run typecheck
npm run test
npm run build
```

Use `npm run format:api` for Python formatting and `npm run format --workspace apps/web` for frontend formatting. Tests must run offline using clearly labeled fixtures.
