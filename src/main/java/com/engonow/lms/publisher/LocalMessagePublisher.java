package com.engonow.lms.publisher;

import com.engonow.lms.entity.OutboxEvent;
import com.engonow.lms.event.SpeakingResultLocalEvent;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
@Slf4j
@RequiredArgsConstructor
@ConditionalOnProperty(
    name = "engonow.broker.type",
    havingValue = "LOCAL",
    matchIfMissing = true
)
public class LocalMessagePublisher implements MessagePublisher {

    private final ApplicationEventPublisher applicationEventPublisher;

    @Override
    public void publish(OutboxEvent event) {
        log.info(
                "[LOCAL BROKER] Publishing outbox event id={} aggregateId={} to local Spring event stream",
                event.getId(),
                event.getAggregateId());

        applicationEventPublisher.publishEvent(LocalOutboxMessage.from(event));
    }

    /**
     * Publishes a speaking result into the in-process result channel.
     *
     * @param jsonPayload serialized Python worker result
     */
    public void publishResult(String jsonPayload) {
        log.info("[LOCAL BROKER] Publishing speaking result to local Spring event stream");
        applicationEventPublisher.publishEvent(new SpeakingResultLocalEvent(jsonPayload));
    }

    public record LocalOutboxMessage(
        java.util.UUID eventId,
        String aggregateType,
        String aggregateId,
        String eventType,
        String payload
    ) {
        private static LocalOutboxMessage from(OutboxEvent event) {
            return new LocalOutboxMessage(
                    event.getId(),
                    event.getAggregateType(),
                    event.getAggregateId(),
                    event.getEventType(),
                    event.getPayload());
        }
    }
}
