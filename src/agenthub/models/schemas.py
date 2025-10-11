"""Pydantic schemas for AgentHub."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    """Tool specification with schema and metadata."""

    name: str
    version: str = "1.0.0"
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    timeout_s: float = 30.0
    requires_llm: bool = False


class ToolCall(BaseModel):
    """A single tool invocation."""

    tool: str
    args: Dict[str, Any]
    step_id: Optional[str] = None


class Plan(BaseModel):
    """Execution plan with tool calls and rationale."""

    steps: List[ToolCall]
    rationale: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    estimated_tokens: Optional[int] = None


class ToolResult(BaseModel):
    """Result of a tool execution."""

    tool: str
    ok: bool
    output: Any
    error: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float
    cached: bool = False
    step_id: Optional[str] = None


class ExecutionResult(BaseModel):
    """Result of executing a complete plan."""

    session_id: str
    steps: List[ToolResult]
    total_tokens: int
    total_cost_usd: float
    duration_ms: float
    success: bool
    final_output: Optional[Any] = None


class Session(BaseModel):
    """User session with context and history."""

    id: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ttl_s: int = 86400
    context: Dict[str, Any] = Field(default_factory=dict)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    total_tokens: int = 0
    total_cost_usd: float = 0.0


class AuditLog(BaseModel):
    """Immutable audit log entry."""

    ts: datetime = Field(default_factory=datetime.utcnow)
    api_key_id: str
    actor_role: str
    route: str
    method: str
    status: int
    session_id: Optional[str] = None
    masked_input_hash: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    ip: str
    trace_id: str
    duration_ms: float = 0.0


# Request/Response models for API

class CreateSessionRequest(BaseModel):
    """Request to create a new session."""

    context: Optional[Dict[str, Any]] = None
    ttl_s: Optional[int] = None


class CreateSessionResponse(BaseModel):
    """Response with session ID."""

    session_id: str
    created_at: datetime


class PlanRequest(BaseModel):
    """Request to create an execution plan."""

    session_id: str
    goal: str
    context: Optional[Dict[str, Any]] = None
    tools_allowed: Optional[List[str]] = None


class ExecuteRequest(BaseModel):
    """Request to execute a plan."""

    session_id: str
    plan: Plan
    idempotency_key: Optional[str] = None


class APIKeyCreate(BaseModel):
    """Request to create an API key."""

    role: str = Field(..., pattern="^(admin|developer|client)$")
    name: Optional[str] = None


class APIKeyResponse(BaseModel):
    """Response with API key details."""

    key_id: str
    api_key: str
    role: str
    created_at: datetime

