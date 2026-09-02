from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import aiosqlite


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class Database:
    def __init__(self, path: Path, migrations_dir: Path | None = None, default_model: str = "gpt-5.6") -> None:
        self.path = path
        self.migrations_dir = migrations_dir or Path(__file__).parents[2] / "migrations"
        self.default_model = default_model

    async def connect(self) -> aiosqlite.Connection:
        connection = await aiosqlite.connect(self.path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys = ON")
        await connection.execute("PRAGMA journal_mode = WAL")
        await connection.execute("PRAGMA synchronous = NORMAL")
        await connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    async def migrate(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = await self.connect()
        try:
            await connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            rows = await connection.execute_fetchall("SELECT version FROM schema_migrations")
            applied = {row[0] for row in rows}
            for migration in sorted(self.migrations_dir.glob("*.sql")):
                if migration.stem in applied:
                    continue
                await connection.executescript(migration.read_text())
                await connection.execute(
                    "INSERT INTO schema_migrations(version) VALUES (?)", (migration.stem,)
                )
                await connection.commit()
        finally:
            await connection.close()
        await self.seed()

    async def seed(self) -> None:
        users = (("user_alice", "Alice"), ("user_bob", "Bob"))
        connection = await self.connect()
        try:
            for user_id, name in users:
                await connection.execute(
                    "INSERT OR IGNORE INTO users(id, name) VALUES (?, ?)", (user_id, name)
                )
                await self._seed_agent(
                    connection,
                    user_id,
                    "kyc",
                    "KYC Research Agent",
                    "Research public companies using public sources only. Never process private identity data or make onboarding decisions. Always finish completed research by calling publish_due_diligence_report with evidence-linked findings, unknowns, and manual checks.",
                )
                await self._seed_agent(
                    connection,
                    user_id,
                    "skills",
                    "Skill Builder",
                    "Help the user draft concise internal skills. Save drafts for review; never activate, assign, or publish them yourself.",
                )
            await connection.commit()
        finally:
            await connection.close()

    async def _seed_agent(
        self,
        connection: aiosqlite.Connection,
        user_id: str,
        suffix: str,
        name: str,
        instructions: str,
    ) -> None:
        agent_id = f"agent_{user_id.removeprefix('user_')}_{suffix}"
        thread_id = f"thread_{user_id.removeprefix('user_')}_{suffix}"
        await connection.execute(
            """
            INSERT OR IGNORE INTO agents(id, user_id, name, instructions, model, permission_mode, kind)
            VALUES (?, ?, ?, ?, ?, 'ask', ?)
            """,
            (agent_id, user_id, name, instructions, self.default_model, suffix),
        )
        await connection.execute(
            "INSERT OR IGNORE INTO threads(id, user_id, agent_id) VALUES (?, ?, ?)",
            (thread_id, user_id, agent_id),
        )

    async def fetchall(self, sql: str, values: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        connection = await self.connect()
        try:
            cursor = await connection.execute(sql, values)
            return [dict(row) for row in await cursor.fetchall()]
        finally:
            await connection.close()

    async def fetchone(self, sql: str, values: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        connection = await self.connect()
        try:
            cursor = await connection.execute(sql, values)
            row = await cursor.fetchone()
            return dict(row) if row else None
        finally:
            await connection.close()

    async def execute(self, sql: str, values: tuple[Any, ...] = ()) -> None:
        connection = await self.connect()
        try:
            await connection.execute(sql, values)
            await connection.commit()
        finally:
            await connection.close()

    async def insert_event(
        self, user_id: str, run_id: str, thread_id: str, kind: str, payload: dict[str, Any]
    ) -> int:
        connection = await self.connect()
        try:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM run_events WHERE thread_id = ?",
                (thread_id,),
            )
            seq = (await cursor.fetchone())[0]
            await connection.execute(
                "INSERT INTO run_events(id, user_id, run_id, thread_id, seq, kind, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (new_id("event"), user_id, run_id, thread_id, seq, kind, json.dumps(payload)),
            )
            await connection.commit()
            return seq
        finally:
            await connection.close()
