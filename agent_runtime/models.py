from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentState(str, Enum):
    IDLE = "idle"
    RECEIVING = "receiving"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING = "waiting"
    VERIFYING = "verifying"
    BLOCKED = "blocked"
    FAILED = "failed"
    STOPPED = "stopped"


class TaskState(str, Enum):
    CREATED = "created"
    ANNOUNCED = "announced"
    AWARDED = "awarded"
    ACCEPTED = "accepted"
    RUNNING = "running"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RuntimeLimits(BaseModel):
    max_iterations: int = Field(default=20, ge=1, le=200)
    timeout_seconds: int = Field(default=300, ge=10, le=86_400)
    max_parallel_tasks: int = Field(default=1, ge=1, le=16)


class ApprovalPolicy(BaseModel):
    required_for: list[str] = Field(default_factory=lambda: ["external-write", "destructive"])


class ModelSettings(BaseModel):
    provider: str = Field(
        default="simulated",
        pattern=r"^(simulated|openai|openai-compatible|anthropic|gemini|ollama)$",
    )
    model: str = Field(default="native-simulator", min_length=1, max_length=160)
    base_url: str = Field(default="", max_length=500)
    api_key_env: str = Field(default="", pattern=r"^$|^[A-Z][A-Z0-9_]{1,79}$")
    api_key_scope: str = Field(default="project", pattern=r"^(project|agent)$")
    temperature: float = Field(default=0.2, ge=0, le=2)


class SystemUiSettings(BaseModel):
    theme: str = Field(default="dark", pattern=r"^(dark|light)$")
    auto_agents: bool = True
    simulation_speed: int = Field(default=1, ge=1, le=4)


class DiagnosticsSettings(BaseModel):
    discord_error_notifications: bool = False
    discord_webhook_url: str = Field(default="", max_length=2000)


class DiscordBotSettings(BaseModel):
    enabled: bool = False
    command_prefix: str = Field(default="!", min_length=1, max_length=8)
    default_agent_id: str = Field(default="", max_length=80)
    allowed_guild_ids: list[int] = Field(default_factory=list)
    allowed_channel_ids: list[int] = Field(default_factory=list)
    message_content: bool = False
    sync_commands: bool = True


class SystemSettings(BaseModel):
    configured: bool = False
    model: ModelSettings = Field(default_factory=ModelSettings)
    ui: SystemUiSettings = Field(default_factory=SystemUiSettings)
    diagnostics: DiagnosticsSettings = Field(default_factory=DiagnosticsSettings)
    discord: DiscordBotSettings = Field(default_factory=DiscordBotSettings)


class AgentDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,47}$")
    name: str = Field(min_length=2, max_length=80)
    role: str = Field(min_length=2, max_length=48)
    color: str = Field(default="#5ee7f2", pattern=r"^#[0-9a-fA-F]{6}$")
    capabilities: list[str] = Field(default_factory=list)
    toolsets: list[str] = Field(default_factory=list)
    protocols: list[str] = Field(default_factory=lambda: ["task-contract", "agent-lifecycle"])
    instructions: str = Field(default="", max_length=8_000)
    model: ModelSettings = Field(default_factory=ModelSettings)
    model_provider: Optional[str] = Field(default=None, exclude=True)
    memory_scope: str = "agent"
    limits: RuntimeLimits = Field(default_factory=RuntimeLimits)
    approvals: ApprovalPolicy = Field(default_factory=ApprovalPolicy)

    @field_validator("capabilities", "toolsets", "protocols")
    @classmethod
    def normalize_unique_values(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().lower() for value in values if value.strip()]
        return list(dict.fromkeys(normalized))


class AgentSnapshot(AgentDefinition):
    state: AgentState = AgentState.IDLE
    active_task_id: Optional[str] = None
    load: float = Field(default=0, ge=0, le=1)
    created_at: datetime = Field(default_factory=utc_now)


class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=4_000)
    capability: Optional[str] = Field(default=None, max_length=64)
    priority: int = Field(default=2, ge=1, le=5)
    requested_agent_id: Optional[str] = None
    source_agent_id: Optional[str] = None
    consult_agent_id: Optional[str] = None
    consult_agent_ids: list[str] = Field(default_factory=list)
    consultation_notes: str = Field(default="", max_length=12_000)
    clarification_question: str = Field(default="", max_length=2_000)
    route_reason: str = Field(default="", max_length=500)
    route_language: str = Field(default="", max_length=32)
    route_mode: str = Field(default="", max_length=32)
    discussion_log: list[dict[str, Any]] = Field(default_factory=list)
    channel: str = Field(default="task", pattern=r"^(task|chat)$")


class TaskRecord(TaskCreate):
    id: str = Field(default_factory=lambda: f"task-{uuid4().hex[:12]}")
    state: TaskState = TaskState.CREATED
    assigned_agent_id: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AgentChatMessage(BaseModel):
    id: str
    task_id: str
    role: str = Field(pattern=r"^(user|assistant|system)$")
    content: str
    sources: list[dict[str, str]] = Field(default_factory=list)
    created_at: datetime


class ProjectJobPresetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=100)
    project_id: str = Field(min_length=1, max_length=80)
    action: str = Field(min_length=1, max_length=100)
    parameters: dict[str, Any] = Field(default_factory=dict)


class ProjectJobPreset(ProjectJobPresetCreate):
    id: str = Field(default_factory=lambda: f"preset-{uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=utc_now)


class ProjectScheduleMode(str, Enum):
    IMMEDIATE = "immediate"
    AT = "at"
    CRON = "cron"


class ProjectRepeatMode(str, Enum):
    ONCE = "once"
    DAILY = "daily"
    WEEKDAYS = "weekdays"


class MessageEnvelope(BaseModel):
    id: str = Field(default_factory=lambda: f"msg-{uuid4().hex[:12]}")
    type: str
    protocol: str
    sender: str
    recipient: str
    task_id: Optional[str] = None
    correlation_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=2, ge=1, le=5)
    created_at: datetime = Field(default_factory=utc_now)


class RuntimeEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"evt-{uuid4().hex[:14]}")
    type: str
    entity_id: Optional[str] = None
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class MemoryUpdate(BaseModel):
    content: str = Field(default="", max_length=8_000)


class MemoryRecord(MemoryUpdate):
    agent_id: str
    updated_at: datetime = Field(default_factory=utc_now)


class WikiUpdate(BaseModel):
    content: str = Field(default="", max_length=8_000)


class WikiRecord(WikiUpdate):
    agent_id: str
    updated_at: datetime = Field(default_factory=utc_now)


class WikiProposalRecord(BaseModel):
    name: str
    content: str


class WikiProposalResolveRequest(BaseModel):
    status: str = Field(pattern=r"^(approved|rejected)$")
    reviewer: str = Field(min_length=1, max_length=120)
    reason: str = Field(default="", max_length=2_000)


class WikiPageRecord(BaseModel):
    name: str
    title: str
    updated: str = ""
    kind: str = "page"
    sections: int = 0
    characters: int = 0


class WikiPageContent(BaseModel):
    name: str
    content: str


class WikiSearchResult(BaseModel):
    query: str
    pages: list[dict[str, str]] = Field(default_factory=list)


class WikiMaintenanceResult(BaseModel):
    pages_scanned: int = 0
    pages_updated: int = 0
    duplicate_sections_removed: int = 0
    index_page: str = ""
