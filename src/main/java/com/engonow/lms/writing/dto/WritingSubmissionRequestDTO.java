package com.engonow.lms.writing.dto;

import com.engonow.lms.writing.domain.enums.TaskType;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.UUID;

@Schema(description = "Request payload for submitting an IELTS writing essay for AI grading")
public record WritingSubmissionRequestDTO(

    @Schema(description = "UUID of the student submitting the essay", example = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    @NotNull(message = "studentId must not be null")
    UUID studentId,

    @Schema(description = "IELTS Writing task category", example = "TASK_2")
    @NotNull(message = "taskType must not be null")
    TaskType taskType,

    @Schema(description = "The prompt question or topic statement assigned to the student", example = "Some people believe that unpaid community service should be a compulsory part of high school programmes. To what extent do you agree or disagree?")
    @NotBlank(message = "taskPrompt must not be blank")
    String taskPrompt,

    @Schema(description = "Full text of the essay written by the student", example = "In contemporary society, the proposition of incorporating mandatory unpaid community service into high school curriculums has sparked considerable debate...")
    @NotBlank(message = "essayText must not be blank")
    @Size(min = 50, message = "essayText must contain at least 50 characters")
    String essayText
) {
    public WritingSubmissionRequestDTO {
        if (essayText != null && countWords(essayText) < 20) {
            throw new IllegalArgumentException("Essay text must contain at least 20 words for valid assessment.");
        }
    }

    public static int countWords(String text) {
        if (text == null || text.isBlank()) {
            return 0;
        }
        return text.trim().split("\\s+").length;
    }
}
