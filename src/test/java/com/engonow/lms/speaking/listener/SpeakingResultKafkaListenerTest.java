package com.engonow.lms.speaking.listener;

import com.engonow.lms.entity.SpeakingSessionResult;
import com.engonow.lms.enums.SpeakingEvaluationStatus;
import com.engonow.lms.repository.InboxEventRepository;
import com.engonow.lms.repository.SpeakingSessionResultRepository;
import com.engonow.lms.speaking.event.SpeakingEvaluationCompletedPayload;
import com.engonow.lms.speaking.event.SpeakingEvaluationFailedPayload;
import com.engonow.lms.writing.event.EventEnvelope;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.Spy;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.kafka.support.Acknowledgment;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
public class SpeakingResultKafkaListenerTest {

    @Mock
    private SpeakingSessionResultRepository speakingSessionResultRepository;

    @Mock
    private InboxEventRepository inboxEventRepository;

    @Mock
    private Acknowledgment acknowledgment;

    @Spy
    private ObjectMapper objectMapper = new ObjectMapper().findAndRegisterModules();

    @InjectMocks
    private SpeakingResultKafkaListener listener;

    private UUID attemptId;
    private UUID eventId;
    private UUID idempotencyKey;

    @BeforeEach
    void setUp() {
        attemptId = UUID.randomUUID();
        eventId = UUID.randomUUID();
        idempotencyKey = UUID.randomUUID();
    }

    @Test
    @DisplayName("Successfully processes completed speaking evaluation with Cambridge score rounding")
    void testHandleEvaluationCompletedSuccess() throws Exception {
        JsonNode feedbackDetail = objectMapper.readTree("{\"speechMetrics\":{\"wpm\":140.0}}");
        // (7.0 + 7.5 + 7.0 + 7.0) / 4 = 7.125 -> Cambridge rounds to 7.0
        SpeakingEvaluationCompletedPayload payload = new SpeakingEvaluationCompletedPayload(
            attemptId,
            new BigDecimal("7.0"),
            new BigDecimal("7.5"),
            new BigDecimal("7.0"),
            new BigDecimal("7.0"),
            new BigDecimal("7.0"),
            feedbackDetail
        );

        EventEnvelope<SpeakingEvaluationCompletedPayload> envelope = new EventEnvelope<>(
            eventId,
            idempotencyKey,
            "SPEAKING_EVALUATION_COMPLETED",
            "1.0",
            Instant.now(),
            Instant.now(),
            "trace-1",
            attemptId.toString(),
            "engonow-ai-speaking-worker",
            0,
            payload
        );

        String json = objectMapper.writeValueAsString(envelope);
        RecordHeaders headers = new RecordHeaders();
        headers.add("traceId", "trace-1".getBytes(StandardCharsets.UTF_8));
        headers.add("correlationId", attemptId.toString().getBytes(StandardCharsets.UTF_8));

        ConsumerRecord<String, String> record = new ConsumerRecord<>(
            "engonow.speaking.evaluation-completed.v1",
            0,
            10L,
            attemptId.toString(),
            json
        );

        when(inboxEventRepository.tryAcquireInbox(eq(eventId), eq(idempotencyKey), eq("SPEAKING_EVALUATION_COMPLETED"), eq("engonow-ai-speaking-worker"), any()))
            .thenReturn(1);

        SpeakingSessionResult existingSession = SpeakingSessionResult.builder()
            .sessionId(attemptId.toString())
            .evaluationStatus(SpeakingEvaluationStatus.PENDING)
            .build();

        when(speakingSessionResultRepository.findBySessionId(attemptId.toString()))
            .thenReturn(Optional.of(existingSession));

        listener.handleEvaluationCompleted(record, acknowledgment);

        ArgumentCaptor<SpeakingSessionResult> savedCaptor = ArgumentCaptor.forClass(SpeakingSessionResult.class);
        verify(speakingSessionResultRepository).save(savedCaptor.capture());
        SpeakingSessionResult saved = savedCaptor.getValue();

        assertThat(saved.getEvaluationStatus()).isEqualTo(SpeakingEvaluationStatus.SUCCESS);
        assertThat(saved.getIsComplete()).isTrue();
        assertThat(saved.getAiScore()).isEqualByComparingTo("7.5");
        assertThat(saved.getFluencyScore()).isEqualByComparingTo("7.0");
        assertThat(saved.getLexicalScore()).isEqualByComparingTo("7.5");
        verify(acknowledgment).acknowledge();
    }

