import asyncio
import logging
from typing import Optional
from aiokafka import AIOKafkaProducer
from app.core.config import settings

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Simple circuit breaker for Kafka producer."""

    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"          # Failing — reject calls fast
    HALF_OPEN = "HALF_OPEN"  # Testing recovery

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 30):
        self.state = self.CLOSED
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._last_failure_time: Optional[float] = None

    def record_success(self):
        self.failure_count = 0
        self.state = self.CLOSED

    def record_failure(self):
        self.failure_count += 1
        import time
        self._last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = self.OPEN
            logger.warning("Circuit breaker OPENED — Kafka appears unreachable")

    def can_attempt(self) -> bool:
        if self.state == self.CLOSED:
            return True
        if self.state == self.OPEN:
            import time
            if time.time() - self._last_failure_time > self.recovery_timeout:
                self.state = self.HALF_OPEN
                return True
            return False
        return True  # HALF_OPEN: allow one attempt


class KafkaProducerClient:
    def __init__(self):
        self._producer: Optional[AIOKafkaProducer] = None
        self._circuit_breaker = CircuitBreaker()

    async def start(self):
        try:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: v.encode("utf-8") if isinstance(v, str) else v,
                key_serializer=lambda k: k.encode("utf-8") if isinstance(k, str) else k,
                acks="all",           # Wait for all replicas to acknowledge
                retries=3,
                max_batch_size=16384,
                linger_ms=5,          # Small batching window for throughput
            )
            await self._producer.start()
            logger.info("Kafka producer connected")
        except Exception as e:
            logger.error(f"Kafka producer failed to start: {e}")
            self._producer = None

    async def stop(self):
        if self._producer:
            await self._producer.stop()

    async def publish(self, topic: str, key: str, value: str):
        """Publish a message to Kafka with circuit-breaker protection."""
        if not self._circuit_breaker.can_attempt():
            logger.warning("Circuit breaker OPEN — skipping Kafka publish")
            # Graceful degradation: could write to a fallback queue here
            raise Exception("Kafka circuit breaker is open")

        if not self._producer:
            raise Exception("Kafka producer not initialized")

        try:
            await self._producer.send_and_wait(topic, value=value, key=key)
            self._circuit_breaker.record_success()
        except Exception as e:
            self._circuit_breaker.record_failure()
            raise e
