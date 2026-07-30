package com.engonow.lms.dto;

import com.fasterxml.jackson.databind.JsonNode;

import java.time.Instant;

public record SpeakingEvaluationEventPayload(
    String sessionId,
    JsonNode questionsMetadata,
    String audioUrl,
    Instant createdAt
) {}
