package com.engonow.lms.writing.listener;

import com.engonow.lms.repository.OutboxEventRepository;
import com.engonow.lms.writing.event.OutboxEventCreatedLocalEvent;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.Optional;
import java.util.UUID;

/**
 * Non-blocking eager dispatcher listening for committed Outbox events.
 * Triggers asynchronous publishing to Apache Kafka via {@code KafkaTemplate.send()}
 * immediately after the database transaction commits successfully.
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class OutboxEagerDispatcherListener {

    private final Optional<KafkaTemplate<String, String>> kafkaTemplate;
    private final OutboxEventRepository outboxEventRepository;
    private final TransactionTemplate transactionTemplate;

    @Async
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handleOutboxCreated(OutboxEventCreatedLocalEvent event) {
        log.debug("[OUTBOX EAGER DISPATCHER] Received committed outbox event: id={}, topic={}, partitionKey={}",
            event.outboxEventId(), event.topic(), event.partitionKey());

        if (kafkaTemplate.isEmpty()) {
            log.debug("[OUTBOX EAGER DISPATCHER] KafkaTemplate is not configured in this profile. Leaving event {} for local runner/reconciliation.",
                event.outboxEventId());
            return;
        }

        try {
            ProducerRecord<String, String> producerRecord = new ProducerRecord<>(
                event.topic(),
                event.partitionKey(),
                event.rawEnvelopeJson()
            );

            if (event.headers() != null) {
                event.headers().forEach((k, v) -> {
                    if (v != null) {
                        producerRecord.headers().add(new RecordHeader(k, v));
                    }
                });
            }

            kafkaTemplate.get().send(producerRecord).whenComplete((result, ex) -> {
                if (ex == null) {
                    log.info("[OUTBOX EAGER DISPATCHER] Successfully published outbox event id={} to topic={} [partition={}, offset={}]",
                        event.outboxEventId(),
                        event.topic(),
                        result.getRecordMetadata().partition(),
                        result.getRecordMetadata().offset());
                    markOutboxEventPublished(event.outboxEventId());
                } else {
                    log.warn("[OUTBOX EAGER DISPATCHER] Eager dispatch failed for outbox event id={}: {}. Reconciliation sweep will retry.",
                        event.outboxEventId(), ex.getMessage());
                }
            });

        } catch (Exception ex) {
            log.warn("[OUTBOX EAGER DISPATCHER] Unexpected exception during eager dispatch of outbox event id={}: {}. Reconciliation sweep will recover.",
                event.outboxEventId(), ex.getMessage(), ex);
        }
    }

    public void markOutboxEventPublished(UUID outboxEventId) {
        try {
            transactionTemplate.execute(status -> {
                outboxEventRepository.findById(outboxEventId).ifPresent(outboxEvent -> {
                    outboxEvent.markPublished();
                    outboxEventRepository.save(outboxEvent);
                    log.debug("[OUTBOX EAGER DISPATCHER] Marked outbox event {} as PUBLISHED", outboxEventId);
                });
                return null;
            });
        } catch (Exception ex) {
            log.error("[OUTBOX EAGER DISPATCHER] Failed to update outbox event {} status to PUBLISHED: {}",
                outboxEventId, ex.getMessage(), ex);
        }
    }
}
