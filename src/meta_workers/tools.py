from __future__ import annotations

import asyncio
import io
import ipaddress
import json
import socket
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import docker
from ddgs import DDGS
from playwright.async_api import async_playwright

from .config import Settings
from .db import Database, new_id
from .schemas import DueDiligenceReport, SkillDraft


ToolHandler = Callable[["ToolContext", dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    risk: str
    handler: ToolHandler

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(frozen=True)
class ToolContext:
    settings: Settings
    db: Database
    sandbox: "SandboxManager"
    user_id: str
    agent_id: str
    run_id: str
    thread_id: str


class SandboxManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: docker.DockerClient | None = None

    def client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    async def healthy(self) -> bool:
        try:
            return bool(await asyncio.to_thread(self.client().ping))
        except Exception:
            return False

    async def ensure(self, user_id: str):
        safe_id = user_id.replace("_", "-")
        name = f"meta-workers-{safe_id}"
        client = self.client()
        try:
            container = await asyncio.to_thread(client.containers.get, name)
            if container.status != "running":
                await asyncio.to_thread(container.start)
            return container
        except docker.errors.NotFound:
            return await asyncio.to_thread(
                client.containers.run,
                self.settings.sandbox_image,
                detach=True,
                name=name,
                labels={"meta-workers.user": user_id},
                volumes={f"{name}-data": {"bind": "/workspace", "mode": "rw"}},
                working_dir="/workspace",
                user="10001:10001",
                mem_limit="1g",
                nano_cpus=1_000_000_000,
                pids_limit=256,
                network_disabled=True,
                security_opt=["no-new-privileges"],
                cap_drop=["ALL"],
            )

    async def shell(self, user_id: str, command: str) -> dict[str, Any]:
        if len(command) > 20_000:
            raise ValueError("command is too long")
        container = await self.ensure(user_id)
        result = await asyncio.wait_for(
            asyncio.to_thread(
                container.exec_run,
                ["sh", "-lc", command],
                workdir="/workspace",
                user="10001:10001",
                demux=True,
            ),
            timeout=120,
        )
        stdout, stderr = result.output
        return {
            "exit_code": result.exit_code,
            "stdout": (stdout or b"").decode(errors="replace")[-20_000:],
            "stderr": (stderr or b"").decode(errors="replace")[-20_000:],
        }

    async def read_file(self, user_id: str, path: str) -> bytes:
        relative = safe_workspace_path(path)
        container = await self.ensure(user_id)
        stream, _ = await asyncio.to_thread(container.get_archive, f"/workspace/{relative}")
        archive = io.BytesIO(b"".join(stream))
        with tarfile.open(fileobj=archive) as bundle:
            member = next(item for item in bundle.getmembers() if item.isfile())
            extracted = bundle.extractfile(member)
            if extracted is None:
                raise FileNotFoundError(path)
            return extracted.read(2_000_001)

    async def write_file(self, user_id: str, path: str, content: bytes) -> None:
        if len(content) > 2_000_000:
            raise ValueError("file exceeds 2 MB")
        relative = safe_workspace_path(path)
        container = await self.ensure(user_id)
        parent, name = relative.parent, relative.name
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as bundle:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mtime = int(datetime.now(UTC).timestamp())
            info.uid = 10001
            info.gid = 10001
            bundle.addfile(info, io.BytesIO(content))
        await self.shell(user_id, f"mkdir -p -- {shell_quote(str(parent))}")
        await asyncio.to_thread(container.put_archive, f"/workspace/{parent}", archive.getvalue())


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def safe_workspace_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.name:
        raise ValueError("path must stay inside /workspace")
    return path


async def validate_public_url(value: str) -> str:
    # ponytail: DNS validation has a rebinding TOCTOU; use an egress proxy before hostile multi-tenant use.
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("only public HTTP(S) URLs are allowed")
    addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, parsed.port or 443)
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("private or reserved network destinations are blocked")
    return value


async def shell_tool(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    command = str(arguments.get("command", "")).strip()
    if not command:
        raise ValueError("command is required")
    return await context.sandbox.shell(context.user_id, command)


async def read_file_tool(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    content = await context.sandbox.read_file(context.user_id, str(arguments.get("path", "")))
    if len(content) > 2_000_000:
        raise ValueError("file exceeds 2 MB")
    return {"content": content.decode(errors="replace")}


async def write_file_tool(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    path = str(arguments.get("path", ""))
    content = str(arguments.get("content", "")).encode()
    await context.sandbox.write_file(context.user_id, path, content)
    return {"path": path, "bytes": len(content)}


async def web_search_tool(_: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query", "")).strip()
    if not query or len(query) > 500:
        raise ValueError("query must be 1-500 characters")

    def search() -> list[dict[str, str]]:
        return [
            {"title": item.get("title", ""), "url": item.get("href", ""), "snippet": item.get("body", "")}
            for item in DDGS().text(query, max_results=8)
        ]

    return {"query": query, "results": await asyncio.to_thread(search)}


async def browser_open_tool(_: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    url = await validate_public_url(str(arguments.get("url", "")))
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()

        async def guard(route) -> None:
            try:
                await validate_public_url(route.request.url)
                await route.continue_()
            except (ValueError, OSError):
                await route.abort()

        await page.route("**/*", guard)
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        title = await page.title()
        text = (await page.locator("body").inner_text())[:30_000]
        links = await page.locator("a[href]").evaluate_all(
            "els => els.slice(0, 100).map(a => ({text: (a.textContent || '').trim(), url: a.href}))"
        )
        final_url = page.url
        await browser.close()
    return {"title": title, "url": final_url, "text": text, "links": links}


async def remember_tool(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    content = str(arguments.get("content", "")).strip()
    if not content or len(content) > 2_000:
        raise ValueError("memory must be 1-2000 characters")
    memory_id = new_id("memory")
    connection = await context.db.connect()
    try:
        await connection.execute(
            "INSERT INTO memories(id, user_id, agent_id, content, source_run_id) VALUES (?, ?, ?, ?, ?)",
            (memory_id, context.user_id, context.agent_id, content, context.run_id),
        )
        await connection.execute(
            "INSERT INTO memory_fts(memory_id, user_id, agent_id, content) VALUES (?, ?, ?, ?)",
            (memory_id, context.user_id, context.agent_id, content),
        )
        await connection.commit()
    finally:
        await connection.close()
    return {"id": memory_id, "content": content}


async def load_skill_tool(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    name = str(arguments.get("name", ""))
    row = await context.db.fetchone(
        """
        SELECT s.name, v.description, v.instructions, v.version
        FROM agent_skills a
        JOIN skills s ON s.id = a.skill_id
        JOIN skill_versions v ON v.id = s.current_version_id
        WHERE a.agent_id = ? AND s.user_id = ? AND s.name = ? AND s.status = 'active'
        """,
        (context.agent_id, context.user_id, name),
    )
    if not row:
        raise ValueError("skill is not assigned and active")
    return row


async def save_skill_draft_tool(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    draft = SkillDraft.model_validate(arguments)
    existing = await context.db.fetchone(
        "SELECT id FROM skills WHERE user_id = ? AND name = ?", (context.user_id, draft.name)
    )
    skill_id = existing["id"] if existing else new_id("skill")
    connection = await context.db.connect()
    try:
        await connection.execute("BEGIN IMMEDIATE")
        if not existing:
            await connection.execute(
                "INSERT INTO skills(id, user_id, name, status) VALUES (?, ?, ?, 'draft')",
                (skill_id, context.user_id, draft.name),
            )
            version = 1
        else:
            cursor = await connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM skill_versions WHERE skill_id = ?", (skill_id,)
            )
            version = (await cursor.fetchone())[0]
        version_id = new_id("skillver")
        await connection.execute(
            "INSERT INTO skill_versions(id, skill_id, version, description, instructions) VALUES (?, ?, ?, ?, ?)",
            (version_id, skill_id, version, draft.description, draft.instructions),
        )
        await connection.execute(
            "UPDATE skills SET current_version_id = ?, status = 'draft', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (version_id, skill_id),
        )
        await connection.commit()
    finally:
        await connection.close()
    return {"id": skill_id, "version": version, "status": "draft"}


REPORT_DISCLAIMER = (
    "This public-source research brief is a product demonstration, not identity verification, "
    "regulated KYC, legal advice, or an onboarding decision. Possible matches require human verification."
)


async def publish_report_tool(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    report = DueDiligenceReport.model_validate(arguments)
    artifact_dir = context.settings.data_dir / "artifacts" / context.user_id / context.run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    json_path = artifact_dir / "due-diligence-report.json"
    md_path = artifact_dir / "due-diligence-report.md"
    json_path.write_text(json.dumps({**report.model_dump(mode="json"), "disclaimer": REPORT_DISCLAIMER}, indent=2))
    md_path.write_text(render_report(report))
    artifacts = []
    for path, media_type in ((json_path, "application/json"), (md_path, "text/markdown")):
        artifact_id = new_id("artifact")
        await context.db.execute(
            "INSERT INTO artifacts(id, user_id, run_id, name, media_type, path) VALUES (?, ?, ?, ?, ?, ?)",
            (artifact_id, context.user_id, context.run_id, path.name, media_type, str(path)),
        )
        artifacts.append({"id": artifact_id, "name": path.name, "media_type": media_type})
    return {"artifacts": artifacts, "disclaimer": REPORT_DISCLAIMER}


def render_report(report: DueDiligenceReport) -> str:
    def bullets(values: list[str]) -> str:
        return "\n".join(f"- {value}" for value in values) or "- Not established from public sources."

    risks = "\n".join(
        f"- **{flag.level.upper()} — {flag.category}:** {flag.rationale}"
        + (f" [sources: {', '.join(str(index + 1) for index in flag.source_indexes)}]" if flag.source_indexes else "")
        for flag in report.risk_flags
    ) or "- No supported flags identified."
    sources = "\n".join(
        f"{index + 1}. [{source.claim}]({source.url}) — accessed {source.accessed_at}"
        for index, source in enumerate(report.sources)
    )
    return f"""# Public-Source Due-Diligence Brief: {report.company_name}

**Website:** {report.website or 'Unknown'}
**Jurisdiction:** {report.jurisdiction}

## Summary

{report.summary}

## Ownership and leadership

{bullets(report.ownership_and_leadership)}

## Business and geographies

{bullets(report.business_and_geographies)}

## Risk flags

{risks}

## Unknowns

{bullets(report.unknowns)}

## Next manual checks

{bullets(report.next_manual_checks)}

## Sources

{sources}

> {REPORT_DISCLAIMER}
"""


def tool_registry() -> dict[str, ToolDefinition]:
    object_schema = lambda properties, required: {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    report_schema = DueDiligenceReport.model_json_schema()
    skill_schema = SkillDraft.model_json_schema()
    tools = [
        ToolDefinition("shell", "Run a shell command in the user's isolated workspace.", object_schema({"command": {"type": "string"}}, ["command"]), "execution", shell_tool),
        ToolDefinition("read_file", "Read a UTF-8 file from the isolated workspace.", object_schema({"path": {"type": "string"}}, ["path"]), "read", read_file_tool),
        ToolDefinition("write_file", "Write a UTF-8 file inside the isolated workspace.", object_schema({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]), "write", write_file_tool),
        ToolDefinition("web_search", "Search the public web.", object_schema({"query": {"type": "string"}}, ["query"]), "egress", web_search_tool),
        ToolDefinition("browser_open", "Open and read a public web page with a headless browser.", object_schema({"url": {"type": "string", "format": "uri"}}, ["url"]), "egress", browser_open_tool),
        ToolDefinition("remember", "Save a durable user preference or working convention, never a case fact.", object_schema({"content": {"type": "string"}}, ["content"]), "write", remember_tool),
        ToolDefinition("load_skill", "Load the full instructions for an assigned active skill.", object_schema({"name": {"type": "string"}}, ["name"]), "read", load_skill_tool),
        ToolDefinition("save_skill_draft", "Save an internal skill draft for user review. This cannot activate or publish it.", skill_schema, "write", save_skill_draft_tool),
        ToolDefinition("publish_due_diligence_report", "Validate and publish the final public-source due-diligence brief as JSON and Markdown artifacts.", report_schema, "write", publish_report_tool),
    ]
    return {tool.name: tool for tool in tools}


def needs_approval(mode: str, risk: str) -> bool:
    if mode == "full":
        return False
    if mode == "workspace":
        return risk == "egress"
    return risk != "read"
