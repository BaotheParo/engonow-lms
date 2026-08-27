package com.engonow.lms.calibration.dto;

import com.engonow.lms.calibration.domain.enums.BandStratum;
import com.engonow.lms.calibration.domain.enums.SubsystemType;
import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.UUID;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record CorpusItemCreateRequestDTO(
    @NotNull(message = "Subsystem must not be null")
    SubsystemType subsystem,

    @NotBlank(message = "Task type must not be blank")
    String taskType,

    @NotBlank(message = "Prompt text must not be blank")
    String promptText,

    String essayText,

    String sourceAudioUrl,

    Integer sourceAudioDurationSeconds,

    String sourceTranscript,

    @NotNull(message = "Target band stratum must not be null")
    BandStratum targetBandStratum,

    @NotNull(message = "Intake batch ID must not be null")
    UUID intakeBatchId
) {}