    @Test
    @DisplayName("Duplicate speaking evaluation completed event is skipped via Inbox check")
    void testHandleEvaluationCompletedDuplicateDeduplicated() throws Exception {
        JsonNode feedbackDetail = objectMapper.readTree("{\"speechMetrics\":{}}");
        SpeakingEvaluationCompletedPayload payload = new SpeakingEvaluationCompletedPayload(
            attemptId,
            new BigDecimal("6.0"),
            new BigDecimal("6.0"),
            new BigDecimal("6.0"),
            new BigDecimal("6.0"),
            new BigDecimal("6.0"),
            feedbackDetail
        );

        EventEnvelope<SpeakingEvaluationCompletedPayload> envelope = new EventEnvelope<>(
            eventId,
            idempotencyKey,
            "SPEAKING_EVALUATION_COMPLETED",
            "1.0",
            Instant.now(),
            Instant.now(),
            "trace-dup",
            attemptId.toString(),
            "worker",
            0,
            payload
        );

        String json = objectMapper.writeValueAsString(envelope);
        ConsumerRecord<String, String> record = new ConsumerRecord<>(
            "engonow.speaking.evaluation-completed.v1",
            0,
            11L,
            attemptId.toString(),
            json
        );

        // Deduplication returns 0 (already in inbox)
        when(inboxEventRepository.tryAcquireInbox(eq(eventId), eq(idempotencyKey), any(), any(), any()))
            .thenReturn(0);

        listener.handleEvaluationCompleted(record, acknowledgment);

        verify(speakingSessionResultRepository, never()).save(any());
        verify(acknowledgment).acknowledge();
    }

    @Test
    @DisplayName("Handles speaking evaluation failure event and marks session as FAILED")
    void testHandleEvaluationFailed() throws Exception {
        SpeakingEvaluationFailedPayload payload = new SpeakingEvaluationFailedPayload(
            attemptId,
            "AUDIO_TOO_SHORT",
            "Audio duration less than 10 seconds",
            false,
            Instant.now()
        );

        EventEnvelope<SpeakingEvaluationFailedPayload> envelope = new EventEnvelope<>(
            eventId,
            idempotencyKey,
            "SPEAKING_EVALUATION_FAILED",
            "1.0",
            Instant.now(),
            Instant.now(),
            "trace-fail",
            attemptId.toString(),
            "worker",
            0,
            payload
        );

        String json = objectMapper.writeValueAsString(envelope);
        ConsumerRecord<String, String> record = new ConsumerRecord<>(
            "engonow.speaking.evaluation-failed.v1",
            0,
            12L,
            attemptId.toString(),
            json
        );

        SpeakingSessionResult existingSession = SpeakingSessionResult.builder()
            .sessionId(attemptId.toString())
            .evaluationStatus(SpeakingEvaluationStatus.PENDING)
            .build();

        when(speakingSessionResultRepository.findBySessionId(attemptId.toString()))
            .thenReturn(Optional.of(existingSession));

        listener.handleEvaluationFailed(record, acknowledgment);

        verify(speakingSessionResultRepository).save(existingSession);
        assertThat(existingSession.getEvaluationStatus()).isEqualTo(SpeakingEvaluationStatus.FAILED);
        verify(acknowledgment).acknowledge();
    }
}
