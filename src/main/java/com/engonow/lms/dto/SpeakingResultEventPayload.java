package com.engonow.lms.dto;

import com.engonow.lms.enums.SpeakingEvaluationStatus;
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.math.BigDecimal;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

/**
 * Broker-facing contract for the result produced by the Python speaking worker.
 *
 * <p>This DTO is deliberately separate from {@link SpeakingWebhookPayload} so the
 * existing HTTP callback contract remains backward compatible.</p>
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record SpeakingResultEventPayload(
        @JsonProperty("session_id")
        @JsonAlias("sessionId")
        String sessionId,

        @JsonProperty("provider_used")
        @JsonAlias("providerUsed")
        String providerUsed,

        @JsonProperty("pronunciation_score")
        @JsonAlias("pronunciationScore")
        BigDecimal pronunciationScore,

        @JsonProperty("fluency_score")
        @JsonAlias("fluencyScore")
        BigDecimal fluencyScore,

        @JsonProperty("grammar_score")
        @JsonAlias("grammarScore")
        BigDecimal grammarScore,

        @JsonProperty("lexical_score")
        @JsonAlias("lexicalScore")
        BigDecimal lexicalScore,

        @JsonProperty("status")
        String status,

        @JsonProperty("genuine_word_coverage")
        @JsonAlias("genuineWordCoverage")
        BigDecimal genuineWordCoverage,

        @JsonProperty("feedback_text")
        @JsonAlias("feedbackText")
        String feedbackText,

        @JsonProperty("processing_time_ms")
        @JsonAlias("processingTimeMs")
        BigDecimal processingTimeMs,

        @JsonProperty("provider_metadata")
        @JsonAlias("providerMetadata")
        Map<String, Object> providerMetadata
) {

    /**
     * Adapts the event contract to the application's existing persistence service contract.
     */
    public SpeakingWebhookPayload toWebhookPayload() {
        if (sessionId == null || sessionId.isBlank()) {
            throw new IllegalArgumentException("Speaking result session_id must not be blank");
        }

        return new SpeakingWebhookPayload(
                sessionId,
                Objects.requireNonNull(
                        pronunciationScore,
                        "Speaking result pronunciation_score must not be null"),
                Objects.requireNonNull(
                        fluencyScore,
                        "Speaking result fluency_score must not be null"),
                Objects.requireNonNull(
                        lexicalScore,
                        "Speaking result lexical_score must not be null"),
                Objects.requireNonNull(
                        grammarScore,
                        "Speaking result grammar_score must not be null"),
                List.of(),
                List.of(),
                requireFeedbackText(),
                toEvaluationStatus(status));
    }

    private String requireFeedbackText() {
        if (feedbackText == null || feedbackText.isBlank()) {
            throw new IllegalArgumentException(
                    "Speaking result feedback_text must not be blank");
        }
        return feedbackText;
    }

    private static SpeakingEvaluationStatus toEvaluationStatus(String rawStatus) {
        if (rawStatus == null || rawStatus.isBlank()) {
            throw new IllegalArgumentException("Speaking result status must not be blank");
        }

        String normalizedStatus = rawStatus.trim().toUpperCase(Locale.ROOT);
        return switch (normalizedStatus) {
            case "PARTIAL" -> SpeakingEvaluationStatus.PARTIAL_SUCCESS_LOW_AUDIO_CONF;
            case "FAILED" -> SpeakingEvaluationStatus.SYSTEM_ERROR;
            default -> {
                try {
                    yield SpeakingEvaluationStatus.valueOf(normalizedStatus);
                } catch (IllegalArgumentException exception) {
                    throw new IllegalArgumentException(
                            "Unsupported speaking result status: " + rawStatus,
                            exception);
                }
            }
        };
    }
}
