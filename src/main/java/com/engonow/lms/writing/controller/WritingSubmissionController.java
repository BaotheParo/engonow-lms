package com.engonow.lms.writing.controller;

import com.engonow.lms.writing.dto.WritingResultResponseDTO;
import com.engonow.lms.writing.dto.WritingSubmissionRequestDTO;
import com.engonow.lms.writing.dto.WritingSubmissionResponseDTO;
import com.engonow.lms.writing.service.WritingSubmissionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/v1/writing/submissions")
@Tag(name = "AI Writing Submission", description = "Endpoints for submitting essays and querying results")
@RequiredArgsConstructor
@Slf4j
public class WritingSubmissionController {

    private final WritingSubmissionService writingSubmissionService;

    @PostMapping("/submit")
    @Operation(
        summary = "Submit IELTS essay for AI evaluation",
        description = "Asynchronously accepts student essay submission, validates word count, and queues it for grading."
    )
    @ApiResponses(value = {
        @ApiResponse(responseCode = "202", description = "Essay successfully submitted and queued for evaluation"),
        @ApiResponse(responseCode = "400", description = "Invalid request payload or word count below minimum requirement")
    })
    public ResponseEntity<WritingSubmissionResponseDTO> submitEssay(
        @Valid @RequestBody WritingSubmissionRequestDTO request
    ) {
        log.info("REST request to submit essay for student: {}", request.studentId());
        WritingSubmissionResponseDTO response = writingSubmissionService.submitEssay(request);
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(response);
    }

    @GetMapping("/{submissionId}")
    @Operation(
        summary = "Query IELTS essay evaluation result",
        description = "Retrieves graded IELTS writing result, criterion breakdown, sentence-level corrections, and pedagogical tips."
    )
    @ApiResponses(value = {
        @ApiResponse(responseCode = "200", description = "Evaluation result successfully retrieved"),
        @ApiResponse(responseCode = "404", description = "Submission or student record not found"),
        @ApiResponse(responseCode = "422", description = "Submission evaluation is still pending or processing")
    })
    public ResponseEntity<WritingResultResponseDTO> getSubmissionResult(
        @Parameter(description = "UUID of the submission", required = true)
        @PathVariable UUID submissionId,
        @Parameter(description = "UUID of the student (for ownership authorization)", required = true)
        @RequestParam UUID studentId
    ) {
        log.debug("REST request to get result for submissionId: {}, studentId: {}", submissionId, studentId);
        WritingResultResponseDTO response = writingSubmissionService.getSubmissionResult(submissionId, studentId);
        return ResponseEntity.ok(response);
    }
}
