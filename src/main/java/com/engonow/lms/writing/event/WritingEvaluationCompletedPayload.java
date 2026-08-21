package com.engonow.lms.writing.event;

import com.engonow.lms.writing.domain.feedback.WritingFeedbackDetail;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.math.BigDecimal;
import java.util.UUID;

@JsonIgnoreProperties(ignoreUnknown = true)
public record WritingEvaluationCompletedPayload(
    UUID submissionId,
    BigDecimal taskAchievementScore,
    BigDecimal coherenceCohesionScore,
    BigDecimal lexicalResourceScore,
    BigDecimal grammaticalRangeScore,
    BigDecimal overallBand,
    WritingFeedbackDetail feedbackDetail
) {}
