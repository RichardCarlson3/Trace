# Contributing to ResearchGraph

Keep `main` stable. Create short-lived feature branches, open pull requests, and integrate frequently. Enable branch protection in GitHub when the team configures the remote repository.

```text
git switch -c feat/paper-details
npm run lint
npm run typecheck
npm run test
npm run build
```

## Developer A

Own `apps/web/`, React Flow visualization, search and paper-details interfaces, and graph expansion UI. Own `apps/api/app/services/openalex.py` and `apps/api/app/api/v1/papers.py` for scholarly-data retrieval. Next work includes work-detail retrieval and references/incoming-citation endpoints, preserving source-to-target citation direction.

## Developer B

Own `apps/api/ml/`, inference and classification, SQLAlchemy models, Alembic migrations, graph persistence and backend tests. Next work includes evaluating the SciCite baseline, installing its artifact, and proposing authenticated graph ownership before enabling persistence.

## Shared changes

Discuss edits to `app/main.py`, configuration, `app/schemas/contracts.py`, `apps/web/src/lib/types.ts`, API documentation, root scripts and lockfiles before concurrent work. Agree on contract changes in a small shared PR before implementing consumers. Pull the initialized foundation into both feature branches.

Maintain the citation-context evidence rules, optional database startup and explicit HTTP 501/503 behavior. Keep test fixtures in test directories. Update lockfiles with npm or uv when dependency inputs change. Run the checks above before review.
