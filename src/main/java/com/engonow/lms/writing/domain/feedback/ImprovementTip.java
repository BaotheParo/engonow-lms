package com.engonow.lms.writing.domain.feedback;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;

/** A concrete improvement action associated with a target IELTS band. */
public record ImprovementTip(
    @NotBlank String category,
    @NotBlank String tipText,
    @NotNull @DecimalMin("0.0") @DecimalMax("9.0") @Digits(integer = 1, fraction = 1)
    BigDecimal targetBand
) {

    private static final BigDecimal HALF_BAND = new BigDecimal("0.5");

    @AssertTrue(message = "targetBand must use a whole-band or half-band increment")
    public boolean isTargetBandIncrementValid() {
        return targetBand == null
            || targetBand.remainder(HALF_BAND).compareTo(BigDecimal.ZERO) == 0;
    }
}
