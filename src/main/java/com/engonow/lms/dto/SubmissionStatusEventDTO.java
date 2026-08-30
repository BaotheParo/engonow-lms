package com.engonow.lms.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class SubmissionStatusEventDTO {
    private String status;        // PENDING, PROCESSING, SCORED, FAILED
    private UUID submissionId;
    private UUID resultId;        // null unless SCORED
    private String subsystem;     // WRITING or SPEAKING
    private Instant timestamp;
}
