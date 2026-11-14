# ResearchGraph
ResearchGraph is a full-stack web app for exploring academic papers through interactive citation graphs. It uses OpenAlex for paper discovery and a SciCite-trained model to classify available citation passages as Background, Method, or Result.

The development foundation provides live paper search, selection into a React Flow canvas, paper details from search metadata, and a FastAPI connection indicator. The API also supports live paper-detail lookup through `GET /api/v1/papers/{id}`; the frontend does not yet call this endpoint. Graph expansion and persistent saves have HTTP 501 contracts. Classification returns HTTP 503 until a trained artifact is installed.

## Stack and prerequisites

- Node.js 24 LTS and npm, Next.js App Router, React, strict TypeScript, Tailwind CSS and React Flow.
- Python 3.12 managed by uv, FastAPI, Pydantic Settings and HTTPX.
- Vitest, Testing Library, ESLint, Prettier, pytest and Ruff.
- Optional PostgreSQL/TigerData through SQLAlchemy, Alembic and psycopg.
- scikit-learn/joblib inference with a separately installed SciCite training dependency group.
- Git and a terminal. See [development prerequisites](docs/DEVELOPMENT.md) for installation links.

## Windows 11 quick start

Replace the repository URL and directory name with the team's actual values. The existing checkout directory is named `Trace`.

```powershell
git clone <repository-url>
cd <repository-directory>
npm ci
uv sync --project apps/api --locked --group dev
Copy-Item apps/api/.env.example apps/api/.env
Copy-Item apps/web/.env.example apps/web/.env.local
npm run dev
```

The example environment files provide working defaults. Leave database and model settings blank to begin. `uv` downloads Python 3.12 when a compatible interpreter is missing. Virtual environment activation is handled by `uv run`.

On macOS/Linux, replace the two copy commands with the following commands. The remaining setup commands are identical.

```bash
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local
```

Open the [frontend](http://localhost:3000), [backend health](http://localhost:8000/api/v1/health), or [interactive API documentation](http://localhost:8000/docs). Search a title, keyword or DOI, then select a returned paper to populate the canvas and details panel.

## Commands

Run these commands from the repository root.

| Command | Purpose |
| --- | --- |
| `npm run dev` | Start both servers with coordinated shutdown |
| `npm run dev:web` | Start Next.js |
| `npm run dev:api` | Start FastAPI with reload |
| `npm run lint` | ESLint and Ruff lint/format checks |
| `npm run typecheck` | Generate Next route types and check strict TypeScript |
| `npm run test` | Run offline frontend and backend tests |
| `npm run build` | Produce the frontend production build |
| `npm run format --workspace apps/web` | Format frontend files |
| `npm run format:api` | Format Python files |

## Environment and optional TigerData

`NEXT_PUBLIC_API_BASE_URL` points to FastAPI. Backend `.env` is anchored to `apps/api` for commands run from either directory. `CORS_ORIGINS` accepts comma-separated browser origins. `OPENALEX_API_KEY` is optional for initial search and stays server-side. Provider quotas and availability can affect live results.

For TigerData, open your service's connection details and obtain the host, port, database, user and password. Set the backend-only connection URL with TLS enabled, URL-encoding special characters in credentials.

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME?sslmode=require
```

Run the initial migration explicitly after supplying credentials.

```text
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
```

This creates the graph snapshot table. Persistence endpoints require a future ownership/authentication implementation. Health and search work with an empty `DATABASE_URL`. `MODEL_ARTIFACT_DIR` defaults to `apps/api/artifacts`. See [ML instructions](apps/api/ml/README.md) for explicit training and evaluation commands.

## Troubleshooting

- If `uv` or Node is missing, install the prerequisites and restart the terminal. Use Node 24, as recorded in `.nvmrc`.
- If ports 3000/8000 are occupied, stop the previous development session. Changing backend ports requires updating the frontend URL and restarting Next.js. Changing the frontend origin requires updating `CORS_ORIGINS`.
- If the API indicator is offline, run `npm run dev:api` and inspect the terminal. Check the health URL and frontend environment URL.
- If search fails, inspect the structured error shown in the UI. Check internet access and the OpenAlex key/quota. The empty workspace remains accessible.
- If classification returns `model_unavailable`, install the trusted trained pipeline described in the ML README and restart FastAPI.
- Run migration commands from the root as shown, or use `uv run alembic upgrade head` inside `apps/api`.
- After changing dependencies, run `npm install` or `uv lock --project apps/api`, then commit the matching lockfile.

## Team documentation

- [Development guide](docs/DEVELOPMENT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API contract](docs/API_CONTRACT.md)
- [Architecture decisions](docs/DECISIONS.md)
- [Ownership and contribution workflow](CONTRIBUTING.md)

The existing repository license is preserved in [LICENSE](LICENSE).
