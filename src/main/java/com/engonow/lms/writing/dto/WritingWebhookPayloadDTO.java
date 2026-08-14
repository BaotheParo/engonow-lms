package com.engonow.lms.writing.dto;

import com.engonow.lms.writing.domain.feedback.WritingFeedbackDetail;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;
import java.util.UUID;

@Schema(description = "Payload sent by Python AI worker upon completing writing evaluation")
public record WritingWebhookPayloadDTO(

    @Schema(description = "UUID of the target writing submission", example = "3fa85f64-5717-4562-b3fc-2c963f66afa6")
    @NotNull(message = "submissionId must not be null")
    UUID submissionId,

    @Schema(description = "Task Response / Task Achievement Band Score", example = "7.0")
    @NotNull(message = "taskAchievementScore must not be null")
    @DecimalMin(value = "0.0", message = "Score must be at least 0.0")
    @DecimalMax(value = "9.0", message = "Score must be at most 9.0")
    BigDecimal taskAchievementScore,

    @Schema(description = "Coherence and Cohesion Band Score", example = "7.0")
    @NotNull(message = "coherenceCohesionScore must not be null")
    @DecimalMin(value = "0.0", message = "Score must be at least 0.0")
    @DecimalMax(value = "9.0", message = "Score must be at most 9.0")
    BigDecimal coherenceCohesionScore,

    @Schema(description = "Lexical Resource Band Score", example = "7.0")
    @NotNull(message = "lexicalResourceScore must not be null")
    @DecimalMin(value = "0.0", message = "Score must be at least 0.0")
    @DecimalMax(value = "9.0", message = "Score must be at most 9.0")
    BigDecimal lexicalResourceScore,

    @Schema(description = "Grammatical Range and Accuracy Band Score", example = "7.0")
    @NotNull(message = "grammaticalRangeScore must not be null")
    @DecimalMin(value = "0.0", message = "Score must be at least 0.0")
    @DecimalMax(value = "9.0", message = "Score must be at most 9.0")
    BigDecimal grammaticalRangeScore,

    @Schema(description = "Structured IELTS diagnostic details matching the WritingFeedbackDetail schema")
    @NotNull(message = "feedbackDetail must not be null")
    @Valid
    WritingFeedbackDetail feedbackDetail,

    @Schema(description = "Model version used for scoring", example = "gemini-2.5-flash")
    @NotBlank(message = "aiModelVersion must not be blank")
    String aiModelVersion,

    @Schema(description = "Evaluation status flag: SUCCESS or FAILED", example = "SUCCESS")
    @NotBlank(message = "status must not be blank")
    String status,

    @Schema(description = "Optional error details if the AI evaluation pipeline failed", example = "null")
    String errorMessage
) {
    public boolean isSuccess() {
        return "SUCCESS".equalsIgnoreCase(status);
    }
}
