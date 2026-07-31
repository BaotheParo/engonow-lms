package com.engonow.lms.listener;

import com.engonow.lms.dto.SpeakingResultEventPayload;
import com.engonow.lms.dto.SpeakingWebhookPayload;
import com.engonow.lms.exception.IdempotencyException;
import com.engonow.lms.repository.IdempotencyRepository;
import com.engonow.lms.service.WebhookService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

@Component
@Slf4j
@RequiredArgsConstructor
public class SpeakingResultListener {

    private static final String IDEMPOTENCY_KEY_PREFIX = "result_process:";
    private static final long IDEMPOTENCY_TTL_MILLIS = 60_000L;

    private final ObjectMapper objectMapper;
    private final WebhookService webhookService;
    private final IdempotencyRepository idempotencyRepository;

    /**
     * Parses and persists one speaking result. Processing failures are propagated so
     * broker adapters can leave the message unacknowledged for redelivery.
     *
     * @param jsonPayload serialized {@link SpeakingResultEventPayload}
     */
    public void handleResultPayload(String jsonPayload) {
        SpeakingResultEventPayload eventPayload = deserialize(jsonPayload);
        SpeakingWebhookPayload webhookPayload = eventPayload.toWebhookPayload();
        String sessionId = webhookPayload.sessionId();
        String idempotencyKey = IDEMPOTENCY_KEY_PREFIX + sessionId;

        if (!tryAcquireLock(idempotencyKey, sessionId)) {
            return;
        }

        try {
            webhookService.handleAiSpeakingCallback(webhookPayload);
            idempotencyRepository.completeLock(
                    idempotencyKey,
                    IDEMPOTENCY_TTL_MILLIS);
            log.info(
                    "[RESULT LISTENER] Successfully processed speaking result for session: {}, "
                            + "Status: {}",
                    sessionId,
                    webhookPayload.status());
        } catch (RuntimeException exception) {
            idempotencyRepository.releaseLock(idempotencyKey);
            throw exception;
        }
    }

    private SpeakingResultEventPayload deserialize(String jsonPayload) {
        if (jsonPayload == null || jsonPayload.isBlank()) {
            throw new IllegalArgumentException("Speaking result JSON payload must not be blank");
        }

        try {
            return objectMapper.readValue(jsonPayload, SpeakingResultEventPayload.class);
        } catch (JsonProcessingException exception) {
            throw new IllegalArgumentException(
                    "Unable to deserialize speaking result payload",
                    exception);
        }
    }

    private boolean tryAcquireLock(String idempotencyKey, String sessionId) {
        try {
            boolean acquired = idempotencyRepository.tryLock(
                    idempotencyKey,
                    IDEMPOTENCY_TTL_MILLIS);
            if (!acquired) {
                logDuplicate(sessionId);
            }
            return acquired;
        } catch (IdempotencyException exception) {
            logDuplicate(sessionId);
            return false;
        }
    }

    private void logDuplicate(String sessionId) {
        log.warn(
                "[RESULT LISTENER] Duplicate result event ignored for session: {}",
                sessionId);
    }
}
