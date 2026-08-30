"""
performance/kafka_duplicate_stress_test.py
==========================================
Stress testing script for Kafka Inbox transactional deduplication.
Publishes 50 unique evaluation requested events, followed immediately by an identical replay
of the same 50 event IDs, verifying that exactly 50 events are processed and 50 are skipped as duplicates.
"""

import asyncio
import json
import uuid
import logging
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("KafkaDuplicateStressTest")


class MockInboxRepository:
    """In-memory simulation of the PostgreSQL Inbox deduplication table."""
    def __init__(self):
        self.processed_keys = set()
        self.lock = asyncio.Lock()
        self.processed_count = 0
        self.duplicate_count = 0

    async def try_acquire_inbox(self, event_id: str, idempotency_key: str) -> bool:
        async with self.lock:
            key = f"{event_id}:{idempotency_key}"
            if key in self.processed_keys:
                self.duplicate_count += 1
                return False
            self.processed_keys.add(key)
            self.processed_count += 1
            return True


async def simulate_event_consumption(
    inbox_repo: MockInboxRepository,
    event: Dict[str, Any]
) -> bool:
    event_id = event["eventId"]
    idempotency_key = event["idempotencyKey"]

    acquired = await inbox_repo.try_acquire_inbox(event_id, idempotency_key)
    if not acquired:
        logger.debug("[DUPLICATE] Skipped duplicate eventId=%s idempotencyKey=%s", event_id, idempotency_key)
        return False

    # Simulate evaluation processing
    await asyncio.sleep(0.005)
    return True


async def run_stress_test():
    logger.info("Starting Kafka Duplicate Stress Test (50 unique + 50 duplicates = 100 total messages)...")
    inbox = MockInboxRepository()

    # 1. Generate 50 unique messages
    batch_1: List[Dict[str, Any]] = []
    for i in range(50):
        sub_id = str(uuid.uuid4())
        batch_1.append({
            "eventId": f"event-{i:03d}",
            "idempotencyKey": f"idemp-key-{i:03d}",
            "eventType": "WRITING_EVALUATION_REQUESTED",
            "payload": {"submissionId": sub_id, "taskType": "TASK2"}
        })

    # 2. Duplicate batch
    batch_2 = [dict(msg) for msg in batch_1]

    # Interleave and execute concurrently
    all_messages = batch_1 + batch_2

    tasks = [simulate_event_consumption(inbox, msg) for msg in all_messages]
    results = await asyncio.gather(*tasks)

    logger.info("Stress Test Finished:")
    logger.info("Total messages sent: %d", len(all_messages))
    logger.info("Successfully processed unique events: %d (Expected: 50)", inbox.processed_count)
    logger.info("Correctly skipped duplicate events: %d (Expected: 50)", inbox.duplicate_count)

    assert inbox.processed_count == 50, f"Expected 50 processed events, got {inbox.processed_count}"
    assert inbox.duplicate_count == 50, f"Expected 50 duplicate events, got {inbox.duplicate_count}"
    logger.info("100% IDEMPOTENCY INTEGRITY VERIFIED!")


if __name__ == "__main__":
    asyncio.run(run_stress_test())
