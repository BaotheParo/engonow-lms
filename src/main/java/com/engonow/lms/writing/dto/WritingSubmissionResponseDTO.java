package com.engonow.lms.writing.dto;

import com.engonow.lms.writing.domain.entity.WritingSubmission;
import com.engonow.lms.writing.domain.enums.SubmissionStatus;
import com.engonow.lms.writing.domain.enums.TaskType;
import io.swagger.v3.oas.annotations.media.Schema;

import java.time.Instant;
import java.util.UUID;

@Schema(description = "Response payload after an essay has been accepted for evaluation")
public record WritingSubmissionResponseDTO(

    @Schema(description = "Unique UUID identifier of the writing submission", example = "3fa85f64-5717-4562-b3fc-2c963f66afa6")
    UUID id,

    @Schema(description = "UUID of the submitting student", example = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    UUID studentId,

    @Schema(description = "IELTS task type", example = "TASK_2")
    TaskType taskType,

    @Schema(description = "Calculated word count of the essay", example = "285")
    int wordCount,

    @Schema(description = "Current lifecycle status of the submission", example = "PENDING")
    SubmissionStatus status,

    @Schema(description = "Submission timestamp", example = "2026-08-14T12:00:00Z")
    Instant createdAt
) {
    public static WritingSubmissionResponseDTO from(WritingSubmission submission) {
        return new WritingSubmissionResponseDTO(
            submission.getId(),
            submission.getStudentId(),
            submission.getTaskType(),
            submission.getWordCount() != null ? submission.getWordCount() : 0,
            submission.getStatus(),
            submission.getCreatedAt()
        );
    }
}
