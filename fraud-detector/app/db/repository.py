"""
PostgreSQL Repository
=====================
Handles all database writes for the fraud detector.
Uses asyncpg for non-blocking I/O.
"""
import logging
from typing import Optional
import asyncpg
from app.core.config import settings

logger = logging.getLogger(__name__)

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id          BIGSERIAL PRIMARY KEY,
    email       VARCHAR(255) UNIQUE,
    country     VARCHAR(50),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transactions (
    id                  BIGSERIAL PRIMARY KEY,
    transaction_id      UUID UNIQUE NOT NULL,
    user_id             BIGINT NOT NULL,
    amount              NUMERIC(12, 2),
    merchant            VARCHAR(100),
    country             VARCHAR(50),
    risk_score          SMALLINT,
    risk_level          VARCHAR(10),
    status              VARCHAR(20),
    triggered_rules     TEXT[],
    processing_time_ms  NUMERIC(8, 2),
    decided_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tx_user_id    ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_tx_status     ON transactions(status);
CREATE INDEX IF NOT EXISTS idx_tx_decided_at ON transactions(decided_at DESC);

CREATE TABLE IF NOT EXISTS alerts (
    id              BIGSERIAL PRIMARY KEY,
    transaction_id  UUID REFERENCES transactions(transaction_id),
    alert_type      VARCHAR(50),
    payload         JSONB,
    sent_at         TIMESTAMPTZ DEFAULT NOW()
);
"""


class TransactionRepository:
    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        try:
            # Convert asyncpg DSN format (strip +asyncpg if present)
            dsn = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
            self._pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
            async with self._pool.acquire() as conn:
                await conn.execute(CREATE_TABLES_SQL)
            logger.info("PostgreSQL connected and tables ensured")
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {e}")
            self._pool = None

    async def close(self):
        if self._pool:
            await self._pool.close()

    async def save_decision(self, decision: dict):
        if not self._pool:
            logger.warning("PostgreSQL unavailable — skipping persist")
            return

        sql = """
            INSERT INTO transactions
                (transaction_id, user_id, amount, country, risk_score,
                 risk_level, status, triggered_rules, processing_time_ms, decided_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (transaction_id) DO NOTHING
        """
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    sql,
                    decision["transaction_id"],
                    decision["user_id"],
                    decision.get("amount"),
                    decision.get("country"),
                    decision["risk_score"],
                    decision["risk_level"],
                    decision["status"],
                    decision.get("triggered_rules", []),
                    decision.get("processing_time_ms"),
                    decision.get("decided_at"),
                )
        except Exception as e:
            logger.error(f"Failed to persist decision {decision['transaction_id']}: {e}")
