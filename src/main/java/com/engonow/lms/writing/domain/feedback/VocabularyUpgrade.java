package com.engonow.lms.writing.domain.feedback;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.List;

/** Context-aware lexical alternatives suggested by the evaluator. */
public record VocabularyUpgrade(
    @NotBlank String originalWord,
    @NotBlank String contextInEssay,
    @NotNull List<@NotBlank String> academicAlternatives,
    @NotNull List<@NotBlank String> recommendedCollocations
) {

    public VocabularyUpgrade {
        academicAlternatives = immutableCopy(academicAlternatives);
        recommendedCollocations = immutableCopy(recommendedCollocations);
    }

    private static <T> List<T> immutableCopy(List<T> values) {
        return values == null ? List.of() : List.copyOf(values);
    }
}
