package com.engonow.lms.speaking.listener;

import com.engonow.lms.entity.SpeakingSessionResult;
import com.engonow.lms.enums.SpeakingEvaluationStatus;
import com.engonow.lms.repository.InboxEventRepository;
import com.engonow.lms.repository.SpeakingSessionResultRepository;
import com.engonow.lms.speaking.event.SpeakingEvaluationCompletedPayload;
import com.engonow.lms.speaking.event.SpeakingEvaluationFailedPayload;
import com.engonow.lms.writing.event.EventEnvelope;
import com.engonow.lms.writing.util.CambridgeRoundingUtil;
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
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;

@Component
@RequiredArgsConstructor
@Slf4j
public class SpeakingResultKafkaListener {

    private final SpeakingSessionResultRepository speakingSessionResultRepository;
    private final InboxEventRepository inboxEventRepository;
    private final ObjectMapper objectMapper;

    @KafkaListener(
        topics = "engonow.speaking.evaluation-completed.v1",
        groupId = "engonow-lms-speaking-consumer-v1"
    )
    @Transactional
    public void handleEvaluationCompleted(ConsumerRecord<String, String> record, Acknowledgment ack) {
        String traceId = extractHeader(record, "traceId");
        String correlationId = extractHeader(record, "correlationId");

        if (traceId != null) MDC.put("traceId", traceId);
        if (correlationId != null) MDC.put("correlationId", correlationId);

        try {
            log.info("[SPEAKING CONSUMER] Received speaking evaluation completed event on partition {} offset {}",
                record.partition(), record.offset());

            EventEnvelope<SpeakingEvaluationCompletedPayload> envelope = objectMapper.readValue(
                record.value(),
                new TypeReference<EventEnvelope<SpeakingEvaluationCompletedPayload>>() {}
            );

            // 1. Atomic Inbox Deduplication
            int acquired = inboxEventRepository.tryAcquireInbox(
                envelope.eventId(),
                envelope.idempotencyKey(),
                envelope.eventType(),
                envelope.source(),
                record.value()
            );

            if (acquired == 0) {
                log.warn("[DUPLICATE EVENT] IdempotencyKey {} already processed in Speaking Inbox. Skipping.",
                    envelope.idempotencyKey());
                if (ack != null) ack.acknowledge();
                return;
            }

            // 2. Update SpeakingSessionResult
            SpeakingEvaluationCompletedPayload payload = envelope.payload();
            String sessionId = payload.attemptId().toString();

            SpeakingSessionResult result = speakingSessionResultRepository.findBySessionId(sessionId)
                .orElseGet(() -> SpeakingSessionResult.builder().sessionId(sessionId).build());

            BigDecimal overallBand = CambridgeRoundingUtil.calculateOverallBand(
                payload.fluencyCoherenceScore(),
                payload.lexicalResourceScore(),
                payload.grammaticalRangeScore(),
                payload.pronunciationScore()
            );

            result.setFluencyScore(payload.fluencyCoherenceScore());
            result.setLexicalScore(payload.lexicalResourceScore());
            result.setGrammarScore(payload.grammaticalRangeScore());
            result.setPronunciationScore(payload.pronunciationScore());
            result.setAiScore(overallBand);
            result.setEvaluationStatus(SpeakingEvaluationStatus.SUCCESS);
            result.setIsComplete(true);
            if (payload.feedbackDetail() != null) {
                result.setFeedbackText(payload.feedbackDetail().toString());
            }

            speakingSessionResultRepository.save(result);
            log.info("[SPEAKING CONSUMER] Successfully saved SpeakingSessionResult for attempt {}, overallBand={}",
                sessionId, overallBand);

            if (ack != null) {
                ack.acknowledge();
            }
        } catch (Exception ex) {
            log.error("[SPEAKING CONSUMER] Error processing evaluation completed event: {}", ex.getMessage(), ex);
            throw new RuntimeException("Failed to process speaking evaluation completed event", ex);
        } finally {
            MDC.remove("traceId");
            MDC.remove("correlationId");
        }
    }

    @KafkaListener(
        topics = "engonow.speaking.evaluation-failed.v1",
        groupId = "engonow-lms-speaking-consumer-v1"
    )
    @Transactional
    public void handleEvaluationFailed(ConsumerRecord<String, String> record, Acknowledgment ack) {
        try {
            log.warn("[SPEAKING CONSUMER] Received speaking evaluation failed event on partition {} offset {}",
                record.partition(), record.offset());

            EventEnvelope<SpeakingEvaluationFailedPayload> envelope = objectMapper.readValue(
                record.value(),
                new TypeReference<EventEnvelope<SpeakingEvaluationFailedPayload>>() {}
            );

            String sessionId = envelope.payload().attemptId().toString();
            speakingSessionResultRepository.findBySessionId(sessionId).ifPresent(result -> {
                result.setEvaluationStatus(SpeakingEvaluationStatus.FAILED);
                speakingSessionResultRepository.save(result);
                log.info("[SPEAKING CONSUMER] Marked attempt {} as FAILED", sessionId);
            });

            if (ack != null) {
                ack.acknowledge();
            }
        } catch (Exception ex) {
            log.error("[SPEAKING CONSUMER] Error processing evaluation failed event: {}", ex.getMessage(), ex);
        }
    }

    private String extractHeader(ConsumerRecord<?, ?> record, String headerName) {
        if (record.headers() == null) return null;
        Header header = record.headers().lastHeader(headerName);
        return header != null ? new String(header.value(), StandardCharsets.UTF_8) : null;
    }
}
