# Tests

- `cd backend && uv run pytest`: settings, stateless Responses history, legacy migration, seeded-user isolation, persistent/idempotent runs, durable tool approval, SSRF rejection, report artifacts, routines, and immutable skill installation.
- `pnpm --dir frontend test`: trusted-POC shell rendering with mocked HTTP boundaries.
- `pnpm --dir frontend build`: strict TypeScript check and production bundle.
- `pnpm --dir frontend test:e2e`: mocked desktop/mobile navigation in Chromium or system Chrome.
- `docker compose config`: deployment definition validation.

Model, public-web, and real Docker execution are deliberately offline in automated tests. Exercise those as environment-specific canaries after setting credentials and starting Docker.
