# Task: KYC research workflow

## Objective
Produce a cited public-company due-diligence brief with memory, routines, bounded recovery, and deterministic cleanup.

## User Story
As an analyst, I can ask a coworker to research a company and receive a reviewable non-regulatory brief.

## Context
- Public sources only; no PII, identity documents, or approve/reject decisions.
- Memory stores user preferences, not stale case facts.

## Changes
1. Add public web search/browser read tools with SSRF protection.
2. Seed the KYC Research Agent and validated report artifact contract.
3. Add bounded memory retrieval, cron routines, run recovery, retry, and cleanup.
4. Add report, memory, routine, and Activity UI states.

## Verification
- `uv run pytest tests/test_kyc.py`
- `pnpm --dir web test`

## Done
- The offline fixture flow produces Markdown and JSON briefs with citations, unknowns, and the required disclaimer.
