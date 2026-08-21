package com.engonow.lms.admin.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record DlqReplayRequestDTO(
    @NotBlank String dlqTopic,
    @NotBlank String targetTopic,
    @Min(1) @Max(500) Integer maxMessages,
    String filterCorrelationId
) {
    public DlqReplayRequestDTO {
        if (maxMessages == null) {
            maxMessages = 50;
        }
    }
}
