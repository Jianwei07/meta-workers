# Meta Workers

A small self-hosted AI coworker POC: OpenWorker-style persistent execution with a restrained three-pane interface inspired by Rakazo.

## Quick start

Requirements: Docker Desktop (or Docker Engine with Compose).

```sh
cp .env.example .env
# Add MODEL_API_KEY to .env for real Grok responses.
docker compose up --build
```

Open <http://localhost:8000>. The UI also starts without a model key so you can inspect the POC. Stop it with `docker compose down`; stored data remains in the Docker volume.

Alice and Bob are seeded demo identities. Their data is logically separated, but **there is no authentication**: deploy only on a trusted machine/network.

The app creates one persistent, network-disabled Docker workspace per seeded user. Full access skips confirmations only inside that container; the application itself controls Docker through the host socket and must be treated as privileged.

## POC workflows

- **KYC Research Agent:** research a public company, review tool approvals, and download a cited Markdown/JSON due-diligence brief. This is not identity verification, regulated KYC, legal advice, or an onboarding decision. Do not submit PII or identity documents.
- **Skill Builder:** draft instruction-only skills, then review and activate them in Skills. Publishing exposes an immutable catalog version; installation creates an independent private copy.

Without `MODEL_API_KEY`, the shell still runs and the agent explains that model access is not configured.

## Local development

```sh
uv sync --extra dev
pnpm --dir web install
uv run uvicorn meta_workers.main:app --reload
```

In a second terminal:

```sh
pnpm --dir web dev
```

Open <http://localhost:5173>. Vite proxies API requests to the backend on port 8000.

## Verify

```sh
uv run pytest
pnpm --dir web test
pnpm --dir web build
pnpm --dir web test:e2e
docker compose config
```

Playwright uses system Chrome on macOS when present; elsewhere run `pnpm --dir web exec playwright install chromium` once.

## Scope

Single-node trusted POC only. No auth, secure multi-tenancy, teams, mobile app, regulated KYC decisioning, private identity data, MCP/connectors, or production sandbox guarantees. SQLite data and artifacts persist in the `meta-workers-data` volume. Unpinned artifacts/events expire after the configured retention window.

OpenWorker-derived runtime concepts are attributed in [NOTICE](NOTICE). The architectural trust decision is recorded in [ADR 0001](docs/adr/0001-trusted-single-node-poc.md).
