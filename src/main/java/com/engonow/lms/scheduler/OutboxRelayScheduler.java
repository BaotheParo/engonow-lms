package com.engonow.lms.scheduler;

import com.engonow.lms.entity.OutboxEvent;
import com.engonow.lms.enums.OutboxStatus;
import com.engonow.lms.publisher.MessagePublisher;
import com.engonow.lms.repository.OutboxEventRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

@Component
@Slf4j
@RequiredArgsConstructor
public class OutboxRelayScheduler {

    private static final int MAX_RETRIES = 3;

    private final OutboxEventRepository outboxEventRepository;
    private final MessagePublisher messagePublisher;
    private final AtomicBoolean relayRunning = new AtomicBoolean(false);

    @Scheduled(fixedDelayString = "${engonow.outbox.relay-delay-ms:500}")
    public void processPendingOutboxEvents() {
        if (!relayRunning.compareAndSet(false, true)) {
            log.debug("[OUTBOX RELAY] Skipping overlapping relay execution");
            return;
        }

        try {
            List<OutboxEvent> pendingEvents;
            try {
                pendingEvents = outboxEventRepository
                        .findTop100ByStatusOrderByCreatedAtAsc(OutboxStatus.PENDING);
            } catch (Exception ex) {
                log.error(
                        "[OUTBOX RELAY] Failed to load pending outbox events: {}",
                        errorMessage(ex),
                        ex);
                return;
            }

            if (pendingEvents.isEmpty()) {
                return;
            }

            for (OutboxEvent event : pendingEvents) {
                processEvent(event);
            }
        } finally {
            relayRunning.set(false);
        }
    }

    private void processEvent(OutboxEvent event) {
        try {
            messagePublisher.publish(event);
            event.setStatus(OutboxStatus.SENT);
            event.setErrorMessage(null);
            outboxEventRepository.save(event);
        } catch (Exception ex) {
            log.error(
                    "[OUTBOX RELAY] Failed to publish outbox event id={}: {}",
                    event.getId(),
                    errorMessage(ex));
            recordFailure(event, ex);
        }
    }

    private void recordFailure(OutboxEvent event, Exception failure) {
        int retryCount = event.getRetryCount() + 1;
        event.setRetryCount(retryCount);
        event.setErrorMessage(errorMessage(failure));
        event.setStatus(
                retryCount >= MAX_RETRIES
                        ? OutboxStatus.FAILED
                        : OutboxStatus.PENDING);

        try {
            outboxEventRepository.save(event);
        } catch (Exception persistenceFailure) {
            log.error(
                    "[OUTBOX RELAY] Failed to persist failure state for outbox event id={}: {}",
                    event.getId(),
                    errorMessage(persistenceFailure),
                    persistenceFailure);
        }
    }

    private String errorMessage(Exception exception) {
        return exception.getMessage() != null
                ? exception.getMessage()
                : exception.getClass().getSimpleName();
    }
}
