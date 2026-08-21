package com.engonow.lms.writing.listener;

import com.engonow.lms.entity.OutboxEvent;
import com.engonow.lms.enums.OutboxStatus;
import com.engonow.lms.repository.OutboxEventRepository;
import com.engonow.lms.writing.event.OutboxEventCreatedLocalEvent;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.apache.kafka.common.TopicPartition;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OutboxEagerDispatcherListenerTest {

    @Mock
    private KafkaTemplate<String, String> kafkaTemplate;

    @Mock
    private OutboxEventRepository outboxEventRepository;

    @Mock
    private org.springframework.transaction.support.TransactionTemplate transactionTemplate;

    @Test
    @DisplayName("handleOutboxCreated sends message to Kafka and marks OutboxEvent as PUBLISHED")
    void handleOutboxCreated_Success() {
        // Configure TransactionTemplate mock to execute callback immediately
        when(transactionTemplate.execute(any())).thenAnswer(invocation -> {
            org.springframework.transaction.support.TransactionCallback<?> callback = invocation.getArgument(0);
            return callback.doInTransaction(null);
        });

        OutboxEagerDispatcherListener listener = new OutboxEagerDispatcherListener(
            Optional.of(kafkaTemplate),
            outboxEventRepository,
            transactionTemplate
        );

        UUID outboxId = UUID.randomUUID();
        String topic = "engonow.writing.evaluation-requested.v1";
        String key = UUID.randomUUID().toString();
        String payload = "{\"eventId\":\"" + UUID.randomUUID() + "\"}";

        OutboxEventCreatedLocalEvent event = new OutboxEventCreatedLocalEvent(
            outboxId,
            topic,
            key,
            payload,
            Map.of("correlationId", key.getBytes(StandardCharsets.UTF_8))
        );

        RecordMetadata metadata = new RecordMetadata(
            new TopicPartition(topic, 0),
            0L,
            0,
            System.currentTimeMillis(),
            0,
            0
        );
        SendResult<String, String> sendResult = new SendResult<>(null, metadata);
        CompletableFuture<SendResult<String, String>> future = CompletableFuture.completedFuture(sendResult);

        when(kafkaTemplate.send(any(ProducerRecord.class))).thenReturn(future);

        OutboxEvent outboxEntity = OutboxEvent.builder()
            .id(outboxId)
            .status(OutboxStatus.PENDING)
            .build();
        when(outboxEventRepository.findById(outboxId)).thenReturn(Optional.of(outboxEntity));

        listener.handleOutboxCreated(event);

        ArgumentCaptor<ProducerRecord<String, String>> recordCaptor = ArgumentCaptor.forClass(ProducerRecord.class);
        verify(kafkaTemplate).send(recordCaptor.capture());
        ProducerRecord<String, String> sentRecord = recordCaptor.getValue();
        assertThat(sentRecord.topic()).isEqualTo(topic);
        assertThat(sentRecord.key()).isEqualTo(key);
        assertThat(sentRecord.value()).isEqualTo(payload);

        verify(outboxEventRepository).save(outboxEntity);
        assertThat(outboxEntity.getStatus()).isEqualTo(OutboxStatus.PUBLISHED);
        assertThat(outboxEntity.getPublishedAt()).isNotNull();
    }

    @Test
    @DisplayName("handleOutboxCreated handles absent KafkaTemplate gracefully")
    void handleOutboxCreated_NoKafkaTemplate() {
        OutboxEagerDispatcherListener listener = new OutboxEagerDispatcherListener(
            Optional.empty(),
            outboxEventRepository,
            transactionTemplate
        );

        OutboxEventCreatedLocalEvent event = new OutboxEventCreatedLocalEvent(
            UUID.randomUUID(),
            "test-topic",
            "key",
            "{}",
            Map.of()
        );

        listener.handleOutboxCreated(event);

        verify(outboxEventRepository, never()).findById(any());
        verify(outboxEventRepository, never()).save(any());
    }
}
