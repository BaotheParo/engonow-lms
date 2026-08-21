package com.engonow.lms.scheduler;

import com.engonow.lms.entity.OutboxEvent;
import com.engonow.lms.enums.OutboxStatus;
import com.engonow.lms.metrics.TelemetryManager;
import com.engonow.lms.publisher.MessagePublisher;
import com.engonow.lms.repository.OutboxEventRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Scheduled resilience fallback poller (Reconciliation Sweep) for the Transactional Outbox.
 * Polls orphan PENDING events that were not eagerly dispatched and publishes them.
 */
@Component
@Slf4j
@RequiredArgsConstructor
public class OutboxRelayScheduler {

    private static final int MAX_RETRIES = 3;
    private static final int BATCH_SIZE = 50;

    private final OutboxEventRepository outboxEventRepository;
    private final MessagePublisher messagePublisher;
    private final TelemetryManager telemetryManager;
    private final TransactionTemplate transactionTemplate;
    private final AtomicBoolean relayRunning = new AtomicBoolean(false);

    @Scheduled(fixedDelayString = "${engonow.outbox.reconciliation-delay-ms:10000}")
    public void processPendingOutboxEvents() {
        if (!relayRunning.compareAndSet(false, true)) {
            log.debug("[OUTBOX RELAY] Skipping overlapping relay execution");
            return;
        }

        try {
            Instant threshold = Instant.now().minus(Duration.ofSeconds(10));
            // 1. Fetch pending events inside a short transaction
            List<OutboxEvent> pendingEvents = transactionTemplate.execute(status -> {
                List<OutboxEvent> events = null;
                try {
                    events = outboxEventRepository.findPendingEventsForReconciliation(threshold, BATCH_SIZE);
                } catch (Exception ex) {
                    log.debug("[OUTBOX RELAY] findPendingEventsForReconciliation failed ({}), using fallback query", ex.getMessage());
                }
                if (events == null || events.isEmpty()) {
                    events = outboxEventRepository.findTop100ByStatusOrderByCreatedAtAsc(OutboxStatus.PENDING);
                }
                return events;
            });

            if (pendingEvents == null || pendingEvents.isEmpty()) {
                return;
            }

            log.info("[OUTBOX RECONCILIATION] Found {} orphan pending outbox event(s) to dispatch", pendingEvents.size());

            // 2. Publish events OUTSIDE of any transaction context
            for (OutboxEvent event : pendingEvents) {
                processEvent(event);
            }
        } finally {
            relayRunning.set(false);
        }
    }

    private void processEvent(OutboxEvent event) {
        try {
            // Synchronous network call to Kafka broker (safely runs outside DB transaction)
            messagePublisher.publish(event);

            // Commit state change inside a short transaction
            transactionTemplate.execute(status -> {
                outboxEventRepository.findById(event.getId()).ifPresent(dbEvent -> {
                    dbEvent.markPublished();
                    outboxEventRepository.save(dbEvent);
                    log.info("[OUTBOX RELAY] Successfully published and marked outbox event id={} aggregateId={}",
                        dbEvent.getId(), dbEvent.getAggregateId());
                });
                return null;
            });
        } catch (Exception ex) {
            telemetryManager.incrementOutboxRelayErrors();
            log.error("[OUTBOX RELAY] Failed to publish outbox event id={}: {}",
                event.getId(), errorMessage(ex), ex);
            recordFailure(event, ex);
        }
    }

    private void recordFailure(OutboxEvent event, Exception failure) {
        try {
            transactionTemplate.execute(status -> {
                outboxEventRepository.findById(event.getId()).ifPresent(dbEvent -> {
                    dbEvent.incrementRetry(errorMessage(failure), MAX_RETRIES);
                    outboxEventRepository.save(dbEvent);
                });
                return null;
            });
        } catch (Exception persistenceFailure) {
            log.error("[OUTBOX RELAY] Failed to persist failure state for outbox event id={}: {}",
                event.getId(), errorMessage(persistenceFailure), persistenceFailure);
        }
    }

    @Scheduled(cron = "${engonow.outbox.cleanup-cron:0 0 2 * * ?}")
    public void cleanupOldPublishedEvents() {
        try {
            Instant threshold = Instant.now().minus(Duration.ofDays(7));
            Integer deleted = transactionTemplate.execute(status -> 
                outboxEventRepository.deleteByStatusAndPublishedAtBefore(OutboxStatus.PUBLISHED, threshold)
            );
            if (deleted != null && deleted > 0) {
                log.info("[OUTBOX CLEANUP] Purged {} stale published outbox events older than 7 days", deleted);
            }
        } catch (Exception ex) {
            log.error("[OUTBOX CLEANUP] Failed to purge old published outbox events: {}", ex.getMessage(), ex);
        }
    }

    private String errorMessage(Exception exception) {
        return exception.getMessage() != null
            ? exception.getMessage()
            : exception.getClass().getSimpleName();
    }
}
