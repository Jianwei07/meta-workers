# Task: Safe coworker tools

## Objective
Run approved shell and file operations inside each user's isolated Docker workspace and expose artifacts in chat.

## User Story
As a user, I can understand and control what my coworker is allowed to do.

## Context
- Sandboxes never receive host mounts, secrets, or the Docker socket.
- Full access remains container-only.

## Changes
1. Add per-user sandbox lifecycle and shell/file/artifact tool adapters.
2. Add Ask, Workspace, and Full permission policies with durable approval state.
3. Render tool progress, approval decisions, artifacts, and computer health in the UI.

## Verification
- `uv run pytest tests/test_tools.py`
- `pnpm --dir web test`

## Done
- Two users cannot access each other's workspaces, and approval decisions resume the correct tool call.
