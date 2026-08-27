package com.engonow.lms.calibration.dto;

import com.engonow.lms.calibration.domain.enums.DatasetSplit;
import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.NotNull;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record AssignSplitRequestDTO(
    @NotNull(message = "Target split must not be null")
    DatasetSplit targetSplit
) {}
