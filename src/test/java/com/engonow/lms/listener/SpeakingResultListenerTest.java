package com.engonow.lms.listener;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.engonow.lms.dto.SpeakingWebhookPayload;
import com.engonow.lms.enums.SpeakingEvaluationStatus;
import com.engonow.lms.repository.IdempotencyRepository;
import com.engonow.lms.service.WebhookService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class SpeakingResultListenerTest {

    private static final String SESSION_ID = "speaking-session-42";
    private static final String IDEMPOTENCY_KEY = "result_process:" + SESSION_ID;
    private static final long IDEMPOTENCY_TTL_MILLIS = 60_000L;

    @Mock
    private WebhookService webhookService;

    @Mock
    private IdempotencyRepository idempotencyRepository;

    private SpeakingResultListener listener;

    @BeforeEach
    void setUp() {
        listener = new SpeakingResultListener(
                new ObjectMapper(),
                webhookService,
                idempotencyRepository);
    }

    @Test
    void handleResultPayloadParsesAndPersistsValidResult() {
        when(idempotencyRepository.tryLock(
                IDEMPOTENCY_KEY,
                IDEMPOTENCY_TTL_MILLIS))
                .thenReturn(true);

        listener.handleResultPayload(successPayload());

        ArgumentCaptor<SpeakingWebhookPayload> payloadCaptor =
                ArgumentCaptor.forClass(SpeakingWebhookPayload.class);
        verify(webhookService).handleAiSpeakingCallback(payloadCaptor.capture());
        verify(idempotencyRepository).completeLock(
                IDEMPOTENCY_KEY,
                IDEMPOTENCY_TTL_MILLIS);

        SpeakingWebhookPayload payload = payloadCaptor.getValue();
        assertThat(payload.sessionId()).isEqualTo(SESSION_ID);
        assertThat(payload.pronunciationScore()).isEqualByComparingTo("7.5");
        assertThat(payload.fluencyScore()).isEqualByComparingTo("7.0");
        assertThat(payload.grammarScore()).isEqualByComparingTo("6.5");
        assertThat(payload.lexicalScore()).isEqualByComparingTo("7.5");
        assertThat(payload.status()).isEqualTo(SpeakingEvaluationStatus.SUCCESS);
        assertThat(payload.feedbackText()).isEqualTo("Clear and well-structured response.");
    }

    @Test
    void handleResultPayloadIgnoresDuplicateSession() {
        when(idempotencyRepository.tryLock(
                IDEMPOTENCY_KEY,
                IDEMPOTENCY_TTL_MILLIS))
                .thenReturn(true, false);

        String jsonPayload = successPayload();
        listener.handleResultPayload(jsonPayload);
        listener.handleResultPayload(jsonPayload);

        verify(webhookService, times(1))
                .handleAiSpeakingCallback(org.mockito.ArgumentMatchers.any());
        verify(idempotencyRepository, times(1)).completeLock(
                IDEMPOTENCY_KEY,
                IDEMPOTENCY_TTL_MILLIS);
        verify(idempotencyRepository, never()).releaseLock(IDEMPOTENCY_KEY);
    }

    @Test
    void handleResultPayloadPersistsSystemErrorWithoutCrashing() {
        when(idempotencyRepository.tryLock(
                IDEMPOTENCY_KEY,
                IDEMPOTENCY_TTL_MILLIS))
                .thenReturn(true);

        String errorPayload = """
                {
                  "session_id": "%s",
                  "provider_used": "GROQ_LOCAL",
                  "pronunciation_score": 5.0,
                  "fluency_score": 5.0,
                  "grammar_score": 5.0,
                  "lexical_score": 5.0,
                  "status": "SYSTEM_ERROR",
                  "genuine_word_coverage": 0.0,
                  "feedback_text": "Evaluation failed due to a provider timeout.",
                  "processing_time_ms": 15000,
                  "provider_metadata": {
                    "error": "provider timeout"
                  }
                }
                """.formatted(SESSION_ID);

        listener.handleResultPayload(errorPayload);

        ArgumentCaptor<SpeakingWebhookPayload> payloadCaptor =
                ArgumentCaptor.forClass(SpeakingWebhookPayload.class);
        verify(webhookService).handleAiSpeakingCallback(payloadCaptor.capture());
        verify(idempotencyRepository).completeLock(
                IDEMPOTENCY_KEY,
                IDEMPOTENCY_TTL_MILLIS);
        assertThat(payloadCaptor.getValue().status())
                .isEqualTo(SpeakingEvaluationStatus.SYSTEM_ERROR);
    }

    private String successPayload() {
        return """
                {
                  "session_id": "%s",
                  "provider_used": "GROQ_LOCAL",
                  "pronunciation_score": 7.5,
                  "fluency_score": 7.0,
                  "grammar_score": 6.5,
                  "lexical_score": 7.5,
                  "status": "SUCCESS",
                  "genuine_word_coverage": 0.91,
                  "feedback_text": "Clear and well-structured response.",
                  "processing_time_ms": 12450.5,
                  "provider_metadata": {
                    "model": "whisper-large-v3"
                  }
                }
                """.formatted(SESSION_ID);
    }
}
