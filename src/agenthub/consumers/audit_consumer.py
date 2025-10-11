"""Audit log consumer for rollups and analysis."""

import json
import logging
from typing import Any, Dict

from kafka import KafkaConsumer

from agenthub.config import settings

logger = logging.getLogger(__name__)


class AuditConsumer:
    """Consumer for audit.logs topic."""

    def __init__(self) -> None:
        """Initialize audit consumer."""
        self.consumer = KafkaConsumer(
            "audit.logs",
            bootstrap_servers=settings.kafka_broker,
            group_id="audit-consumer-group",
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )

    def process_event(self, event: Dict[str, Any]) -> None:
        """Process an audit event.
        
        Args:
            event: Audit event dict
        """
        # In production, this would:
        # - Store in a time-series database
        # - Create daily rollups
        # - Trigger alerts on anomalies
        logger.info(f"Processed audit event: {event.get('event_type')} from {event.get('api_key_id')}")

    def run(self) -> None:
        """Run the consumer loop."""
        logger.info("Starting audit consumer...")
        try:
            for message in self.consumer:
                try:
                    self.process_event(message.value)
                except Exception as e:
                    logger.error(f"Failed to process audit event: {e}")
        except KeyboardInterrupt:
            logger.info("Shutting down audit consumer...")
        finally:
            self.consumer.close()


def main() -> None:
    """Run audit consumer."""
    consumer = AuditConsumer()
    consumer.run()


if __name__ == "__main__":
    main()

