package com.engonow.lms.speaking.event;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.JsonNode;

import java.math.BigDecimal;
import java.util.UUID;

/**
 * Domain payload for Speaking Evaluation Completed events, conforming strictly to
 * {@code schemas/speaking_evaluation_completed.json}.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record SpeakingEvaluationCompletedPayload(
    UUID attemptId,
    BigDecimal fluencyCoherenceScore,
    BigDecimal lexicalResourceScore,
    BigDecimal grammaticalRangeScore,
    BigDecimal pronunciationScore,
    BigDecimal overallBand,
    JsonNode feedbackDetail
) {}
