package com.engonow.lms.writing.domain.feedback;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;

import java.math.BigDecimal;

/** Aggregate, deterministic metrics calculated from the submitted essay. */
public record EssayMetrics(
    @NotNull @PositiveOrZero Integer totalWords,
    @NotNull @PositiveOrZero Integer uniqueWords,
    @NotNull @DecimalMin("0.0") @DecimalMax("1.0") BigDecimal lexicalDiversityRatio,
    @NotNull @DecimalMin("0.0") BigDecimal averageSentenceLength,
    @NotNull @DecimalMin("0.0") @DecimalMax("1.0") BigDecimal complexSentencesRatio
) {

    /** A vocabulary cannot contain more distinct words than total words. */
    @AssertTrue(message = "uniqueWords must not exceed totalWords")
    public boolean isUniqueWordCountValid() {
        return totalWords == null || uniqueWords == null || uniqueWords <= totalWords;
    }
}
