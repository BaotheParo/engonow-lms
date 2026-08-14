package com.engonow.lms.writing.controller;

import com.engonow.lms.annotation.Idempotent;
import com.engonow.lms.writing.dto.WritingWebhookPayloadDTO;
import com.engonow.lms.writing.service.WritingSubmissionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;
import java.util.concurrent.TimeUnit;

@RestController
@RequestMapping("/api/v1/writing/webhook")
@Tag(name = "AI Writing Webhook", description = "Internal callback for AI Worker evaluation results")
@RequiredArgsConstructor
@Slf4j
public class WritingWebhookController {

    private final WritingSubmissionService writingSubmissionService;

    @PostMapping("/result")
    @Idempotent(
        key = "'webhook:writing:' + #payload.submissionId()",
        expireTime = 86400,
        timeUnit = TimeUnit.SECONDS
    )
    @Operation(
        summary = "Ingest AI writing evaluation result callback",
        description = "Processes evaluated score results from Python AI worker idempotently with Redis distributed lock guarding."
    )
    @ApiResponses(value = {
        @ApiResponse(responseCode = "200", description = "Webhook payload acknowledged and processed successfully"),
        @ApiResponse(responseCode = "400", description = "Invalid payload or validation failure"),
        @ApiResponse(responseCode = "404", description = "Target writing submission not found"),
        @ApiResponse(responseCode = "409", description = "Duplicate webhook callback rejected by idempotency filter")
    })
    public ResponseEntity<Map<String, String>> handleWritingResultCallback(
        @Valid @RequestBody WritingWebhookPayloadDTO payload
    ) {
        log.info("Received AI writing evaluation webhook callback for submissionId: {}, status: {}",
            payload.submissionId(), payload.status());

        writingSubmissionService.processEvaluationWebhook(payload);

        return ResponseEntity.ok(Map.of("status", "ACK"));
    }
}
