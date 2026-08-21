package com.engonow.lms.writing.domain.feedback;

import com.engonow.lms.writing.domain.enums.CorrectionErrorType;
import com.engonow.lms.writing.domain.enums.ErrorSeverity;
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;

/**
 * A correction anchored to an end-exclusive character range in the original
 * essay. Keeping offsets with the correction allows clients to highlight the
 * source text without fuzzy matching.
 */
public record SentenceCorrection(
    @NotNull @PositiveOrZero Integer startIndex,
    @NotNull @PositiveOrZero Integer endIndex,
    @NotBlank String originalSentence,
    @NotBlank String correctedSentence,
    @NotNull CorrectionErrorType errorType,
    @NotNull ErrorSeverity severity,
    @NotBlank String explanation,
    @NotNull @Valid EnhancedOptions enhancedOptions
) {

    @com.fasterxml.jackson.annotation.JsonIgnore
    @AssertTrue(message = "endIndex must be greater than startIndex")
    public boolean isIndexRangeValid() {
        return startIndex == null || endIndex == null || endIndex > startIndex;
    }
}
