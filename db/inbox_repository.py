import logging
import json
from uuid import UUID
import asyncpg
from models.events import EventEnvelope

logger = logging.getLogger(__name__)

async def try_acquire_inbox(conn: asyncpg.Connection, envelope: EventEnvelope) -> bool:
    """
    Atomically inserts the incoming outbox event payload to the inbox_events table.
    Ensures message deduplication using PostgreSQL unique constraint handling.

    Returns:
        True if successfully acquired (first time seeing the event).
        False if event is a duplicate.
    """
    query = """
        INSERT INTO inbox_events (event_id, idempotency_key, event_type, source_service, payload, status)
        VALUES ($1, $2, $3, $4, $5, 'PROCESSING')
        ON CONFLICT (idempotency_key) DO NOTHING
        RETURNING id;
    """
    try:
        # Convert envelope payload to JSON string
        payload_json = envelope.payload.model_dump_json()
        row = await conn.fetchrow(
            query,
            envelope.eventId,
            envelope.idempotencyKey,
            envelope.eventType,
            envelope.source,
            payload_json
        )
        # If row is returned, it means insert succeeded and row is acquired.
        return row is not None
    except Exception as e:
        logger.error(
            "Failed to acquire inbox event idempotencyKey=%s error=%s",
            envelope.idempotencyKey,
            str(e),
            extra={"traceId": envelope.traceId, "idempotencyKey": str(envelope.idempotencyKey)}
        )
        raise

async def mark_inbox_completed(conn: asyncpg.Connection, idempotency_key: UUID) -> None:
    """
    Marks the inbox event as successfully processed.
    """
    query = """
        UPDATE inbox_events
        SET status = 'PROCESSED', processed_at = CURRENT_TIMESTAMP
        WHERE idempotency_key = $1;
    """
    await conn.execute(query, idempotency_key)

async def mark_inbox_failed(conn: asyncpg.Connection, idempotency_key: UUID, error_msg: str) -> None:
    """
    Marks the inbox event as failed and logs the error context.
    """
    query = """
        UPDATE inbox_events
        SET status = 'FAILED', error_message = $1, processed_at = CURRENT_TIMESTAMP
        WHERE idempotency_key = $2;
    """
    await conn.execute(query, error_msg, idempotency_key)
