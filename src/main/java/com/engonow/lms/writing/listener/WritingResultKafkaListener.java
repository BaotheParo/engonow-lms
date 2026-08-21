package com.engonow.lms.writing.listener;

import com.engonow.lms.writing.event.EventEnvelope;
import com.engonow.lms.writing.event.WritingEvaluationCompletedPayload;
import com.engonow.lms.writing.event.WritingEvaluationFailedPayload;
import com.engonow.lms.writing.service.WritingSubmissionService;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.slf4j.MDC;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;

@Component
@RequiredArgsConstructor
@Slf4j
public class WritingResultKafkaListener {

    private final WritingSubmissionService writingSubmissionService;
    private final ObjectMapper objectMapper;

    @KafkaListener(
        topics = "engonow.writing.evaluation-completed.v1",
        groupId = "engonow-lms-writing-consumer-v1",
        containerFactory = "writingKafkaListenerContainerFactory"
    )
    public void handleEvaluationCompleted(ConsumerRecord<String, String> record, Acknowledgment ack) {
        String traceId = extractHeader(record, "traceId");
        if (traceId == null) {
            traceId = extractHeader(record, "traceparent");
        }
        String correlationId = extractHeader(record, "correlationId");

        if (traceId != null) {
            MDC.put("traceId", traceId);
        }
        if (correlationId != null) {
            MDC.put("correlationId", correlationId);
        }

        try {
            log.info("[KAFKA CONSUMER] Received evaluation completed event on partition {} offset {}",
                record.partition(), record.offset());

            EventEnvelope<WritingEvaluationCompletedPayload> envelope = objectMapper.readValue(
                record.value(),
                new TypeReference<EventEnvelope<WritingEvaluationCompletedPayload>>() {}
            );

            writingSubmissionService.processEvaluationCompletedEvent(envelope, record.value());

            if (ack != null) {
                ack.acknowledge();
            }
        } catch (Exception ex) {
            log.error("[KAFKA CONSUMER] Error processing evaluation completed event from partition {} offset {}: {}",
                record.partition(), record.offset(), ex.getMessage(), ex);
            throw new RuntimeException("Failed to process evaluation completed event", ex);
        } finally {
            MDC.remove("traceId");
            MDC.remove("correlationId");
        }
    }

    @KafkaListener(
        topics = "engonow.writing.evaluation-failed.v1",
        groupId = "engonow-lms-writing-consumer-v1",
        containerFactory = "writingKafkaListenerContainerFactory"
    )
    public void handleEvaluationFailed(ConsumerRecord<String, String> record, Acknowledgment ack) {
        String traceId = extractHeader(record, "traceId");
        if (traceId == null) {
            traceId = extractHeader(record, "traceparent");
        }
        String correlationId = extractHeader(record, "correlationId");

        if (traceId != null) {
            MDC.put("traceId", traceId);
        }
        if (correlationId != null) {
            MDC.put("correlationId", correlationId);
        }

        try {
            log.warn("[KAFKA CONSUMER] Received evaluation failed event on partition {} offset {}",
                record.partition(), record.offset());

            EventEnvelope<WritingEvaluationFailedPayload> envelope = objectMapper.readValue(
                record.value(),
                new TypeReference<EventEnvelope<WritingEvaluationFailedPayload>>() {}
            );

            writingSubmissionService.processEvaluationFailedEvent(envelope, record.value());

            if (ack != null) {
                ack.acknowledge();
            }
        } catch (Exception ex) {
            log.error("[KAFKA CONSUMER] Error processing evaluation failed event from partition {} offset {}: {}",
                record.partition(), record.offset(), ex.getMessage(), ex);
            throw new RuntimeException("Failed to process evaluation failed event", ex);
        } finally {
            MDC.remove("traceId");
            MDC.remove("correlationId");
        }
    }

    private String extractHeader(ConsumerRecord<String, String> record, String key) {
        if (record.headers() == null) return null;
        Header header = record.headers().lastHeader(key);
        return header != null ? new String(header.value(), StandardCharsets.UTF_8) : null;
    }
}
