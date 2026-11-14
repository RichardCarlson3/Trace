# Initial decisions

## Monorepo with npm workspaces and a uv project

Keep the web and API applications under `apps/`. npm provides cross-platform root commands, and concurrently coordinates two development servers. uv installs Python dependencies and runs commands without manual virtual environment activation. Lockfiles capture both dependency graphs.

## Node 24 and Python 3.12

Use the requested LTS major and Python minor. Next.js CLI scaffolding provides the compatible App Router, React and Tailwind setup. TypeScript is strict. Backend packaging makes `app` and `ml` importable from root-level commands.

## Optional PostgreSQL

Database connectivity is independent of application startup. Use SQLAlchemy 2.x, psycopg 3 and explicit Alembic migrations. JSONB snapshots support the MVP saved-graph representation without a large relational graph schema.

## Persistence waits for authenticated ownership

Keep graph endpoints at HTTP 501. Future identity must be verified server-side and checked on every graph operation. Anonymous caller-supplied IDs do not prove ownership. Authentication implementation needs team selection before persistence work.

## Canonical scholarly contracts

Use normalized OpenAlex work IDs and snake_case JSON. A citation source is the citing paper and target is the cited paper. Preserve nullable metadata and unavailable intent. Pydantic validates evidence requirements and graph endpoints.

## Real search as the first vertical slice

Search FastAPI through HTTPX against OpenAlex with a bounded timeout and at most three attempts. Display selected search metadata in the canvas and details pane. Provider outages surface as errors while the workspace stays usable. The remaining routes expose HTTP 501 contracts.

## Pipeline artifact and separate training dependencies

Bundle a fitted TF-IDF vectorizer and logistic regression classifier in one sklearn Pipeline, saved with joblib. Load it lazily for context-only inference. Keep NumPy/scikit-learn/joblib runtime compatibility in the same uv lockfile. Install datasets, Pandas and plotting packages through the training group. Original SciCite JSONL avoids obsolete remote dataset loading scripts.

## Lightweight validation

Use Vitest/Testing Library, pytest, ESLint, Prettier and Ruff. Tests mock provider HTTP and run without credentials, model artifacts or a database. CI also builds Next.js. Browser smoke testing checks the real React Flow integration.
