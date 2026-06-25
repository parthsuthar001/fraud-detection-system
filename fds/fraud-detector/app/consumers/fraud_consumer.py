"""
Fraud Detection Worker
=======================
Consumes from `transactions-raw`, runs the rule engine + ML model,
writes decisions to PostgreSQL, publishes results to `fraud-events`.
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from app.core.config import settings
from app.rules.engine import evaluate, score_to_level, score_to_action, TransactionContext
from app.rules.velocity import VelocityTracker
from app.db.repository import TransactionRepository
from app.ml.features import build_features
from app.ml.scorer import get_scorer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class FraudDetectorWorker:
    def __init__(self):
        self.consumer: AIOKafkaConsumer = None
        self.producer: AIOKafkaProducer = None
        self.velocity = VelocityTracker()
        self.repo = TransactionRepository()
        self._running = False
        self._scorer = get_scorer()

    async def start(self):
        # Load ML model (gracefully skipped if not trained yet)
        self._scorer.load()

        await self.velocity.connect()
        await self.repo.connect()

        self.consumer = AIOKafkaConsumer(
            settings.KAFKA_TOPIC_TRANSACTIONS,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="fraud-detector-group",
            auto_offset_reset="earliest",
            enable_auto_commit=False,   # Manual commit — process exactly once
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )
        self.producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

        await self.consumer.start()
        await self.producer.start()
        self._running = True
        logger.info(
            f"Fraud detector worker started — ML scoring: "
            f"{'ENABLED' if self._scorer.is_available else 'DISABLED (rules only)'}"
        )

    async def stop(self):
        self._running = False
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
        await self.velocity.close()
        await self.repo.close()

    async def process_message(self, transaction: dict):
        start_time = time.perf_counter()
        transaction_id = transaction["transaction_id"]
        user_id = transaction["user_id"]

        # ── 1. Idempotency check (dedup) ─────────────────────────────────
        if await self.velocity.is_duplicate(transaction_id):
            logger.warning(f"Duplicate transaction {transaction_id} — skipping")
            return

        # ── 2. Build context from Redis ───────────────────────────────────
        velocity_counts = await self.velocity.record_and_count(user_id, transaction_id)
        country_history = await self.velocity.get_country_history(user_id)
        last_tx = await self.velocity.get_last_transaction(user_id)

        last_ts = None
        if last_tx.get("timestamp"):
            try:
                last_ts = datetime.fromisoformat(last_tx["timestamp"])
            except ValueError:
                pass

        ctx = TransactionContext(
            user_country_history=country_history,
            transactions_last_60s=velocity_counts.get("60s", 0),
            transactions_last_10min=velocity_counts.get("10min", 0),
            last_transaction_country=last_tx.get("country"),
            last_transaction_ts=last_ts,
        )

        # ── 3. Rules engine ───────────────────────────────────────────────
        rule_result = evaluate(transaction, ctx)

        # ── 4. ML scoring (hybrid: rules + XGBoost) ───────────────────────
        features = build_features(transaction, ctx, rule_result.score)
        ml_output = self._scorer.score(features.to_array(), rule_result.score)

        final_score = ml_output["final_score"]
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        decision = {
            "transaction_id": transaction_id,
            "user_id": user_id,
            "amount": transaction.get("amount"),
            "country": transaction.get("country"),
            # Final blended score
            "risk_score": final_score,
            "risk_level": score_to_level(final_score),
            "status": score_to_action(final_score),
            "triggered_rules": rule_result.triggered_rules,
            # ML detail fields
            "ml_score": ml_output.get("ml_score"),
            "ml_probability": ml_output.get("ml_probability"),
            "rule_score": rule_result.score,
            "scoring_mode": ml_output["scoring_mode"],
            "processing_time_ms": round(elapsed_ms, 2),
            "decided_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            f"TX {transaction_id} | final={final_score} "
            f"(ml={ml_output.get('ml_score')} rules={rule_result.score}) | "
            f"status={decision['status']} | mode={ml_output['scoring_mode']} | "
            f"{elapsed_ms:.1f}ms"
        )

        # ── 5. Persist to PostgreSQL ──────────────────────────────────────
        await self.repo.save_decision(decision)

        # ── 6. Update Redis state ─────────────────────────────────────────
        country = transaction.get("country")
        if country:
            await self.velocity.add_country(user_id, country)
            await self.velocity.set_last_transaction(
                user_id, country, decision["decided_at"]
            )

        # ── 7. Publish fraud event to downstream services ─────────────────
        await self.producer.send_and_wait(
            settings.KAFKA_TOPIC_FRAUD_EVENTS,
            value=decision,
            key=str(user_id).encode(),
        )


async def main():
    worker = FraudDetectorWorker()
    await worker.start()
    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await worker.stop()

    async def run(self):
        async for msg in self.consumer:
            if not self._running:
                break
            try:
                await self.process_message(msg.value)
                await self.consumer.commit()
            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
