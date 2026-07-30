package com.engonow.lms.dto;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record SpeakingSubmissionRequestDTO(
    @NotBlank(message = "Session ID must not be blank")
    String sessionId,

    @NotNull(message = "Questions metadata must not be null")
    JsonNode questionsMetadata,

    @NotBlank(message = "Audio URL or file reference must not be blank")
    String audioUrl
) {}
