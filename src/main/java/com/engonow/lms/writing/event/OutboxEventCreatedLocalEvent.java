package com.engonow.lms.writing.event;

import java.util.Map;
import java.util.UUID;

/**
 * Spring application in-process event published immediately after an Outbox row is persisted,
 * triggering non-blocking eager Kafka dispatching on transaction commit.
 */
public record OutboxEventCreatedLocalEvent(
    UUID outboxEventId,
    String topic,
    String partitionKey,
    String rawEnvelopeJson,
    Map<String, byte[]> headers
) {}
