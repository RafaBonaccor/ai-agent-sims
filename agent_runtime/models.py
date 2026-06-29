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
    provider: str = Field(default="simulated", pattern=r"^(simulated|openai-compatible)$")
    model: str = Field(default="native-simulator", min_length=1, max_length=160)
    base_url: str = Field(default="", max_length=500)
    api_key_env: str = Field(default="", pattern=r"^$|^[A-Z][A-Z0-9_]{1,79}$")
    temperature: float = Field(default=0.2, ge=0, le=2)


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


class TaskRecord(TaskCreate):
    id: str = Field(default_factory=lambda: f"task-{uuid4().hex[:12]}")
    state: TaskState = TaskState.CREATED
    assigned_agent_id: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


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
