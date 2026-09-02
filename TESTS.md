# Tests

- `uv run pytest`: seeded-user isolation, persistent/idempotent chat runs, durable tool approval, SSRF rejection, report artifacts, routines, and immutable skill installation.
- `pnpm --dir web test`: trusted-POC shell rendering with mocked HTTP boundaries.
- `pnpm --dir web build`: strict TypeScript check and production bundle.
- `pnpm --dir web test:e2e`: mocked desktop/mobile navigation in Chromium or system Chrome.
- `docker compose config`: deployment definition validation.

Model, public-web, and real Docker execution are deliberately offline in automated tests. Exercise those as environment-specific canaries after setting credentials and starting Docker.
