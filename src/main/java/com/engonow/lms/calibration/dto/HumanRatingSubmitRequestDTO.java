package com.engonow.lms.calibration.dto;

import com.engonow.lms.calibration.domain.enums.EvaluationCriterion;
import com.engonow.lms.calibration.domain.enums.RaterCredentialLevel;
import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;
import java.util.UUID;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record HumanRatingSubmitRequestDTO(
    @NotNull(message = "Rater ID must not be null")
    UUID raterId,

    @NotNull(message = "Rater credential level must not be null")
    RaterCredentialLevel raterCredentialLevel,

    @NotNull(message = "Evaluation criterion must not be null")
    EvaluationCriterion criterion,

    @NotNull(message = "Band score must not be null")
    @DecimalMin(value = "0.0", message = "Band score must be >= 0.0")
    @DecimalMax(value = "9.0", message = "Band score must be <= 9.0")
    BigDecimal bandScore,

    boolean transcriptFlaggedIncorrect,

    String ratingNotes
) {}
