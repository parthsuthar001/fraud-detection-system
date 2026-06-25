"""
Redis Velocity Tracker
======================
Uses Redis Sorted Sets for O(log N) sliding-window transaction counting.

Key pattern : velocity:{user_id}:{window_seconds}
Members      : transaction_id (score = unix timestamp)

Why Sorted Sets?
  ZADD  — add a transaction in O(log N)
  ZREMRANGEBYSCORE — remove expired entries in O(log N + M)
  ZCARD — count live entries in O(1)

This gives sub-millisecond velocity checks without touching PostgreSQL.
"""
import time
import logging
from typing import Optional
import redis.asyncio as aioredis
from app.core.config import settings

logger = logging.getLogger(__name__)

# Sliding windows to track
WINDOWS = {
    "60s": 60,
    "10min": 600,
    "1h": 3600,
}

DEDUP_TTL_SECONDS = 300  # 5 minutes dedup window


class VelocityTracker:
    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self):
        self._redis = await aioredis.from_url(
            f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("Redis velocity tracker connected")

    async def close(self):
        if self._redis:
            await self._redis.aclose()

    # ------------------------------------------------------------------ #
    # Idempotency / De-duplication                                         #
    # ------------------------------------------------------------------ #

    async def is_duplicate(self, transaction_id: str) -> bool:
        """
        Check if this transaction has already been processed.
        Protects against Kafka at-least-once redelivery.
        """
        if not self._redis:
            return False
        key = f"dedup:{transaction_id}"
        # SET key 1 EX ttl NX  — atomic set-if-not-exists
        result = await self._redis.set(key, "1", ex=DEDUP_TTL_SECONDS, nx=True)
        return result is None  # None means key already existed → duplicate

    # ------------------------------------------------------------------ #
    # Velocity counts                                                      #
    # ------------------------------------------------------------------ #

    async def record_and_count(self, user_id: int, transaction_id: str) -> dict[str, int]:
        """
        Record a transaction and return counts for all sliding windows.
        Returns: {"60s": N, "10min": N, "1h": N}
        """
        if not self._redis:
            return {k: 0 for k in WINDOWS}

        now = time.time()
        counts = {}

        async with self._redis.pipeline(transaction=True) as pipe:
            for window_name, seconds in WINDOWS.items():
                key = f"velocity:{user_id}:{window_name}"
                cutoff = now - seconds

                pipe.zadd(key, {transaction_id: now})           # Add current tx
                pipe.zremrangebyscore(key, "-inf", cutoff)       # Remove expired
                pipe.zcard(key)                                  # Count remaining
                pipe.expire(key, seconds * 2)                   # Auto-cleanup TTL

            results = await pipe.execute()

        # Parse results: 4 commands per window → zcard is at index 2, 6, 10 ...
        for i, window_name in enumerate(WINDOWS):
            counts[window_name] = results[i * 4 + 2]

        return counts

    # ------------------------------------------------------------------ #
    # Country history                                                      #
    # ------------------------------------------------------------------ #

    async def get_country_history(self, user_id: int) -> list[str]:
        """Return the last 20 unique countries this user transacted from."""
        if not self._redis:
            return []
        key = f"user:{user_id}:countries"
        return await self._redis.lrange(key, 0, 19)

    async def add_country(self, user_id: int, country: str):
        """Push a country to the user's recent country list."""
        if not self._redis:
            return
        key = f"user:{user_id}:countries"
        async with self._redis.pipeline() as pipe:
            pipe.lpush(key, country)
            pipe.ltrim(key, 0, 19)    # Keep last 20 only
            pipe.expire(key, 86400 * 30)  # 30-day TTL
            await pipe.execute()

    # ------------------------------------------------------------------ #
    # Last transaction info                                                #
    # ------------------------------------------------------------------ #

    async def get_last_transaction(self, user_id: int) -> dict:
        """Get the country and timestamp of the user's most recent transaction."""
        if not self._redis:
            return {}
        key = f"user:{user_id}:last_tx"
        return await self._redis.hgetall(key) or {}

    async def set_last_transaction(self, user_id: int, country: str, timestamp: str):
        if not self._redis:
            return
        key = f"user:{user_id}:last_tx"
        await self._redis.hset(key, mapping={"country": country, "timestamp": timestamp})
        await self._redis.expire(key, 86400)  # 24-hour TTL
