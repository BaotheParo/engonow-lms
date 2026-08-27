package com.engonow.lms.calibration.dto;

import com.engonow.lms.calibration.domain.enums.EvaluationCriterion;
import com.engonow.lms.calibration.domain.enums.RaterCredentialLevel;
import com.fasterxml.jackson.annotation.JsonInclude;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record CalibrationHumanRatingDTO(
    UUID id,
    UUID raterId,
    RaterCredentialLevel raterCredentialLevel,
    EvaluationCriterion criterion,
    BigDecimal bandScore,
    boolean transcriptFlaggedIncorrect,
    String ratingNotes,
    Instant ratedAt
) {}
