import asyncio
import sqlite3
from pathlib import Path

from meta_workers.db import Database


def test_legacy_grok_volume_migrates_without_losing_user_data(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    migration_dir = Path(__file__).parents[1] / "migrations"
    with sqlite3.connect(path) as connection:
        connection.executescript((migration_dir / "0001_initial.sql").read_text())
        connection.execute("INSERT INTO schema_migrations(version) VALUES ('0001_initial')")
        connection.execute("INSERT INTO users(id, name) VALUES ('legacy_user', 'Legacy')")
        connection.execute("INSERT INTO agents(id, user_id, name, instructions, model, permission_mode) VALUES ('legacy_agent', 'legacy_user', 'Legacy Agent', 'Keep me', 'grok-4.3', 'ask')")
        connection.execute("INSERT INTO threads(id, user_id, agent_id) VALUES ('legacy_thread', 'legacy_user', 'legacy_agent')")
        connection.execute("INSERT INTO runs(id, user_id, agent_id, thread_id, trigger, status) VALUES ('legacy_run', 'legacy_user', 'legacy_agent', 'legacy_thread', 'manual', 'succeeded')")
        connection.execute("INSERT INTO messages(id, user_id, thread_id, run_id, seq, role, content) VALUES ('legacy_message', 'legacy_user', 'legacy_thread', 'legacy_run', 1, 'user', 'Keep transcript')")
        connection.execute("INSERT INTO artifacts(id, user_id, run_id, name, media_type, path) VALUES ('legacy_artifact', 'legacy_user', 'legacy_run', 'keep.md', 'text/markdown', '/tmp/keep.md')")
        connection.execute("INSERT INTO routines(id, user_id, agent_id, name, prompt, cron, timezone) VALUES ('legacy_routine', 'legacy_user', 'legacy_agent', 'Keep routine', 'Run', '0 9 * * 1', 'UTC')")
        connection.execute("INSERT INTO skills(id, user_id, name, status) VALUES ('legacy_skill', 'legacy_user', 'keep-skill', 'draft')")
        connection.execute("INSERT INTO skill_versions(id, skill_id, version, description, instructions) VALUES ('legacy_skill_v1', 'legacy_skill', 1, 'Keep', 'Keep instructions')")
        connection.execute("UPDATE skills SET current_version_id = 'legacy_skill_v1' WHERE id = 'legacy_skill'")

    asyncio.run(Database(path, migrations_dir=migration_dir).migrate())

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT model FROM agents WHERE id = 'legacy_agent'").fetchone()[0] == "gpt-5.6"
        assert connection.execute("SELECT content FROM messages WHERE id = 'legacy_message'").fetchone()[0] == "Keep transcript"
        for table in ("runs", "artifacts", "routines", "skills"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table} WHERE id LIKE 'legacy_%'").fetchone()[0] == 1
        assert "response_items_json" in {row[1] for row in connection.execute("PRAGMA table_info(messages)")}
