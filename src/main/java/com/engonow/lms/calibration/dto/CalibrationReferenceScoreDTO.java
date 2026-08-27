package com.engonow.lms.calibration.dto;

import com.engonow.lms.calibration.domain.enums.EvaluationCriterion;
import com.engonow.lms.calibration.domain.enums.ResolutionMethod;
import com.fasterxml.jackson.annotation.JsonInclude;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record CalibrationReferenceScoreDTO(
    UUID id,
    EvaluationCriterion criterion,
    BigDecimal referenceBand,
    ResolutionMethod resolutionMethod,
    List<UUID> contributingRatingIds,
    BigDecimal iccAtResolution,
    boolean discordant,
    UUID adjudicatorId,
    Instant resolvedAt
) {}
