from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent

from .config import Settings
from .db import Database, new_id
from .runtime import AgentRunner, OpenAIModel
from .schemas import (
    AgentCreate,
    AgentOut,
    AgentUpdate,
    ApprovalDecision,
    ErrorBody,
    ErrorResponse,
    MessageOut,
    RoutineCreate,
    RunOut,
    RunRequest,
    SkillAssign,
    SkillDraft,
    SkillOut,
    ThreadSnapshot,
    UserOut,
)
from .tools import SandboxManager


logger = logging.getLogger("meta_workers")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")


def log_event(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, default=str))


def fail(status: int, code: str, message: str, retryable: bool = False) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=ErrorResponse(error=ErrorBody(code=code, message=message, retryable=retryable)).model_dump(),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = getattr(app.state, "settings", Settings.from_env())
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.database_path, default_model=settings.default_model)
    await db.migrate()
    await db.execute(
        "UPDATE runs SET status = 'unknown', error = 'Application restarted during execution', updated_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP WHERE status = 'running'"
    )
    sandbox = SandboxManager(settings)
    model = OpenAIModel(settings)
    app.state.settings = settings
    app.state.db = db
    app.state.sandbox = sandbox
    app.state.runner = AgentRunner(settings, db, model, sandbox)
    app.state.run_tasks = {}
    app.state.maintenance_stop = asyncio.Event()
    app.state.maintenance = asyncio.create_task(maintenance_loop(app))
    for row in await db.fetchall("SELECT id FROM runs WHERE status = 'queued'"):
        schedule_run(app, row["id"])
    yield
    app.state.maintenance_stop.set()
    await asyncio.gather(app.state.maintenance, return_exceptions=True)
    for task in app.state.run_tasks.values():
        task.cancel()
    await asyncio.gather(*app.state.run_tasks.values(), return_exceptions=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Meta Workers", version="0.1.0", lifespan=lifespan)
    if settings:
        app.state.settings = settings

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        started = time.perf_counter()
        request_id = request.headers.get("x-request-id", new_id("request"))[:100]
        response = await call_next(request)
        response.headers.update(
            {
                "X-Request-ID": request_id,
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "strict-origin-when-cross-origin",
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'",
            }
        )
        log_event(
            "http.request",
            request_id=request_id,
            route=request.url.path,
            method=request.method,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1_000, 1),
        )
        return response

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, error: HTTPException):
        if isinstance(error.detail, dict) and "error" in error.detail:
            return JSONResponse(error.detail, status_code=error.status_code)
        return JSONResponse(
            ErrorResponse(error=ErrorBody(code="HTTP_ERROR", message=str(error.detail))).model_dump(),
            status_code=error.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, error: RequestValidationError):
        return JSONResponse(
            ErrorResponse(
                error=ErrorBody(
                    code="VALIDATION_ERROR", message="Request validation failed", details={"errors": error.errors()}
                )
            ).model_dump(),
            status_code=422,
        )

    register_routes(app)
    return app


