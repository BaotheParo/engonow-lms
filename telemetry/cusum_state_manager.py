"""
telemetry/cusum_state_manager.py
================================
State Manager for CUSUM Drift Detection with Redis primary cache and Postgres durable checkpoints.
Provides atomic deduplication, cold-start recovery, and system drift-hold safety flag governance.
"""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set
from telemetry.cusum_detector import CusumState

logger = logging.getLogger(__name__)

DEDUP_TTL_SECONDS = 7 * 24 * 3600  # 7 days

class InMemoryStateBackend:
    """In-memory Redis and Postgres simulation for hermetic testing and zero-dependency mode."""
    def __init__(self):
        self.hashes: Dict[str, Dict[str, str]] = {}
        self.sets: Dict[str, Set[str]] = {}
        self.keys: Dict[str, str] = {}
        self.ttls: Dict[str, int] = {}
        self.db_checkpoints: Dict[str, Dict[str, Any]] = {}
        self.db_flags: Dict[str, Dict[str, Any]] = {}

    async def hgetall(self, key: str) -> Dict[str, str]:
        return self.hashes.get(key, {})

    async def hset(self, key: str, mapping: Dict[str, str]) -> None:
        if key not in self.hashes:
            self.hashes[key] = {}
        self.hashes[key].update(mapping)

    async def sismember(self, key: str, member: str) -> bool:
        return member in self.sets.get(key, set())

    async def sadd(self, key: str, member: str) -> None:
        if key not in self.sets:
            self.sets[key] = set()
        self.sets[key].add(member)

    async def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = seconds

    async def get(self, key: str) -> Optional[str]:
        return self.keys.get(key)

    async def set(self, key: str, value: str) -> None:
        self.keys[key] = value

    async def keys_pattern(self, pattern: str) -> List[str]:
        prefix = pattern.replace("*", "")
        return [k for k in self.hashes.keys() if k.startswith(prefix)]

