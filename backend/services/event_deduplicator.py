"""
CAPI Event Deduplicator
Uses Redis to deduplicate events firing from both browser and server.
Implements event_id logic for cross-platform deduplication.
"""

import logging
import time
from typing import Optional, Tuple
from backend.config import settings

logger = logging.getLogger(__name__)

# Event TTL in seconds (how long to remember an event_id)
EVENT_TTL = 3600  # 1 hour


class EventDeduplicator:
    """
    CAPI-style event deduplication using event_id.
    Ensures single attribution per user action across browser + server events.
    """

    def __init__(self):
        self._redis = None
        self._memory_cache = {}  # Fallback when Redis unavailable

    async def _get_redis(self):
        """Lazy-initialize async Redis connection."""
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                )
                await self._redis.ping()
            except Exception as e:
                logger.warning(f"Redis unavailable: {e}. Using in-memory cache.")
                self._redis = None
        return self._redis

    async def check_and_record(
        self, event_id: str, event_name: str, session_token: str
    ) -> Tuple[bool, str]:
        """
        Check if an event is a duplicate and record it.

        Args:
            event_id: Unique event identifier
            event_name: Type of event
            session_token: Session identifier

        Returns:
            Tuple of (is_duplicate, status)
        """
        cache_key = f"aidus:event:{event_id}"

        redis = await self._get_redis()
        if redis:
            try:
                # SETNX: Set if Not eXists (atomic deduplication)
                was_set = await redis.set(
                    cache_key,
                    f"{event_name}:{session_token}:{int(time.time())}",
                    nx=True,
                    ex=EVENT_TTL,
                )
                if was_set:
                    return False, "ACCEPTED"
                else:
                    return True, "DEDUPLICATED"
            except Exception as e:
                logger.error(f"Redis dedup error: {e}")

        # Fallback: in-memory dedup
        if event_id in self._memory_cache:
            return True, "DEDUPLICATED"

        self._memory_cache[event_id] = {
            "event_name": event_name,
            "session_token": session_token,
            "timestamp": time.time(),
        }

        # Cleanup old entries
        self._cleanup_memory_cache()
        return False, "ACCEPTED"

    def _cleanup_memory_cache(self):
        """Remove expired entries from in-memory cache."""
        now = time.time()
        expired = [
            k for k, v in self._memory_cache.items()
            if now - v["timestamp"] > EVENT_TTL
        ]
        for k in expired:
            del self._memory_cache[k]


# Singleton
event_deduplicator = EventDeduplicator()
