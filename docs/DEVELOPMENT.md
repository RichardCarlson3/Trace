# Development guide

## Install prerequisites

Install Node.js 24 LTS using the official installer. npm is included. Install Git and uv, then restart your terminal. uv manages Python 3.12 automatically through `apps/api/.python-version`. A separate Python installer is optional.

- [Node.js downloads](https://nodejs.org/en/download)
- [Git downloads](https://git-scm.com/downloads)
- [uv installation](https://docs.astral.sh/uv/getting-started/installation/)
- [Python downloads](https://www.python.org/downloads/)

The official uv installer commands are shown below. Review the linked installer documentation when installing tooling.

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Windows PowerShell

```powershell
git clone <repository-url>
cd <repository-directory>
node --version
uv --version
npm ci
uv sync --project apps/api --locked --group dev
Copy-Item apps/api/.env.example apps/api/.env
Copy-Item apps/web/.env.example apps/web/.env.local
npm run dev
```

Copy example files once during initial setup. Keep existing local values when updating the checkout. A database account, OpenAlex key and trained model are optional. The frontend calls the health endpoint on mount and makes OpenAlex requests through FastAPI only after a search.

## macOS and Linux

Use the same Node 24, npm, uv and Git prerequisites. With nvm already installed, `nvm install` selects `.nvmrc`. Run the Windows quick-start commands using `cp` for the environment files.

```bash
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local
```

## Development and validation

```text
npm run dev:web
npm run dev:api
npm run lint
npm run typecheck
npm run test
npm run build
```

`npm run dev` starts both servers. Ctrl+C stops the session. Run `npm run start --workspace apps/web` after a production build to smoke-test production serving with a separately running API. Frontend tests isolate React Flow for the basic render test. Browser verification exercises the actual graph canvas.

CI uses `npm ci` and `uv sync --locked` with committed lockfiles. To add a frontend package use `npm install <package> --workspace apps/web`. To add a backend runtime package use `uv add --project apps/api <package>`. Use `--group training` for training-only additions.

## Configuration

| Backend variable | Default and use |
| --- | --- |
| `APP_ENV` | `development`, reserved environment label |
| `API_HOST` | `127.0.0.1`, local bind address |
| `API_PORT` | `8000` |
| `CORS_ORIGINS` | `http://localhost:3000`, comma-separated allowed origins |
| `OPENALEX_BASE_URL` | `https://api.openalex.org` |
| `OPENALEX_API_KEY` | Empty, optional backend-only key |
| `DATABASE_URL` | Empty, required only for migration/database operations |
| `MODEL_ARTIFACT_DIR` | Empty selects `apps/api/artifacts`, relative overrides resolve from `apps/api` |

Frontend `NEXT_PUBLIC_API_BASE_URL` defaults to `http://localhost:8000` and is embedded during the frontend build. Restart the frontend after changes. Browser origins distinguish `localhost` from `127.0.0.1`.

## Dependency notices

The installed TypeScript ESLint dependency chain currently carries seven moderate npm audit findings through minimatch. Compatible `npm audit fix` did not resolve them. Recheck the upstream TypeScript ESLint release before updating the lint toolchain. The backend tests also emit a Starlette deprecation notice for its HTTPX TestClient integration. Test behavior passes with the locked dependencies.

## Optional TigerData

Create or select a Tiger Cloud PostgreSQL service, open its connection details, and copy the host, port, database and role. Retrieve or reset the password through the service console. Assemble a `postgresql+psycopg` SQLAlchemy URL and retain `sslmode=require`. Store it in `apps/api/.env`. The console connection string may use `postgres://` or `postgresql://`, which should be changed to `postgresql+psycopg://` for this application.

Run migrations from the root with the following command.

```text
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
```

Inside `apps/api`, use `uv run alembic upgrade head`. Startup never runs migrations. The initial schema is PostgreSQL-specific and contains JSONB graph snapshots. The `updated_at` update behavior is provided by SQLAlchemy when future ORM writes are implemented.

Keep persistence routes at HTTP 501 until authenticated owner identity and server-side authorization checks are implemented. An arbitrary session identifier supplied by a browser cannot establish ownership.

[TigerData connection documentation](https://docs.tigerdata.com/use-timescale/latest/integrations/)
