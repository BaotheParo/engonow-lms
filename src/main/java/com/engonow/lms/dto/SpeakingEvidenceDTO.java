package com.engonow.lms.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public record SpeakingEvidenceDTO(
    String criterion,
    String part,
    String question,
    String quote,
    @JsonProperty("error_type") String errorType,
    String correction,
    String explanation
) {}
