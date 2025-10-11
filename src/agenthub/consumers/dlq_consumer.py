"""Dead letter queue consumer."""

import json
import logging
from typing import Any, Dict

from kafka import KafkaConsumer

from agenthub.config import settings

logger = logging.getLogger(__name__)


class DLQConsumer:
    """Consumer for dead.letter topic."""

    def __init__(self) -> None:
        """Initialize DLQ consumer."""
        self.consumer = KafkaConsumer(
            "dead.letter",
            bootstrap_servers=settings.kafka_broker,
            group_id="dlq-consumer-group",
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )

    def process_event(self, event: Dict[str, Any]) -> None:
        """Process a DLQ event.
        
        Args:
            event: DLQ event dict
        """
        # In production, this would:
        # - Alert on-call engineers
        # - Store in a separate database for analysis
        # - Attempt retry with exponential backoff
        logger.warning(
            f"DLQ event from {event.get('original_topic')}: "
            f"{event.get('error')} (retries: {event.get('retry_count')})"
        )

    def run(self) -> None:
        """Run the consumer loop."""
        logger.info("Starting DLQ consumer...")
        try:
            for message in self.consumer:
                try:
                    self.process_event(message.value)
                except Exception as e:
                    logger.error(f"Failed to process DLQ event: {e}")
        except KeyboardInterrupt:
            logger.info("Shutting down DLQ consumer...")
        finally:
            self.consumer.close()


def main() -> None:
    """Run DLQ consumer."""
    consumer = DLQConsumer()
    consumer.run()


if __name__ == "__main__":
    main()

