package com.engonow.lms.dto;

import com.engonow.lms.enums.SpeakingEvaluationStatus;

public record SpeakingSubmissionResponseDTO(
    String sessionId,
    SpeakingEvaluationStatus status,
    String message
) {}
