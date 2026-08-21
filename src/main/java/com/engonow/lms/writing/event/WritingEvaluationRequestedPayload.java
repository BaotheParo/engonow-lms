package com.engonow.lms.writing.event;

import com.engonow.lms.writing.domain.enums.TaskType;

import java.util.UUID;

/**
 * Domain payload for Writing Evaluation Requested events, conforming strictly to
 * {@code schemas/writing_evaluation_requested.json}.
 */
public record WritingEvaluationRequestedPayload(
    UUID submissionId,
    UUID studentId,
    TaskType taskType,
    String taskPrompt,
    String essayText,
    int wordCount
) {}
