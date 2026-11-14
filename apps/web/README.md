# ResearchGraph frontend

The App Router entry point is `src/app/page.tsx`. Workspace components live in `src/components`, network state in `src/hooks`, and shared API transport/types in `src/lib`.

Use the repository-root [setup instructions](../../README.md) to install both applications. Copy `.env.example` to `.env.local` and run `npm run dev:web` from the root. FastAPI is expected at `http://localhost:8000` by default.

```text
npm run lint:web
npm run typecheck
npm run test:web
npm run build
```

Run `npm run format --workspace apps/web` for formatting. The real React Flow canvas has a DOM initialization test. Search results and selected paper details use provider data retrieved by FastAPI. Future citation expansion should preserve the backend contracts and citation direction documented in `docs/API_CONTRACT.md`.
