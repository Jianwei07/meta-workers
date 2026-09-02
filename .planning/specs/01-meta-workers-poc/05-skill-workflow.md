# Task: Skill workflow

## Objective
Create, review, assign, progressively load, publish, and install instruction-only internal skills.

## User Story
As a user, I can teach my coworkers a reviewed workflow and optionally share an immutable copy with other users.

## Context
- Skills contain metadata and instructions only in v1.
- The model may draft but cannot activate or publish.

## Changes
1. Add private skills, immutable versions, assignments, and published catalog queries.
2. Seed Skill Builder and add structured draft validation.
3. Expose assigned metadata and load full instructions only on demand.
4. Add draft review, activation, assignment, publishing, and copy-on-install UI.

## Verification
- `uv run pytest tests/test_skills.py`
- `pnpm --dir web test`

## Done
- A published version remains immutable and another seeded user installs an independent private copy.
