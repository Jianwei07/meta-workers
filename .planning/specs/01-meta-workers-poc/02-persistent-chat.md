# Task: Persistent coworker chat

## Objective
Create an agent, stream a bounded model run, and restore its transcript after reload or stream reconnect.

## User Story
As a user, I can chat with a persistent coworker and see its live progress and recent activity.

## Context
- Adapt the OpenWorker engine/event patterns with MIT attribution.
- One active run and one thread per agent.

## Changes
1. Add tenant-scoped agents, threads, messages, runs, and ordered run events.
2. Add the OpenAI-compatible provider and bounded tool loop.
3. Add run creation, stop, snapshot, Activity, and resumable SSE APIs.
4. Connect the shell transcript and composer to the durable event stream.

## Verification
- `uv run pytest tests/test_chat.py`
- `pnpm --dir web test`

## Done
- A scripted model response streams, persists, reloads, and resumes without duplicate messages.
