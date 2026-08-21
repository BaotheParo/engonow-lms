package com.engonow.lms.writing.service;

import com.engonow.lms.writing.dto.WritingResultResponseDTO;
import com.engonow.lms.writing.dto.WritingSubmissionRequestDTO;
import com.engonow.lms.writing.dto.WritingSubmissionResponseDTO;
import com.engonow.lms.writing.dto.WritingWebhookPayloadDTO;

import java.util.UUID;

public interface WritingSubmissionService {

    /**
     * Accepts a student's essay submission, persists it in PENDING state,
     * and publishes an Outbox event for asynchronous processing.
     *
     * @param request the submission payload containing student ID, prompt, and essay
     * @return summary response containing submission UUID and status
     */
    WritingSubmissionResponseDTO submitEssay(WritingSubmissionRequestDTO request);

    /**
     * Retrieves the graded IELTS writing result and diagnostic feedback for a submission.
     *
     * @param submissionId UUID of the submission
     * @param studentId    UUID of the student (for authorization and ownership check)
     * @return detailed result response DTO
     */
    WritingResultResponseDTO getSubmissionResult(UUID submissionId, UUID studentId);

    /**
     * Ingests the evaluation callback from the AI evaluation engine, calculates
     * overall Cambridge band, updates status to SCORED, and atomically persists the result.
     *
     * @param payload the webhook payload sent by Python AI worker
     */
    void processEvaluationWebhook(WritingWebhookPayloadDTO payload);

    /**
     * Processes a WRITING_EVALUATION_COMPLETED Kafka event envelope with Inbox deduplication.
     */
    void processEvaluationCompletedEvent(
        com.engonow.lms.writing.event.EventEnvelope<com.engonow.lms.writing.event.WritingEvaluationCompletedPayload> envelope,
        String rawPayload
    );

    /**
     * Processes a WRITING_EVALUATION_FAILED Kafka event envelope with Inbox deduplication.
     */
    void processEvaluationFailedEvent(
        com.engonow.lms.writing.event.EventEnvelope<com.engonow.lms.writing.event.WritingEvaluationFailedPayload> envelope,
        String rawPayload
    );
}
