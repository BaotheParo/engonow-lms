package com.engonow.lms.dto;

import com.engonow.lms.enums.SpeakingEvaluationStatus;
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.util.List;

public record SpeakingWebhookPayload(
    @JsonProperty("session_id")
    @NotBlank(message = "Session ID must not be blank")
    String sessionId,

    @JsonProperty("pronunciation_score")
    @NotNull(message = "Pronunciation score must not be null")
    BigDecimal pronunciationScore,

    @JsonProperty("fluency_score")
    @NotNull(message = "Fluency score must not be null")
    BigDecimal fluencyScore,

    @JsonProperty("lexical_score")
    @NotNull(message = "Lexical score must not be null")
    BigDecimal lexicalScore,

    @JsonProperty("grammar_score")
    @NotNull(message = "Grammar score must not be null")
    BigDecimal grammarScore,

    @JsonProperty("evidences")
    List<SpeakingEvidenceDTO> evidences,

    @JsonProperty("self_corrections")
    List<SpeakingSelfCorrectionDTO> selfCorrections,

    @JsonProperty("feedback_text")
    @NotBlank(message = "Feedback text must not be blank")
    String feedbackText,

    @JsonProperty("status")
    SpeakingEvaluationStatus status
) {
    public SpeakingWebhookPayload(
            String sessionId,
            BigDecimal pronunciationScore,
            BigDecimal fluencyScore,
            BigDecimal lexicalScore,
            BigDecimal grammarScore,
            List<SpeakingEvidenceDTO> evidences,
            List<SpeakingSelfCorrectionDTO> selfCorrections,
            String feedbackText) {
        this(
            sessionId,
            pronunciationScore,
            fluencyScore,
            lexicalScore,
            grammarScore,
            evidences,
            selfCorrections,
            feedbackText,
            SpeakingEvaluationStatus.SUCCESS
        );
    }

    public record SpeakingSelfCorrectionDTO(
        String original,
        String marker,
        String corrected,
        String type
    ) {}
}
