package com.engonow.lms.speaking.event;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.time.Instant;
import java.util.UUID;

/**
 * Domain payload for Speaking Evaluation Failed events, conforming strictly to
 * {@code schemas/speaking_evaluation_failed.json}.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record SpeakingEvaluationFailedPayload(
    UUID attemptId,
    String errorCode,
    String errorMessage,
    boolean isRetriable,
    Instant failedAt
) {}
