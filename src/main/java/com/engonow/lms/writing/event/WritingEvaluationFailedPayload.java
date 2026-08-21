package com.engonow.lms.writing.event;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.time.Instant;
import java.util.UUID;

@JsonIgnoreProperties(ignoreUnknown = true)
public record WritingEvaluationFailedPayload(
    UUID submissionId,
    String errorCode,
    String errorMessage,
    boolean isRetriable,
    Instant failedAt
) {}
