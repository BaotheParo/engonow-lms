package com.engonow.lms.writing.domain.feedback;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.List;

/**
 * Versionable JSONB document persisted with a writing result. The relational
 * columns retain fields used for filtering and integrity, while this record
 * carries the evolving, high-cardinality feedback payload.
 */
public record WritingFeedbackDetail(
    @NotBlank String examinerSummary,
    @NotNull @Valid EssayMetrics essayMetrics,
    @NotNull @Valid List<@Valid CriterionFeedback> criteria,
    @NotNull @Valid List<@Valid SentenceCorrection> corrections,
    @NotNull @Valid CohesiveDeviceAnalysis cohesiveDeviceAnalysis,
    @NotNull @Valid List<@Valid VocabularyUpgrade> vocabularyUpgrades,
    @NotNull @Valid List<@Valid ImprovementTip> improvementTips
) {

    public WritingFeedbackDetail {
        criteria = immutableCopy(criteria);
        corrections = immutableCopy(corrections);
        vocabularyUpgrades = immutableCopy(vocabularyUpgrades);
        improvementTips = immutableCopy(improvementTips);
    }

    private static <T> List<T> immutableCopy(List<T> values) {
        return values == null ? List.of() : List.copyOf(values);
    }
}
