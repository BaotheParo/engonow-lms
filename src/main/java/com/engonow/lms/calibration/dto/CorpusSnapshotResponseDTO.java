package com.engonow.lms.calibration.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.util.Map;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record CorpusSnapshotResponseDTO(
    long totalItems,
    long writingItems,
    long speakingItems,
    long tuningItems,
    long gatekeeperItems,
    long unassignedItems,
    Map<String, Long> stratumCounts,
    Map<String, Long> statusCounts
) {}
