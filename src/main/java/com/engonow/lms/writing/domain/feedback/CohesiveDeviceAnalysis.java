package com.engonow.lms.writing.domain.feedback;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.List;

/** Analysis of linking expressions and discourse markers in the essay. */
public record CohesiveDeviceAnalysis(
    @NotNull List<@NotBlank String> usedDevices,
    @NotNull List<@NotBlank String> overusedOrRepetitive,
    @NotNull List<@NotBlank String> suggestedTransitions
) {

    public CohesiveDeviceAnalysis {
        usedDevices = immutableCopy(usedDevices);
        overusedOrRepetitive = immutableCopy(overusedOrRepetitive);
        suggestedTransitions = immutableCopy(suggestedTransitions);
    }

    private static <T> List<T> immutableCopy(List<T> values) {
        return values == null ? List.of() : List.copyOf(values);
    }
}
