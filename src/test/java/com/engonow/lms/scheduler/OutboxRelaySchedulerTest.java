package com.engonow.lms.scheduler;

import com.engonow.lms.entity.OutboxEvent;
import com.engonow.lms.enums.OutboxStatus;
import com.engonow.lms.publisher.MessagePublisher;
import com.engonow.lms.repository.OutboxEventRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;

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

    @Test
    void publishesPendingEventExactlyOnceAndMarksItSent() {
        OutboxEvent event = pendingEvent(1L, 0);
        when(outboxEventRepository.findTop100ByStatusOrderByCreatedAtAsc(
                OutboxStatus.PENDING))
                .thenReturn(List.of(event));
        OutboxRelayScheduler scheduler =
                new OutboxRelayScheduler(outboxEventRepository, messagePublisher);

        scheduler.processPendingOutboxEvents();

        verify(messagePublisher, times(1)).publish(event);
        verify(outboxEventRepository).save(event);
        assertEquals(OutboxStatus.SENT, event.getStatus());
        assertEquals(0, event.getRetryCount());
        assertNull(event.getErrorMessage());
    }

    @Test
    void marksEventFailedWhenThirdPublishAttemptFails() {
        OutboxEvent event = pendingEvent(2L, 2);
        when(outboxEventRepository.findTop100ByStatusOrderByCreatedAtAsc(
                OutboxStatus.PENDING))
                .thenReturn(List.of(event));
        doThrow(new IllegalStateException("Kafka unavailable"))
                .when(messagePublisher)
                .publish(event);
        OutboxRelayScheduler scheduler =
                new OutboxRelayScheduler(outboxEventRepository, messagePublisher);

        scheduler.processPendingOutboxEvents();

        verify(messagePublisher).publish(event);
        verify(outboxEventRepository).save(event);
        assertEquals(3, event.getRetryCount());
        assertEquals(OutboxStatus.FAILED, event.getStatus());
        assertEquals("Kafka unavailable", event.getErrorMessage());
    }

    @Test
    void keepsEventPendingBeforeRetryLimit() {
        OutboxEvent event = pendingEvent(3L, 0);
        when(outboxEventRepository.findTop100ByStatusOrderByCreatedAtAsc(
                OutboxStatus.PENDING))
                .thenReturn(List.of(event));
        doThrow(new IllegalArgumentException("Invalid payload"))
                .when(messagePublisher)
                .publish(event);
        OutboxRelayScheduler scheduler =
                new OutboxRelayScheduler(outboxEventRepository, messagePublisher);

        scheduler.processPendingOutboxEvents();

        assertEquals(1, event.getRetryCount());
        assertEquals(OutboxStatus.PENDING, event.getStatus());
        assertEquals("Invalid payload", event.getErrorMessage());
    }

    @Test
    void failedEventDoesNotPreventLaterEventsFromBeingPublished() {
        OutboxEvent badEvent = pendingEvent(4L, 0);
        OutboxEvent goodEvent = pendingEvent(5L, 0);
        when(outboxEventRepository.findTop100ByStatusOrderByCreatedAtAsc(
                OutboxStatus.PENDING))
                .thenReturn(List.of(badEvent, goodEvent));
        doAnswer(invocation -> {
            if (invocation.getArgument(0) == badEvent) {
                throw new IllegalStateException("Poisoned event");
            }
            return null;
        }).when(messagePublisher).publish(any(OutboxEvent.class));
        OutboxRelayScheduler scheduler =
                new OutboxRelayScheduler(outboxEventRepository, messagePublisher);

        scheduler.processPendingOutboxEvents();

        verify(messagePublisher).publish(badEvent);
        verify(messagePublisher).publish(goodEvent);
        assertEquals(OutboxStatus.PENDING, badEvent.getStatus());
        assertEquals(1, badEvent.getRetryCount());
        assertEquals(OutboxStatus.SENT, goodEvent.getStatus());
    }

    private static OutboxEvent pendingEvent(Long id, int retryCount) {
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
