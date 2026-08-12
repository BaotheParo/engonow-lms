package com.engonow.lms.writing.domain.feedback;

import com.engonow.lms.writing.domain.enums.WritingCriterion;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;
import java.util.List;

/** Detailed examiner feedback for one IELTS writing criterion. */
public record CriterionFeedback(
    @NotNull WritingCriterion criterion,
    @NotNull @DecimalMin("0.0") @DecimalMax("9.0") @Digits(integer = 1, fraction = 1)
    BigDecimal score,
    @NotBlank String summary,
    @NotNull List<@NotBlank String> strengths,
    @NotNull List<@NotBlank String> weaknesses,
    @NotBlank String bandGapAnalysis
) {

    private static final BigDecimal HALF_BAND = new BigDecimal("0.5");

    public CriterionFeedback {
        strengths = immutableCopy(strengths);
        weaknesses = immutableCopy(weaknesses);
    }

    @AssertTrue(message = "score must use a whole-band or half-band increment")
    public boolean isScoreIncrementValid() {
        return score == null || score.remainder(HALF_BAND).compareTo(BigDecimal.ZERO) == 0;
    }

    private static <T> List<T> immutableCopy(List<T> values) {
        return values == null ? null : List.copyOf(values);
    }
}
