# Task: Runnable trusted-tenant shell

## Objective
Run the self-hosted application with seeded users, durable SQLite state, health reporting, and the empty three-pane product shell.

## User Story
As a demo user, I can select a seeded identity and enter a clearly labelled trusted POC workspace.

## Context
- The repository is greenfield.
- The POC is single-node and logically tenant-scoped without authentication.

## Changes
1. Add locked Python and frontend projects, configuration, SQLite migrations, and seed data.
2. Add FastAPI health and user APIs plus generated frontend-facing contracts.
3. Add the responsive React shell, user switcher, and trusted-demo warning.
4. Add Docker packaging and persistent application data.

## Verification
- `uv run pytest tests/test_foundation.py`
- `pnpm --dir web test`
- `pnpm --dir web build`
- `docker compose config`

## Done
- A seeded user can open the shell and `/healthz` reports database and Docker readiness.
