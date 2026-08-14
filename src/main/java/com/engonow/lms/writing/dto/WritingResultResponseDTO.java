package com.engonow.lms.writing.dto;

import com.engonow.lms.writing.domain.entity.WritingResult;
import com.engonow.lms.writing.domain.enums.EvaluatedBy;
import com.engonow.lms.writing.domain.feedback.WritingFeedbackDetail;
import io.swagger.v3.oas.annotations.media.Schema;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

@Schema(description = "Evaluation result and diagnostic breakdown for a writing submission")
public record WritingResultResponseDTO(

    @Schema(description = "UUID of the writing submission", example = "3fa85f64-5717-4562-b3fc-2c963f66afa6")
    UUID submissionId,

    @Schema(description = "Overall IELTS Band Score (rounded using official Cambridge rules)", example = "7.0")
    BigDecimal overallBand,

    @Schema(description = "Task Response / Task Achievement Band Score", example = "7.0")
    BigDecimal taskAchievementScore,

    @Schema(description = "Coherence and Cohesion Band Score", example = "7.0")
    BigDecimal coherenceCohesionScore,

    @Schema(description = "Lexical Resource Band Score", example = "7.0")
    BigDecimal lexicalResourceScore,

    @Schema(description = "Grammatical Range and Accuracy Band Score", example = "7.0")
    BigDecimal grammaticalRangeScore,

    @Schema(description = "Detailed JSON feedback, sentence corrections, and pedagogical tips")
    WritingFeedbackDetail feedbackDetail,

    @Schema(description = "Evaluator mechanism", example = "AI_AUTO")
    EvaluatedBy evaluatedBy,

    @Schema(description = "Sequential version number of this evaluation result", example = "1")
    Integer resultVersion,

    @Schema(description = "Timestamp when the evaluation was finalized", example = "2026-08-14T12:05:00Z")
    Instant evaluatedAt
) {
    public static WritingResultResponseDTO from(WritingResult result) {
        return new WritingResultResponseDTO(
            result.getSubmission().getId(),
            result.getOverallBand(),
            result.getTaskAchievementScore(),
            result.getCoherenceCohesionScore(),
            result.getLexicalResourceScore(),
            result.getGrammaticalRangeScore(),
            result.getFeedbackDetail(),
            result.getEvaluatedBy(),
            result.getResultVersion(),
            result.getEvaluatedAt()
        );
    }
}
