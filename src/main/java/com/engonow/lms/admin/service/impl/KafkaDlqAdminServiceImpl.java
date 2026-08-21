package com.engonow.lms.admin.service.impl;

import com.engonow.lms.admin.dto.DlqReplayRequestDTO;
import com.engonow.lms.admin.dto.DlqReplayResponseDTO;
import com.engonow.lms.admin.service.KafkaDlqAdminService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.PartitionInfo;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

@Service
@RequiredArgsConstructor
@Slf4j
public class KafkaDlqAdminServiceImpl implements KafkaDlqAdminService {

    private final ConsumerFactory<String, String> consumerFactory;
    private final KafkaTemplate<String, String> kafkaTemplate;

    private record PendingDispatch(
        ConsumerRecord<String, String> originalRecord,
        CompletableFuture<SendResult<String, String>> sendFuture,
        String eventId
    ) {}

    @Override
    public DlqReplayResponseDTO replayDlqMessages(DlqReplayRequestDTO request) {
        if (request.dlqTopic().trim().equalsIgnoreCase(request.targetTopic().trim())) {
            throw new IllegalArgumentException("dlqTopic and targetTopic cannot be the same topic: " + request.dlqTopic());
        }

        log.info("[ADMIN DLQ REPLAY] Initiating replay from dlqTopic={} to targetTopic={} maxMessages={}",
            request.dlqTopic(), request.targetTopic(), request.maxMessages());

        String tempGroupId = "engonow-dlq-replay-admin-" + UUID.randomUUID();

        try (Consumer<String, String> consumer = consumerFactory.createConsumer(tempGroupId, "admin-replay-client")) {
            List<PartitionInfo> partitionInfos = consumer.partitionsFor(request.dlqTopic());
            if (partitionInfos == null || partitionInfos.isEmpty()) {
                log.warn("[ADMIN DLQ REPLAY] No partitions found for DLQ topic {}", request.dlqTopic());
                return new DlqReplayResponseDTO(0, 0, 0, List.of());
            }

            List<TopicPartition> topicPartitions = partitionInfos.stream()
                .map(p -> new TopicPartition(p.topic(), p.partition()))
                .toList();

            consumer.assign(topicPartitions);

            int messagesRead = 0;
            int messagesSkipped = 0;
            List<ConsumerRecord<String, String>> recordsToProcess = new ArrayList<>();

            int pollAttempts = 3;
            while (pollAttempts > 0 && recordsToProcess.size() < request.maxMessages()) {
                ConsumerRecords<String, String> polled = consumer.poll(Duration.ofMillis(1000));
                if (polled.isEmpty()) {
                    pollAttempts--;
                } else {
                    for (ConsumerRecord<String, String> record : polled) {
                        recordsToProcess.add(record);
                        if (recordsToProcess.size() >= request.maxMessages()) {
                            break;
                        }
                    }
                }
            }

            messagesRead = recordsToProcess.size();
            List<PendingDispatch> pendingDispatches = new ArrayList<>();

            for (ConsumerRecord<String, String> record : recordsToProcess) {
                String correlationId = extractHeader(record, "correlationId");
                String eventId = extractHeader(record, "eventId");

                if (request.filterCorrelationId() != null && !request.filterCorrelationId().isBlank()) {
                    if (!Objects.equals(request.filterCorrelationId(), correlationId)) {
                        log.debug("[ADMIN DLQ REPLAY] Skipping message due to correlationId filter mismatch: expected={}, found={}",
                            request.filterCorrelationId(), correlationId);
                        messagesSkipped++;
                        continue;
                    }
                }

                ProducerRecord<String, String> replayRecord = new ProducerRecord<>(
                    request.targetTopic(),
                    record.key(),
                    record.value()
                );

                if (record.headers() != null) {
                    for (Header header : record.headers()) {
                        replayRecord.headers().add(header.key(), header.value());
                    }
                }

                replayRecord.headers().add("x-replayed-by-admin", "true".getBytes(StandardCharsets.UTF_8));
                replayRecord.headers().add("x-replayed-at", Instant.now().toString().getBytes(StandardCharsets.UTF_8));

                // Dispatch asynchronously without blocking in the loop
                CompletableFuture<SendResult<String, String>> future = kafkaTemplate.send(replayRecord);
                pendingDispatches.add(new PendingDispatch(
                    record,
                    future,
                    eventId != null ? eventId : (record.key() != null ? record.key() : "unknown")
                ));
            }

            // Wait for all asynchronous dispatches in the batch to complete
            List<String> replayedEventIds = new ArrayList<>();
            Map<TopicPartition, OffsetAndMetadata> offsetsToCommit = new HashMap<>();

            if (!pendingDispatches.isEmpty()) {
                CompletableFuture<?>[] futuresArray = pendingDispatches.stream()
                    .map(PendingDispatch::sendFuture)
                    .toArray(CompletableFuture[]::new);

                try {
                    CompletableFuture.allOf(futuresArray).get(15, TimeUnit.SECONDS);
                } catch (Exception ex) {
                    log.error("[ADMIN DLQ REPLAY] Batch asynchronous dispatch failed: {}", ex.getMessage(), ex);
                    throw new RuntimeException("Failed to complete batch replay to target topic", ex);
                }

                for (PendingDispatch dispatch : pendingDispatches) {
                    replayedEventIds.add(dispatch.eventId());
                    TopicPartition tp = new TopicPartition(
                        dispatch.originalRecord().topic(),
                        dispatch.originalRecord().partition()
                    );
                    long nextOffset = dispatch.originalRecord().offset() + 1;
                    offsetsToCommit.compute(tp, (k, current) ->
                        (current == null || nextOffset > current.offset())
                            ? new OffsetAndMetadata(nextOffset)
                            : current
                    );
                }

                // Monotonically commit offsets strictly for successfully dispatched messages
                consumer.commitSync(offsetsToCommit);
            }

            int messagesReplayed = replayedEventIds.size();
            log.info("[ADMIN DLQ REPLAY] Completed batch replay. Read={}, Replayed={}, Skipped={}",
                messagesRead, messagesReplayed, messagesSkipped);

            return new DlqReplayResponseDTO(
                messagesRead,
                messagesReplayed,
                messagesSkipped,
                replayedEventIds
            );
        }
    }

    private String extractHeader(ConsumerRecord<String, String> record, String key) {
        if (record.headers() == null) return null;
        Header header = record.headers().lastHeader(key);
        return header != null ? new String(header.value(), StandardCharsets.UTF_8) : null;
    }
}
