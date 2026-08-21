package com.engonow.lms.scheduler;

import com.engonow.lms.entity.OutboxEvent;
import com.engonow.lms.enums.OutboxStatus;
import com.engonow.lms.metrics.TelemetryManager;
import com.engonow.lms.publisher.MessagePublisher;
import com.engonow.lms.repository.OutboxEventRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OutboxRelaySchedulerTest {

    @Mock
    private OutboxEventRepository outboxEventRepository;

    @Mock
    private MessagePublisher messagePublisher;

    @Mock
    private TelemetryManager telemetryManager;

    @Mock
    private org.springframework.transaction.support.TransactionTemplate transactionTemplate;

    private void mockTransactionTemplate() {
        when(transactionTemplate.execute(any())).thenAnswer(invocation -> {
            org.springframework.transaction.support.TransactionCallback<?> callback = invocation.getArgument(0);
            return callback.doInTransaction(null);
        });
    }

    @Test
    void publishesPendingEventExactlyOnceAndMarksItSent() {
        mockTransactionTemplate();
        OutboxEvent event = pendingEvent(UUID.randomUUID(), 0);
        when(outboxEventRepository.findTop100ByStatusOrderByCreatedAtAsc(
                OutboxStatus.PENDING))
                .thenReturn(List.of(event));
        when(outboxEventRepository.findById(event.getId())).thenReturn(Optional.of(event));

        OutboxRelayScheduler scheduler =
                new OutboxRelayScheduler(
                        outboxEventRepository,
                        messagePublisher,
                        telemetryManager,
                        transactionTemplate);

        scheduler.processPendingOutboxEvents();

        verify(messagePublisher, times(1)).publish(event);
        verify(outboxEventRepository).save(event);
        assertEquals(OutboxStatus.PUBLISHED, event.getStatus());
        assertEquals(0, event.getRetryCount());
        assertNull(event.getErrorMessage());
    }

    @Test
    void marksEventFailedWhenThirdPublishAttemptFails() {
        mockTransactionTemplate();
        OutboxEvent event = pendingEvent(UUID.randomUUID(), 2);
        when(outboxEventRepository.findTop100ByStatusOrderByCreatedAtAsc(
                OutboxStatus.PENDING))
                .thenReturn(List.of(event));
        when(outboxEventRepository.findById(event.getId())).thenReturn(Optional.of(event));

        doThrow(new IllegalStateException("Kafka unavailable"))
                .when(messagePublisher)
                .publish(event);

        OutboxRelayScheduler scheduler =
                new OutboxRelayScheduler(
                        outboxEventRepository,
                        messagePublisher,
                        telemetryManager,
                        transactionTemplate);

        scheduler.processPendingOutboxEvents();

        verify(messagePublisher).publish(event);
        verify(outboxEventRepository).save(event);
        assertEquals(3, event.getRetryCount());
        assertEquals(OutboxStatus.FAILED, event.getStatus());
        assertEquals("Kafka unavailable", event.getErrorMessage());
        verify(telemetryManager).incrementOutboxRelayErrors();
    }

    @Test
    void keepsEventPendingBeforeRetryLimit() {
        mockTransactionTemplate();
        OutboxEvent event = pendingEvent(UUID.randomUUID(), 0);
        when(outboxEventRepository.findTop100ByStatusOrderByCreatedAtAsc(
                OutboxStatus.PENDING))
                .thenReturn(List.of(event));
        when(outboxEventRepository.findById(event.getId())).thenReturn(Optional.of(event));

        doThrow(new IllegalArgumentException("Invalid payload"))
                .when(messagePublisher)
                .publish(event);

        OutboxRelayScheduler scheduler =
                new OutboxRelayScheduler(
                        outboxEventRepository,
                        messagePublisher,
                        telemetryManager,
                        transactionTemplate);

        scheduler.processPendingOutboxEvents();

        assertEquals(1, event.getRetryCount());
        assertEquals(OutboxStatus.PENDING, event.getStatus());
        assertEquals("Invalid payload", event.getErrorMessage());
        verify(telemetryManager).incrementOutboxRelayErrors();
    }

    @Test
    void failedEventDoesNotPreventLaterEventsFromBeingPublished() {
        mockTransactionTemplate();
        OutboxEvent badEvent = pendingEvent(UUID.randomUUID(), 0);
        OutboxEvent goodEvent = pendingEvent(UUID.randomUUID(), 0);
        when(outboxEventRepository.findTop100ByStatusOrderByCreatedAtAsc(
                OutboxStatus.PENDING))
                .thenReturn(List.of(badEvent, goodEvent));
        when(outboxEventRepository.findById(badEvent.getId())).thenReturn(Optional.of(badEvent));
        when(outboxEventRepository.findById(goodEvent.getId())).thenReturn(Optional.of(goodEvent));

        doAnswer(invocation -> {
            if (invocation.getArgument(0) == badEvent) {
                throw new IllegalStateException("Poisoned event");
            }
            return null;
        }).when(messagePublisher).publish(any(OutboxEvent.class));

        OutboxRelayScheduler scheduler =
                new OutboxRelayScheduler(
                        outboxEventRepository,
                        messagePublisher,
                        telemetryManager,
                        transactionTemplate);

        scheduler.processPendingOutboxEvents();

        verify(messagePublisher).publish(badEvent);
        verify(messagePublisher).publish(goodEvent);
        assertEquals(OutboxStatus.PENDING, badEvent.getStatus());
        assertEquals(1, badEvent.getRetryCount());
        assertEquals(OutboxStatus.PUBLISHED, goodEvent.getStatus());
        verify(telemetryManager).incrementOutboxRelayErrors();
    }

    private static OutboxEvent pendingEvent(UUID id, int retryCount) {
        return OutboxEvent.builder()
                .id(id)
                .aggregateType("SPEAKING_SESSION")
                .aggregateId("session-" + id)
                .eventType("SPEAKING_EVALUATION_REQUESTED")
                .payload("{\"sessionId\":\"session-" + id + "\"}")
                .status(OutboxStatus.PENDING)
                .retryCount(retryCount)
                .errorMessage("previous error")
                .build();
    }
}
