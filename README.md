# Meta Workers

A small, trusted self-hosted AI coworker POC: persistent local execution with a restrained three-pane interface.

## Quick start

Requirements: Docker Desktop, or Docker Engine with Compose.

1. Create an API key in the [OpenAI dashboard](https://platform.openai.com/api-keys).
2. Copy the example environment file and put the key in your untracked `.env`:

   ```sh
   cp .env.example .env
   # Edit .env and set OPENAI_API_KEY. Never commit .env.
   ```

3. Start both containers:

   ```sh
   docker compose up --build
   ```

Open <http://localhost:8000>. Nginx serves the React application there and proxies `/api/*` and `/healthz` to the internal backend. The UI also starts without a key so the POC remains inspectable.

Stop the application with `docker compose down`. SQLite data remains in the existing `meta-workers-data` volume.

Alice and Bob are seeded demo identities. Their data is logically separated, but **there is no authentication**: deploy only on a trusted machine or network.

The app creates one persistent, network-disabled Docker workspace per seeded user. Full access skips confirmations only inside that container; the backend controls Docker through the host socket and must be treated as privileged.

## Repository ownership

- `backend/`: Python package, SQLite migrations, tests, and dependency lock.
- `frontend/`: React application, unit tests, and Playwright tests.
- `infra/`: backend, frontend, and sandbox Dockerfiles.
- `deploy/`: Nginx and deployment-only assets.

The root owns the single `compose.yaml` entrypoint, environment example, notices, documentation, and planning state. No monorepo orchestrator is required.

## POC workflows

- **KYC Research Agent:** research a public company, review tool approvals, and download a cited Markdown/JSON due-diligence brief. This is not identity verification, regulated KYC, legal advice, or an onboarding decision. Do not submit PII or identity documents.
- **Skill Builder:** draft instruction-only skills, then review and activate them in Skills. Publishing exposes an immutable catalog version; installation creates an independent private copy.

Without `OPENAI_API_KEY`, the shell still runs and the agent explains that model access is not configured. OpenAI is the only model provider; the default and allowlist are both `gpt-5.6`.

## Local development

Run the backend:

```sh
cd backend
uv sync --extra dev
uv run uvicorn meta_workers.main:app --reload --env-file ../.env
```

In a second terminal, run the frontend:

```sh
cd frontend
pnpm install
pnpm dev
```

Open <http://localhost:5173>. Vite proxies `/api` and `/healthz` to the backend on port 8000.

## Verify

```sh
uv run --project backend --extra dev pytest
pnpm --dir frontend test
pnpm --dir frontend build
pnpm --dir frontend test:e2e
docker compose config
python3 /Users/jayden77/.agents/skills/jayden-workflow/scripts/validate_specs.py .
```

Playwright uses system Chrome on macOS when present; elsewhere run `pnpm --dir frontend exec playwright install chromium` once.

## Scope

Single-node trusted POC only. No auth, secure multi-tenancy, teams, mobile app, regulated KYC decisioning, private identity data, MCP/connectors, or production sandbox guarantees. SQLite data and artifacts persist in `meta-workers-data`. Unpinned artifacts/events expire after the configured retention window.

OpenWorker-derived runtime concepts are attributed in [NOTICE](NOTICE). The architectural trust decision is recorded in [ADR 0001](docs/adr/0001-trusted-single-node-poc.md).
