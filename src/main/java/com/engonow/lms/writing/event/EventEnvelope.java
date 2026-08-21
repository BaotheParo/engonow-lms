package com.engonow.lms.writing.event;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.time.Instant;
import java.util.UUID;

/**
 * Standardized event envelope wrapping all Kafka messages within the ENGONOW
 * event-driven architecture, strictly conforming to {@code schemas/envelope.json}.
 *
 * @param <T> Domain payload type
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record EventEnvelope<T>(
    UUID eventId,
    UUID idempotencyKey,
    String eventType,
    String schemaVersion,
    Instant occurredAt,
    Instant producedAt,
    String traceId,
    String correlationId,
    String source,
    int retryCount,
    T payload
) {

    public static <T> EventEnvelope<T> of(
        String eventType,
        UUID idempotencyKey,
        String correlationId,
        String traceId,
        String source,
        T payload
    ) {
        Instant now = Instant.now();
        return new EventEnvelope<>(
            UUID.randomUUID(),
            idempotencyKey,
            eventType,
            "1.0",
            now,
            now,
            traceId != null ? traceId : UUID.randomUUID().toString(),
            correlationId != null ? correlationId : idempotencyKey.toString(),
            source != null ? source : "engonow-lms-backend",
            0,
            payload
        );
    }
}
