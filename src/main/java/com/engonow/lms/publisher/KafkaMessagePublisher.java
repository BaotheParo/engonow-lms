package com.engonow.lms.publisher;

import com.engonow.lms.entity.OutboxEvent;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

import java.util.Optional;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

@Component
@Slf4j
@ConditionalOnProperty(name = "engonow.broker.type", havingValue = "KAFKA")
public class KafkaMessagePublisher implements MessagePublisher {

    private static final long PUBLISH_TIMEOUT_SECONDS = 10;

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final String topic;

    public KafkaMessagePublisher(
            Optional<KafkaTemplate<String, String>> kafkaTemplate,
            @Value("${engonow.broker.kafka.topic:ielts-speaking-requests}")
            String topic) {
        this.kafkaTemplate = kafkaTemplate.orElse(null);
        this.topic = topic;
    }

    @Override
    public void publish(OutboxEvent event) {
        if (kafkaTemplate == null) {
            throw new IllegalStateException(
                    "Kafka broker is selected but no KafkaTemplate is configured");
        }

        try {
            kafkaTemplate
                    .send(topic, event.getAggregateId(), event.getPayload())
                    .get(PUBLISH_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            log.info(
                    "[KAFKA BROKER] Published outbox event id={} aggregateId={} topic={}",
                    event.getId(),
                    event.getAggregateId(),
                    topic);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Interrupted while publishing outbox event " + event.getId(),
                    ex);
        } catch (ExecutionException | TimeoutException ex) {
            throw new IllegalStateException(
                    "Failed to publish outbox event " + event.getId()
                            + " to Kafka topic " + topic,
                    ex);
        }
    }
}
