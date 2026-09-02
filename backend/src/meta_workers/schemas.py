from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


PermissionMode = Literal["ask", "workspace", "full"]
RunStatus = Literal[
    "queued", "running", "waiting_approval", "succeeded", "failed", "stopped", "unknown"
]


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class UserOut(BaseModel):
    id: str
    name: str


class AgentOut(BaseModel):
    id: str
    user_id: str
    name: str
    instructions: str
    model: str
    permission_mode: PermissionMode
    kind: str


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    instructions: str = Field(min_length=1, max_length=12_000)
    model: str | None = Field(default=None, max_length=160)
    permission_mode: PermissionMode = "ask"


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    instructions: str | None = Field(default=None, min_length=1, max_length=12_000)
    model: str | None = Field(default=None, max_length=160)
    permission_mode: PermissionMode | None = None


class RunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=40_000)
    client_nonce: str = Field(min_length=8, max_length=100)


class RunOut(BaseModel):
    id: str
    agent_id: str
    thread_id: str
    trigger: str
    status: RunStatus
    error: str | None = None
    created_at: str


class MessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant", "tool"]
    content: str
    seq: int
    created_at: str


class ThreadSnapshot(BaseModel):
    thread_id: str
    messages: list[MessageOut]
    active_run: RunOut | None
    pending_approval: dict[str, Any] | None = None
    cursor: int


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "deny"]


class RoutineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=40_000)
    cron: str = Field(min_length=5, max_length=100)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)


class SkillDraft(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=1024)
    instructions: str = Field(min_length=1, max_length=30_000)


class SkillOut(BaseModel):
    id: str
    user_id: str
    current_version_id: str
    name: str
    status: Literal["draft", "active", "archived"]
    description: str
    instructions: str
    version: int
    published_at: str | None = None


class SkillAssign(BaseModel):
    agent_id: str


class CompanySource(BaseModel):
    claim: str = Field(min_length=1, max_length=2_000)
    url: HttpUrl
    accessed_at: str


class RiskFlag(BaseModel):
    category: str = Field(min_length=1, max_length=100)
    level: Literal["low", "medium", "high", "unknown"]
    rationale: str = Field(min_length=1, max_length=4_000)
    source_indexes: list[int] = Field(default_factory=list, max_length=20)


class DueDiligenceReport(BaseModel):
    company_name: str = Field(min_length=1, max_length=300)
    website: HttpUrl | None = None
    jurisdiction: str = Field(default="Unknown", max_length=200)
    summary: str = Field(min_length=1, max_length=6_000)
    ownership_and_leadership: list[str] = Field(default_factory=list, max_length=50)
    business_and_geographies: list[str] = Field(default_factory=list, max_length=50)
    risk_flags: list[RiskFlag] = Field(default_factory=list, max_length=50)
    unknowns: list[str] = Field(default_factory=list, max_length=50)
    next_manual_checks: list[str] = Field(default_factory=list, max_length=50)
    sources: list[CompanySource] = Field(min_length=1, max_length=100)

    @field_validator("ownership_and_leadership", "business_and_geographies", "unknowns", "next_manual_checks")
    @classmethod
    def bound_items(cls, values: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 2_000 for item in values):
            raise ValueError("items must be non-empty and at most 2000 characters")
        return values

    @model_validator(mode="after")
    def source_references_exist(self):
        if any(index < 0 or index >= len(self.sources) for flag in self.risk_flags for index in flag.source_indexes):
            raise ValueError("risk source_indexes must reference an included source")
        return self
