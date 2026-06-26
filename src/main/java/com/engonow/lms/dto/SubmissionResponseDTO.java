package com.engonow.lms.dto;

import com.engonow.lms.enums.AnswerOption;
import java.math.BigDecimal;
import java.util.List;

public record SubmissionResponseDTO(
    Long submissionId,
    Long examId,
    Long studentId,
    int totalCorrect,
    int totalQuestions,
    BigDecimal percentage,
    List<QuestionResult> questionResults
) {
    public record QuestionResult(
        Integer questionNumber,
        AnswerOption studentAnswer,
        AnswerOption correctAnswer,
        Boolean isCorrect
    ) {}
}
