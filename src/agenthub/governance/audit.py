"""Audit logging to Kafka."""

import hashlib
import json
import logging
from typing import Any, Dict, Optional

from kafka import KafkaProducer

from agenthub.config import settings
from agenthub.models.events import AuditEvent

logger = logging.getLogger(__name__)


class AuditLogger:
    """Audit logger that produces to Kafka."""

    def __init__(self) -> None:
        """Initialize audit logger."""
        self._producer: Optional[KafkaProducer] = None

    def _get_producer(self) -> KafkaProducer:
        """Get or create Kafka producer."""
        if self._producer is None:
            self._producer = KafkaProducer(
                bootstrap_servers=settings.kafka_broker,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                retries=3,
            )
        return self._producer

    async def log(
        self,
        api_key_id: str,
        actor_role: str,
        route: str,
        method: str,
        status: int,
        trace_id: str,
        ip: str,
        session_id: Optional[str] = None,
        request_body: Optional[Dict[str, Any]] = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
        duration_ms: float = 0.0,
    ) -> None:
        """Log an audit event.
        
        Args:
            api_key_id: API key ID
            actor_role: User role
            route: Request route
            method: HTTP method
            status: HTTP status code
            trace_id: Trace ID
            ip: Client IP
            session_id: Optional session ID
            request_body: Optional request body (will be masked)
            tokens_in: Tokens consumed (input)
            tokens_out: Tokens generated (output)
            cost_usd: Cost in USD
            duration_ms: Request duration in ms
        """
        from agenthub.governance.masking import mask_sensitive_data

        # Hash the masked input
        masked_input = ""
        if request_body:
            masked_input = json.dumps(mask_sensitive_data(request_body))

        input_hash = hashlib.sha256(masked_input.encode()).hexdigest()[:16]

        event = AuditEvent(
            api_key_id=api_key_id,
            actor_role=actor_role,
            route=route,
            method=method,
            status=status,
            session_id=session_id,
            masked_input_hash=input_hash,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            ip=ip,
            trace_id=trace_id,
            duration_ms=duration_ms,
        )

        try:
            producer = self._get_producer()
            producer.send("audit.logs", value=event.model_dump())
            producer.flush(timeout=1.0)
        except Exception as e:
            logger.error(f"Failed to send audit log: {e}")

    def close(self) -> None:
        """Close the producer."""
        if self._producer:
            self._producer.close()


audit_logger = AuditLogger()

