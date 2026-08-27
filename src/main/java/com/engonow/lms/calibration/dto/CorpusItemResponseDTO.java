package com.engonow.lms.calibration.dto;

import com.engonow.lms.calibration.domain.enums.BandStratum;
import com.engonow.lms.calibration.domain.enums.CorpusItemStatus;
import com.engonow.lms.calibration.domain.enums.DatasetSplit;
import com.engonow.lms.calibration.domain.enums.SubsystemType;
import com.fasterxml.jackson.annotation.JsonInclude;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record CorpusItemResponseDTO(
    UUID id,
    SubsystemType subsystem,
    String taskType,
    String promptText,
    String essayText,
    String sourceAudioUrl,
    Integer sourceAudioDurationSeconds,
    String sourceTranscript,
    Instant calibrationHoldUntil,
    BandStratum targetBandStratum,
    DatasetSplit datasetSplit,
    Instant splitAssignedAt,
    Instant splitLockedAt,
    UUID intakeBatchId,
    CorpusItemStatus status,
    Instant createdAt,
    Long version,
    List<CalibrationHumanRatingDTO> ratings,
    List<CalibrationReferenceScoreDTO> referenceScores
) {}
