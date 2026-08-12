package com.engonow.lms.writing.domain.feedback;

import jakarta.validation.constraints.NotBlank;

/** Higher-band alternatives for a corrected sentence. */
public record EnhancedOptions(
    @NotBlank String band7Option,
    @NotBlank String band8Option
) {
}
