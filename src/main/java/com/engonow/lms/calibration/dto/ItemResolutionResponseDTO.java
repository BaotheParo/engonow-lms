package com.engonow.lms.calibration.dto;

import com.engonow.lms.calibration.domain.enums.EvaluationCriterion;
import com.engonow.lms.calibration.domain.enums.ResolutionMethod;
import com.fasterxml.jackson.annotation.JsonInclude;

import java.math.BigDecimal;
import java.util.UUID;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ItemResolutionResponseDTO(
    UUID corpusItemId,
    EvaluationCriterion criterion,
    BigDecimal referenceBand,
    ResolutionMethod resolutionMethod,
    boolean requiresAdjudicator,
    Double currentIcc,
    String message
) {}
