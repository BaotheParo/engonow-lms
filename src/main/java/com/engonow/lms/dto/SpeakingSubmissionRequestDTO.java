package com.engonow.lms.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Valid;

import java.util.UUID;

/**
 * Request DTO for student IELTS Speaking evaluation submissions.
 * Supports both modern Claim-Check audio references and legacy session submissions.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record SpeakingSubmissionRequestDTO(
    String sessionId,
    JsonNode questionsMetadata,
    String audioUrl,
    UUID studentId,
    String part,
    String topicPrompt,
    @Valid AudioReferenceDTO audioRef
) {
    public SpeakingSubmissionRequestDTO(String sessionId, JsonNode questionsMetadata, String audioUrl) {
        this(sessionId, questionsMetadata, audioUrl, null, null, null, null);
    }

    public SpeakingSubmissionRequestDTO(UUID studentId, String part, String topicPrompt, AudioReferenceDTO audioRef) {
        this(null, null, null, studentId, part, topicPrompt, audioRef);
    }
}
