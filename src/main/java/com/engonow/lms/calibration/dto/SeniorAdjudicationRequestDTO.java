package com.engonow.lms.calibration.dto;

import com.engonow.lms.calibration.domain.enums.EvaluationCriterion;
import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;
import java.util.UUID;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record SeniorAdjudicationRequestDTO(
    @NotNull(message = "Adjudicator ID must not be null")
    UUID adjudicatorId,

    @NotNull(message = "Evaluation criterion must not be null")
    EvaluationCriterion criterion,

    @NotNull(message = "Binding score must not be null")
    @DecimalMin(value = "0.0", message = "Binding score must be >= 0.0")
    @DecimalMax(value = "9.0", message = "Binding score must be <= 9.0")
    BigDecimal bindingScore,

    String adjudicationNotes
) {}