class CusumStateManager:
    """
    Manages CUSUM state across Redis primary storage and PostgreSQL fallback/checkpoint tables.
    """

    def __init__(self, redis_client: Optional[Any] = None, pg_conn: Optional[Any] = None):
        self.redis = redis_client if redis_client is not None else InMemoryStateBackend()
        self.pg_conn = pg_conn
        self._is_in_memory = isinstance(self.redis, InMemoryStateBackend)

    def _state_key(self, subsystem: str, criterion: str) -> str:
        return f"cusum:state:{subsystem}:{criterion}"

    def _dedup_key(self, subsystem: str, criterion: str) -> str:
        return f"cusum:dedup:{subsystem}:{criterion}"

    async def get_state(self, subsystem: str, criterion: str) -> CusumState:
        """
        Retrieves CUSUM state from Redis. On cache miss (cold start), recovers from PostgreSQL.
        """
        key = self._state_key(subsystem, criterion)
        raw_hash = await self.redis.hgetall(key)

        if raw_hash and len(raw_hash) > 0:
            # Redis hit
            return CusumState(
                subsystem=subsystem,
                criterion=criterion,
                c_plus=float(raw_hash.get("c_plus", 0.0)),
                c_minus=float(raw_hash.get("c_minus", 0.0)),
                sample_count=int(raw_hash.get("sample_count", 0)),
                last_updated_at=raw_hash.get("last_updated_at"),
                last_reset_at=raw_hash.get("last_reset_at")
            )

        # Cold-start: Attempt PostgreSQL recovery
        recovered = await self._recover_from_postgres(subsystem, criterion)
        if recovered:
            logger.info("[CUSUM STATE] Cold-start recovered state for %s.%s from PostgreSQL", subsystem, criterion)
            await self.save_state_and_mark_dedup(recovered, event_id=None)
            return recovered

        # Brand new state
        logger.warning("[CUSUM STATE] No existing state found for %s.%s. Initializing fresh 0.0 baseline.", subsystem, criterion)
        return CusumState(subsystem=subsystem, criterion=criterion)

    async def is_duplicate_event(self, subsystem: str, criterion: str, event_id: str) -> bool:
        """
        Authoritative event deduplication using Redis SET with 7-day TTL.
        """
        dedup_key = self._dedup_key(subsystem, criterion)
        return await self.redis.sismember(dedup_key, event_id)

    async def save_state_and_mark_dedup(self, state: CusumState, event_id: Optional[str] = None) -> None:
        """
        Atomically saves CUSUM state hash and records event ID in deduplication set.
        """
        state_key = self._state_key(state.subsystem, state.criterion)
        mapping = {
            "c_plus": str(state.c_plus),
            "c_minus": str(state.c_minus),
            "sample_count": str(state.sample_count),
            "last_updated_at": state.last_updated_at or datetime.now(timezone.utc).isoformat(),
            "last_reset_at": state.last_reset_at or ""
        }
        await self.redis.hset(state_key, mapping=mapping)

        if event_id:
            dedup_key = self._dedup_key(state.subsystem, state.criterion)
            await self.redis.sadd(dedup_key, event_id)
            await self.redis.expire(dedup_key, DEDUP_TTL_SECONDS)

    async def set_drift_hold(self, is_held: bool, reason: str) -> None:
        """
        Sets the system-wide drift_hold safety flag in Redis and persists to PostgreSQL.
        """
        flag_val = "1" if is_held else "0"
        await self.redis.set("system:drift_hold:flag", flag_val)

        now_iso = datetime.now(timezone.utc).isoformat()
        if self._is_in_memory:
            self.redis.db_flags["drift_hold"] = {
                "flag_key": "drift_hold",
                "flag_value": is_held,
                "reason": reason,
                "updated_at": now_iso
            }
        elif self.pg_conn:
            try:
                query = """
                    INSERT INTO calibration_system_flags (flag_key, flag_value, reason, updated_at)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (flag_key) DO UPDATE
                    SET flag_value = EXCLUDED.flag_value,
                        reason = EXCLUDED.reason,
                        updated_at = EXCLUDED.updated_at
                """
                await self.pg_conn.execute(query, "drift_hold", is_held, reason, datetime.now(timezone.utc))
            except Exception as e:
                logger.error("[CUSUM STATE] Failed to persist drift_hold flag to PostgreSQL: %s", str(e))

        logger.warning("[CUSUM DRIFT HOLD] Set system drift_hold=%s reason='%s'", is_held, reason)

    async def is_drift_hold_active(self) -> bool:
        """
        Checks whether the system drift_hold safety flag is active.
        """
        val = await self.redis.get("system:drift_hold:flag")
        if val is not None:
            return val in ("1", "true", "True")

        # Fallback to Postgres
        if self._is_in_memory:
            flag_entry = self.redis.db_flags.get("drift_hold")
            if flag_entry:
                return flag_entry.get("flag_value", False)
        elif self.pg_conn:
            try:
                row = await self.pg_conn.fetchrow(
                    "SELECT flag_value FROM calibration_system_flags WHERE flag_key = 'drift_hold'"
                )
                if row:
                    return bool(row["flag_value"])
            except Exception as e:
                logger.error("[CUSUM STATE] Failed to read drift_hold from PostgreSQL: %s", str(e))

        return False

    async def checkpoint_to_postgres(self) -> int:
        """
        Persists all active Redis CUSUM state hashes to PostgreSQL calibration_cusum_checkpoints.
        Groups all state records into a single atomic batch transaction (executemany) to minimize network RTT.
        """
        keys = []
        if hasattr(self.redis, "keys_pattern"):
            keys = await self.redis.keys_pattern("cusum:state:*")
        elif hasattr(self.redis, "keys"):
            keys = await self.redis.keys("cusum:state:*")

        checkpointed = 0
        records = []

        for k in keys:
            k_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
            parts = k_str.split(":")
            if len(parts) != 4:
                continue
            subsystem, criterion = parts[2], parts[3]
            state = await self.get_state(subsystem, criterion)

            if self._is_in_memory:
                self.redis.db_checkpoints[f"{subsystem}:{criterion}"] = {
                    "subsystem": subsystem,
                    "criterion": criterion,
                    "c_plus": state.c_plus,
                    "c_minus": state.c_minus,
                    "sample_count": state.sample_count,
                    "last_updated_at": state.last_updated_at,
                    "last_reset_at": state.last_reset_at
                }
                checkpointed += 1
            else:
                records.append((
                    subsystem,
                    criterion,
                    state.c_plus,
                    state.c_minus,
                    state.sample_count,
                    datetime.now(timezone.utc),
                    datetime.fromisoformat(state.last_reset_at) if state.last_reset_at else None
                ))

        if not self._is_in_memory and self.pg_conn and records:
            try:
                query = """
                    INSERT INTO calibration_cusum_checkpoints
                    (subsystem, criterion, c_plus, c_minus, sample_count, last_updated_at, last_reset_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (subsystem, criterion) DO UPDATE
                    SET c_plus = EXCLUDED.c_plus,
                        c_minus = EXCLUDED.c_minus,
                        sample_count = EXCLUDED.sample_count,
                        last_updated_at = EXCLUDED.last_updated_at,
                        last_reset_at = EXCLUDED.last_reset_at
                """
                if hasattr(self.pg_conn, "transaction"):
                    async with self.pg_conn.transaction():
                        await self.pg_conn.executemany(query, records)
                else:
                    await self.pg_conn.executemany(query, records)
                checkpointed = len(records)
            except Exception as e:
                logger.error("[CUSUM CHECKPOINT] Batch checkpoint error to PostgreSQL: %s", str(e))

        logger.info("[CUSUM CHECKPOINT] Successfully checkpointed %d state(s) to PostgreSQL", checkpointed)
        return checkpointed

    async def _recover_from_postgres(self, subsystem: str, criterion: str) -> Optional[CusumState]:
        if self._is_in_memory:
            data = self.redis.db_checkpoints.get(f"{subsystem}:{criterion}")
            if data:
                return CusumState(
                    subsystem=subsystem,
                    criterion=criterion,
                    c_plus=data["c_plus"],
                    c_minus=data["c_minus"],
                    sample_count=data["sample_count"],
                    last_updated_at=data["last_updated_at"],
                    last_reset_at=data["last_reset_at"]
                )
            return None

        if self.pg_conn:
            try:
                row = await self.pg_conn.fetchrow(
                    "SELECT c_plus, c_minus, sample_count, last_updated_at, last_reset_at "
                    "FROM calibration_cusum_checkpoints WHERE subsystem = $1 AND criterion = $2",
                    subsystem, criterion
                )
                if row:
                    return CusumState(
                        subsystem=subsystem,
                        criterion=criterion,
                        c_plus=float(row["c_plus"]),
                        c_minus=float(row["c_minus"]),
                        sample_count=int(row["sample_count"]),
                        last_updated_at=row["last_updated_at"].isoformat() if row["last_updated_at"] else None,
                        last_reset_at=row["last_reset_at"].isoformat() if row["last_reset_at"] else None
                    )
            except Exception as e:
                logger.error("[CUSUM RECOVERY] Failed to query PostgreSQL for %s.%s: %s", subsystem, criterion, str(e))

        return None
