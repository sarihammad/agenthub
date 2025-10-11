"""Kafka event payloads."""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """Audit event for Kafka."""

    event_type: str = "audit"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
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


class AgentEvent(BaseModel):
    """Agent execution event for Kafka."""

    event_type: str = "agent_event"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    session_id: str
    step_id: Optional[str] = None
    tool: Optional[str] = None
    action: str  # plan_created, step_started, step_completed, execution_finished
    data: Dict[str, Any] = Field(default_factory=dict)
    trace_id: str


class DeadLetterEvent(BaseModel):
    """Dead letter queue event."""

    event_type: str = "dead_letter"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    original_topic: str
    original_payload: Dict[str, Any]
    error: str
    retry_count: int = 0