def register_routes(app: FastAPI) -> None:
    @app.get("/healthz")
    async def health(request: Request):
        db_ready = bool(await request.app.state.db.fetchone("SELECT 1 AS ok"))
        docker_ready = await request.app.state.sandbox.healthy()
        configured = bool(request.app.state.settings.openai_api_key)
        return {
            "status": "ok" if db_ready else "degraded",
            "database": db_ready,
            "docker": docker_ready,
            "model_configured": configured,
        }

    @app.get("/api/users", response_model=list[UserOut])
    async def users(request: Request):
        return await request.app.state.db.fetchall("SELECT id, name FROM users ORDER BY name")

    @app.get("/api/users/{user_id}/agents", response_model=list[AgentOut])
    async def agents(user_id: str, request: Request):
        await require_user(request.app.state.db, user_id)
        return await request.app.state.db.fetchall(
            "SELECT id, user_id, name, instructions, model, permission_mode, kind FROM agents WHERE user_id = ? ORDER BY created_at",
            (user_id,),
        )

    @app.post("/api/users/{user_id}/agents", response_model=AgentOut, status_code=201)
    async def create_agent(user_id: str, body: AgentCreate, request: Request):
        await require_user(request.app.state.db, user_id)
        model = body.model or request.app.state.settings.default_model
        if model not in request.app.state.settings.allowed_models:
            raise fail(422, "MODEL_NOT_ALLOWED", "Model is not in the server allowlist")
        agent_id, thread_id = new_id("agent"), new_id("thread")
        connection = await request.app.state.db.connect()
        try:
            await connection.execute("BEGIN IMMEDIATE")
            await connection.execute(
                "INSERT INTO agents(id, user_id, name, instructions, model, permission_mode) VALUES (?, ?, ?, ?, ?, ?)",
                (agent_id, user_id, body.name, body.instructions, model, body.permission_mode),
            )
            await connection.execute(
                "INSERT INTO threads(id, user_id, agent_id) VALUES (?, ?, ?)",
                (thread_id, user_id, agent_id),
            )
            await connection.commit()
        except Exception as error:
            await connection.rollback()
            if "UNIQUE" in str(error):
                raise fail(409, "AGENT_NAME_EXISTS", "An agent with that name already exists") from error
            raise
        finally:
            await connection.close()
        return await get_agent(request.app.state.db, user_id, agent_id)

    @app.patch("/api/users/{user_id}/agents/{agent_id}", response_model=AgentOut)
    async def update_agent(user_id: str, agent_id: str, body: AgentUpdate, request: Request):
        current = await get_agent(request.app.state.db, user_id, agent_id)
        values = body.model_dump(exclude_none=True)
        if "model" in values and values["model"] not in request.app.state.settings.allowed_models:
            raise fail(422, "MODEL_NOT_ALLOWED", "Model is not in the server allowlist")
        if values:
            assignments = ", ".join(f"{field} = ?" for field in values)
            await request.app.state.db.execute(
                f"UPDATE agents SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
                (*values.values(), agent_id, user_id),
            )
        return await get_agent(request.app.state.db, user_id, agent_id) or current

    @app.get("/api/users/{user_id}/agents/{agent_id}/thread", response_model=ThreadSnapshot)
    async def thread(user_id: str, agent_id: str, request: Request):
        await get_agent(request.app.state.db, user_id, agent_id)
        thread_row = await request.app.state.db.fetchone(
            "SELECT id FROM threads WHERE user_id = ? AND agent_id = ?", (user_id, agent_id)
        )
        messages = await request.app.state.db.fetchall(
            "SELECT id, role, content, seq, created_at FROM messages WHERE user_id = ? AND thread_id = ? ORDER BY seq DESC LIMIT 100",
            (user_id, thread_row["id"]),
        )
        messages.reverse()
        active = await request.app.state.db.fetchone(
            "SELECT id, agent_id, thread_id, trigger, status, error, created_at FROM runs WHERE user_id = ? AND thread_id = ? AND status IN ('queued', 'running', 'waiting_approval') ORDER BY created_at DESC LIMIT 1",
            (user_id, thread_row["id"]),
        )
        cursor = await request.app.state.db.fetchone(
            "SELECT COALESCE(MAX(seq), 0) AS cursor FROM run_events WHERE thread_id = ?", (thread_row["id"],)
        )
        pending = None
        if active and active["status"] == "waiting_approval":
            call = await request.app.state.db.fetchone(
                "SELECT id, name, risk, arguments_json FROM tool_calls WHERE run_id = ? AND status = 'waiting' ORDER BY created_at LIMIT 1",
                (active["id"],),
            )
            if call:
                pending = {
                    "id": call["id"], "tool": call["name"], "risk": call["risk"],
                    "arguments": json.loads(call["arguments_json"]),
                }
        return ThreadSnapshot(
            thread_id=thread_row["id"],
            messages=[MessageOut.model_validate(item) for item in messages],
            active_run=RunOut.model_validate(active) if active else None,
            pending_approval=pending,
            cursor=cursor["cursor"],
        )

    @app.post("/api/users/{user_id}/agents/{agent_id}/runs", response_model=RunOut, status_code=202)
    async def create_run(user_id: str, agent_id: str, body: RunRequest, request: Request):
        run = await create_run_record(request.app, user_id, agent_id, body.prompt, body.client_nonce, "manual")
        if run["status"] == "queued":
            schedule_run(request.app, run["id"])
        return run

    @app.post("/api/users/{user_id}/runs/{run_id}/stop", response_model=RunOut)
    async def stop_run(user_id: str, run_id: str, request: Request):
        run = await get_run(request.app.state.db, user_id, run_id)
        if run["status"] in {"queued", "running", "waiting_approval"}:
            await request.app.state.db.execute(
                "UPDATE runs SET status = 'stopped', updated_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (run_id,),
            )
            task = request.app.state.run_tasks.get(run_id)
            if task:
                task.cancel()
            await request.app.state.db.insert_event(user_id, run_id, run["thread_id"], "run.stopped", {})
        return await get_run(request.app.state.db, user_id, run_id)

    @app.post("/api/users/{user_id}/runs/{run_id}/approvals/{approval_id}", response_model=RunOut)
    async def decide_approval(
        user_id: str, run_id: str, approval_id: str, body: ApprovalDecision, request: Request
    ):
        run = await get_run(request.app.state.db, user_id, run_id)
        call = await request.app.state.db.fetchone(
            "SELECT * FROM tool_calls WHERE id = ? AND run_id = ? AND user_id = ? AND status = 'waiting'",
            (approval_id, run_id, user_id),
        )
        if not call:
            raise fail(409, "APPROVAL_EXPIRED", "This approval is no longer pending")
        if body.decision == "approve":
            await request.app.state.db.execute(
                "UPDATE tool_calls SET status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (approval_id,),
            )
        else:
            await request.app.state.db.execute(
                "UPDATE tool_calls SET status = 'denied', result_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps({"error": "Denied by user"}), approval_id),
            )
            await insert_tool_denial(request.app.state.db, run, approval_id)
        await request.app.state.db.execute(
            "UPDATE runs SET status = 'running', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (run_id,)
        )
        await request.app.state.db.insert_event(
            user_id, run_id, run["thread_id"], "approval.resolved", {"approval_id": approval_id, "decision": body.decision}
        )
        schedule_run(request.app, run_id)
        return await get_run(request.app.state.db, user_id, run_id)

    @app.get("/api/users/{user_id}/threads/{thread_id}/events")
    async def events(
        user_id: str,
        thread_id: str,
        request: Request,
        after: int = Query(default=0, ge=0),
    ):
        thread_row = await request.app.state.db.fetchone(
            "SELECT id FROM threads WHERE id = ? AND user_id = ?", (thread_id, user_id)
        )
        if not thread_row:
            raise fail(404, "NOT_FOUND", "Thread not found")
        header_cursor = request.headers.get("last-event-id")
        cursor = max(after, int(header_cursor)) if header_cursor and header_cursor.isdigit() else after

        async def stream():
            nonlocal cursor
            # ponytail: 250ms SQLite polling is enough for one node; use broker fanout when multi-instance.
            while not await request.is_disconnected():
                rows = await request.app.state.db.fetchall(
                    "SELECT seq, run_id, kind, payload_json FROM run_events WHERE user_id = ? AND thread_id = ? AND seq > ? ORDER BY seq LIMIT 100",
                    (user_id, thread_id, cursor),
                )
                for row in rows:
                    cursor = row["seq"]
                    yield ServerSentEvent(
                        id=str(cursor),
                        event=row["kind"],
                        data={"seq": cursor, "run_id": row["run_id"], "kind": row["kind"], "payload": json.loads(row["payload_json"])},
                    )
                await asyncio.sleep(0.25)

        return EventSourceResponse(stream())

    @app.get("/api/users/{user_id}/activity", response_model=list[RunOut])
    async def activity(user_id: str, request: Request, limit: int = Query(default=30, ge=1, le=100)):
        await require_user(request.app.state.db, user_id)
        return await request.app.state.db.fetchall(
            "SELECT id, agent_id, thread_id, trigger, status, error, created_at FROM runs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )

    @app.get("/api/users/{user_id}/artifacts")
    async def artifacts(user_id: str, request: Request):
        await require_user(request.app.state.db, user_id)
        return await request.app.state.db.fetchall(
            "SELECT id, run_id, name, media_type, pinned, created_at FROM artifacts WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )

    @app.get("/api/users/{user_id}/artifacts/{artifact_id}")
    async def artifact(user_id: str, artifact_id: str, request: Request):
        row = await request.app.state.db.fetchone(
            "SELECT name, media_type, path FROM artifacts WHERE id = ? AND user_id = ?", (artifact_id, user_id)
        )
        if not row or not Path(row["path"]).is_file():
            raise fail(404, "NOT_FOUND", "Artifact not found")
        return FileResponse(row["path"], media_type=row["media_type"], filename=row["name"])

    @app.get("/api/users/{user_id}/agents/{agent_id}/memories")
    async def memories(user_id: str, agent_id: str, request: Request):
        await get_agent(request.app.state.db, user_id, agent_id)
        return await request.app.state.db.fetchall(
            "SELECT id, content, created_at, updated_at FROM memories WHERE user_id = ? AND agent_id = ? ORDER BY updated_at DESC",
            (user_id, agent_id),
        )

    @app.delete("/api/users/{user_id}/memories/{memory_id}", status_code=204)
    async def delete_memory(user_id: str, memory_id: str, request: Request):
        connection = await request.app.state.db.connect()
        try:
            await connection.execute("BEGIN IMMEDIATE")
            await connection.execute("DELETE FROM memory_fts WHERE memory_id = ? AND user_id = ?", (memory_id, user_id))
            cursor = await connection.execute("DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id))
            await connection.commit()
            if cursor.rowcount == 0:
                raise fail(404, "NOT_FOUND", "Memory not found")
        finally:
            await connection.close()

    @app.get("/api/users/{user_id}/agents/{agent_id}/routines")
    async def routines(user_id: str, agent_id: str, request: Request):
        await get_agent(request.app.state.db, user_id, agent_id)
        return await request.app.state.db.fetchall(
            "SELECT * FROM routines WHERE user_id = ? AND agent_id = ? ORDER BY created_at", (user_id, agent_id)
        )

    @app.post("/api/users/{user_id}/agents/{agent_id}/routines", status_code=201)
    async def create_routine(user_id: str, agent_id: str, body: RoutineCreate, request: Request):
        await get_agent(request.app.state.db, user_id, agent_id)
        try:
            zone = ZoneInfo(body.timezone)
            next_at = croniter(body.cron, datetime.now(zone)).get_next(datetime).astimezone(UTC).isoformat()
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise fail(422, "INVALID_SCHEDULE", "Cron expression or timezone is invalid") from error
        routine_id = new_id("routine")
        await request.app.state.db.execute(
            "INSERT INTO routines(id, user_id, agent_id, name, prompt, cron, timezone, next_run_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (routine_id, user_id, agent_id, body.name, body.prompt, body.cron, body.timezone, next_at),
        )
        return await request.app.state.db.fetchone("SELECT * FROM routines WHERE id = ?", (routine_id,))

    register_skill_routes(app)


def register_skill_routes(app: FastAPI) -> None:
    @app.get("/api/users/{user_id}/skills", response_model=list[SkillOut])
    async def skills(user_id: str, request: Request):
        await require_user(request.app.state.db, user_id)
        return await skill_rows(request.app.state.db, "s.user_id = ?", (user_id,))

    @app.post("/api/users/{user_id}/skills", response_model=SkillOut, status_code=201)
    async def create_skill(user_id: str, body: SkillDraft, request: Request):
        await require_user(request.app.state.db, user_id)
        skill_id, version_id = new_id("skill"), new_id("skillver")
        connection = await request.app.state.db.connect()
        try:
            await connection.execute("BEGIN IMMEDIATE")
            await connection.execute(
                "INSERT INTO skills(id, user_id, name, status, current_version_id) VALUES (?, ?, ?, 'draft', ?)",
                (skill_id, user_id, body.name, version_id),
            )
            await connection.execute(
                "INSERT INTO skill_versions(id, skill_id, version, description, instructions) VALUES (?, ?, 1, ?, ?)",
                (version_id, skill_id, body.description, body.instructions),
            )
            await connection.commit()
        except Exception as error:
            await connection.rollback()
            if "UNIQUE" in str(error):
                raise fail(409, "SKILL_NAME_EXISTS", "A skill with that name already exists") from error
            raise
        finally:
            await connection.close()
        return (await skill_rows(request.app.state.db, "s.id = ? AND s.user_id = ?", (skill_id, user_id)))[0]

    @app.post("/api/users/{user_id}/skills/{skill_id}/activate", response_model=SkillOut)
    async def activate_skill(user_id: str, skill_id: str, request: Request):
        await require_skill(request.app.state.db, user_id, skill_id)
        await request.app.state.db.execute(
            "UPDATE skills SET status = 'active', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
            (skill_id, user_id),
        )
        return (await skill_rows(request.app.state.db, "s.id = ? AND s.user_id = ?", (skill_id, user_id)))[0]

    @app.post("/api/users/{user_id}/skills/{skill_id}/assign", status_code=204)
    async def assign_skill(user_id: str, skill_id: str, body: SkillAssign, request: Request):
        skill = await require_skill(request.app.state.db, user_id, skill_id)
        if skill["status"] != "active":
            raise fail(409, "SKILL_NOT_ACTIVE", "Activate the skill before assigning it")
        await get_agent(request.app.state.db, user_id, body.agent_id)
        await request.app.state.db.execute(
            "INSERT OR IGNORE INTO agent_skills(agent_id, skill_id) VALUES (?, ?)", (body.agent_id, skill_id)
        )

    @app.post("/api/users/{user_id}/skills/{skill_id}/publish", response_model=SkillOut)
    async def publish_skill(user_id: str, skill_id: str, request: Request):
        skill = await require_skill(request.app.state.db, user_id, skill_id)
        if skill["status"] != "active":
            raise fail(409, "SKILL_NOT_ACTIVE", "Activate the skill before publishing it")
        await request.app.state.db.execute(
            "UPDATE skill_versions SET published_at = COALESCE(published_at, CURRENT_TIMESTAMP) WHERE id = ?",
            (skill["current_version_id"],),
        )
        return (await skill_rows(request.app.state.db, "s.id = ? AND s.user_id = ?", (skill_id, user_id)))[0]

    @app.get("/api/catalog/skills", response_model=list[SkillOut])
    async def catalog(request: Request):
        return await skill_rows(request.app.state.db, "v.published_at IS NOT NULL", ())

    @app.post("/api/users/{user_id}/catalog/{version_id}/install", response_model=SkillOut, status_code=201)
    async def install_skill(user_id: str, version_id: str, request: Request):
        await require_user(request.app.state.db, user_id)
        source = await request.app.state.db.fetchone(
            """
            SELECT s.name, v.description, v.instructions
            FROM skill_versions v JOIN skills s ON s.id = v.skill_id
            WHERE v.id = ? AND v.published_at IS NOT NULL
            """,
            (version_id,),
        )
        if not source:
            raise fail(404, "NOT_FOUND", "Published skill version not found")
        name = source["name"]
        suffix = 2
        while await request.app.state.db.fetchone("SELECT 1 FROM skills WHERE user_id = ? AND name = ?", (user_id, name)):
            name = f"{source['name']}-{suffix}"
            suffix += 1
        skill_id, copy_version_id = new_id("skill"), new_id("skillver")
        connection = await request.app.state.db.connect()
        try:
            await connection.execute("BEGIN IMMEDIATE")
            await connection.execute(
                "INSERT INTO skills(id, user_id, name, status, current_version_id, source_version_id) VALUES (?, ?, ?, 'active', ?, ?)",
                (skill_id, user_id, name, copy_version_id, version_id),
            )
            await connection.execute(
                "INSERT INTO skill_versions(id, skill_id, version, description, instructions) VALUES (?, ?, 1, ?, ?)",
                (copy_version_id, skill_id, source["description"], source["instructions"]),
            )
            await connection.commit()
        finally:
            await connection.close()
        return (await skill_rows(request.app.state.db, "s.id = ? AND s.user_id = ?", (skill_id, user_id)))[0]


async def require_user(db: Database, user_id: str) -> dict[str, Any]:
    row = await db.fetchone("SELECT id, name FROM users WHERE id = ?", (user_id,))
    if not row:
        raise fail(404, "NOT_FOUND", "User not found")
    return row


async def get_agent(db: Database, user_id: str, agent_id: str) -> dict[str, Any]:
    row = await db.fetchone(
        "SELECT id, user_id, name, instructions, model, permission_mode, kind FROM agents WHERE id = ? AND user_id = ?",
        (agent_id, user_id),
    )
    if not row:
        raise fail(404, "NOT_FOUND", "Agent not found")
    return row


async def get_run(db: Database, user_id: str, run_id: str) -> dict[str, Any]:
    row = await db.fetchone(
        "SELECT id, user_id, agent_id, thread_id, trigger, status, error, created_at FROM runs WHERE id = ? AND user_id = ?",
        (run_id, user_id),
    )
    if not row:
        raise fail(404, "NOT_FOUND", "Run not found")
    return row


async def create_run_record(
    app: FastAPI, user_id: str, agent_id: str, prompt: str, client_nonce: str, trigger: str
) -> dict[str, Any]:
    await get_agent(app.state.db, user_id, agent_id)
    thread = await app.state.db.fetchone(
        "SELECT id FROM threads WHERE user_id = ? AND agent_id = ?", (user_id, agent_id)
    )
    existing = await app.state.db.fetchone(
        "SELECT run_id FROM messages WHERE thread_id = ? AND client_nonce = ?", (thread["id"], client_nonce)
    )
    if existing:
        return await get_run(app.state.db, user_id, existing["run_id"])
    run_id, message_id = new_id("run"), new_id("message")
    connection = await app.state.db.connect()
    try:
        await connection.execute("BEGIN IMMEDIATE")
        active = await connection.execute(
            "SELECT 1 FROM runs WHERE thread_id = ? AND status IN ('queued', 'running', 'waiting_approval')",
            (thread["id"],),
        )
        if await active.fetchone():
            raise fail(409, "RUN_ACTIVE", "This agent already has an active run")
        cursor = await connection.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE thread_id = ?", (thread["id"],)
        )
        seq = (await cursor.fetchone())[0]
        await connection.execute(
            "INSERT INTO runs(id, user_id, agent_id, thread_id, trigger, status) VALUES (?, ?, ?, ?, ?, 'queued')",
            (run_id, user_id, agent_id, thread["id"], trigger),
        )
        await connection.execute(
            "INSERT INTO messages(id, user_id, thread_id, run_id, seq, role, content, client_nonce) VALUES (?, ?, ?, ?, ?, 'user', ?, ?)",
            (message_id, user_id, thread["id"], run_id, seq, prompt, client_nonce),
        )
        await connection.commit()
    except Exception:
        await connection.rollback()
        raise
    finally:
        await connection.close()
    return await get_run(app.state.db, user_id, run_id)


def schedule_run(app: FastAPI, run_id: str) -> None:
    current = app.state.run_tasks.get(run_id)
    if current and not current.done():
        return

    async def execute():
        try:
            await app.state.runner.run(run_id)
        finally:
            app.state.run_tasks.pop(run_id, None)

    app.state.run_tasks[run_id] = asyncio.create_task(execute())


async def insert_tool_denial(db: Database, run: dict[str, Any], tool_call_id: str) -> None:
    connection = await db.connect()
    try:
        await connection.execute("BEGIN IMMEDIATE")
        cursor = await connection.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE thread_id = ?", (run["thread_id"],)
        )
        seq = (await cursor.fetchone())[0]
        await connection.execute(
            "INSERT INTO messages(id, user_id, thread_id, run_id, seq, role, content, tool_call_id) VALUES (?, ?, ?, ?, ?, 'tool', ?, ?)",
            (new_id("message"), run["user_id"], run["thread_id"], run["id"], seq, '{"error":"Denied by user"}', tool_call_id),
        )
        await connection.commit()
    finally:
        await connection.close()


async def maintenance_loop(app: FastAPI) -> None:
    while not app.state.maintenance_stop.is_set():
        try:
            await run_due_routines(app)
            await cleanup(app)
        except Exception as error:
            log_event("maintenance.failed", error=str(error)[:500])
        try:
            await asyncio.wait_for(app.state.maintenance_stop.wait(), 30)
        except TimeoutError:
            pass


async def run_due_routines(app: FastAPI) -> None:
    now = datetime.now(UTC)
    rows = await app.state.db.fetchall(
        "SELECT * FROM routines WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= ?",
        (now.isoformat(),),
    )
    for row in rows:
        scheduled_for = row["next_run_at"]
        try:
            await create_run_record(
                app,
                row["user_id"],
                row["agent_id"],
                row["prompt"],
                f"routine:{row['id']}:{scheduled_for}",
                "routine",
            )
            run = await app.state.db.fetchone(
                "SELECT run_id FROM messages WHERE client_nonce = ?", (f"routine:{row['id']}:{scheduled_for}",)
            )
            if run:
                schedule_run(app, run["run_id"])
        except HTTPException as error:
            if error.status_code != 409:
                raise
        zone = ZoneInfo(row["timezone"])
        next_at = croniter(row["cron"], datetime.now(zone)).get_next(datetime).astimezone(UTC).isoformat()
        await app.state.db.execute(
            "UPDATE routines SET last_scheduled_for = ?, next_run_at = ? WHERE id = ?",
            (scheduled_for, next_at, row["id"]),
        )


async def cleanup(app: FastAPI) -> None:
    cutoff = (datetime.now(UTC) - timedelta(days=app.state.settings.artifact_ttl_days)).isoformat()
    rows = await app.state.db.fetchall(
        "SELECT id, path FROM artifacts WHERE pinned = 0 AND created_at < ?", (cutoff,)
    )
    for row in rows:
        path = Path(row["path"])
        if path.is_file() and app.state.settings.data_dir in path.parents:
            path.unlink()
        await app.state.db.execute("DELETE FROM artifacts WHERE id = ?", (row["id"],))
    await app.state.db.execute("DELETE FROM run_events WHERE created_at < ?", (cutoff,))


async def require_skill(db: Database, user_id: str, skill_id: str) -> dict[str, Any]:
    row = await db.fetchone("SELECT * FROM skills WHERE id = ? AND user_id = ?", (skill_id, user_id))
    if not row:
        raise fail(404, "NOT_FOUND", "Skill not found")
    return row


async def skill_rows(db: Database, where: str, values: tuple[Any, ...]) -> list[dict[str, Any]]:
    return await db.fetchall(
        f"""
        SELECT s.id, s.user_id, s.current_version_id, s.name, s.status,
               v.description, v.instructions, v.version, v.published_at
        FROM skills s JOIN skill_versions v ON v.id = s.current_version_id
        WHERE {where}
        ORDER BY s.name
        """,
        values,
    )


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("meta_workers.main:app", host="127.0.0.1", port=8000, reload=False)
