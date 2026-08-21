package com.engonow.lms.speaking.event;

import com.engonow.lms.dto.AudioReferenceDTO;
import com.fasterxml.jackson.annotation.JsonInclude;

import java.util.UUID;

/**
 * Domain payload for Speaking Evaluation Requested events, conforming strictly to
 * {@code schemas/speaking_evaluation_requested.json}.
 * Employs the Claim-Check pattern (never transmits raw binary audio).
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record SpeakingEvaluationRequestedPayload(
    UUID attemptId,
    UUID studentId,
    String part,
    AudioReferenceDTO audioRef
) {}
