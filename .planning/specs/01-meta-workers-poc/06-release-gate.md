# Task: POC release gate

## Objective
Ship a reproducible, accessible, observable, and documented POC with deterministic end-to-end verification.

## Context
- Automated tests remain offline through fake model, clock, Docker, and web boundaries.
- External model/web checks are optional canaries.

## Changes
1. Finish responsive and keyboard/screen-reader behavior.
2. Add structured redacted logs, security headers, operator warnings, and health diagnostics.
3. Add Playwright POC flows, deployment instructions, and scope disclaimers.

## Verification
- `uv run pytest`
- `pnpm --dir web test`
- `pnpm --dir web build`
- `pnpm --dir web test:e2e`
- `docker compose config`

## Done
- All checks pass and a fresh operator can launch and complete both POC workflows from the README.
