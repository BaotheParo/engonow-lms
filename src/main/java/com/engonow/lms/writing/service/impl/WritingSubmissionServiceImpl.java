package com.engonow.lms.writing.service.impl;

import com.engonow.lms.entity.OutboxEvent;
import com.engonow.lms.enums.OutboxStatus;
import com.engonow.lms.repository.OutboxEventRepository;
import com.engonow.lms.writing.domain.entity.WritingResult;
import com.engonow.lms.writing.domain.entity.WritingSubmission;
import com.engonow.lms.writing.domain.enums.EvaluatedBy;
import com.engonow.lms.writing.domain.enums.SubmissionStatus;
import com.engonow.lms.writing.dto.WritingResultResponseDTO;
import com.engonow.lms.writing.dto.WritingSubmissionRequestDTO;
import com.engonow.lms.writing.dto.WritingSubmissionResponseDTO;
import com.engonow.lms.writing.dto.WritingWebhookPayloadDTO;
import com.engonow.lms.writing.event.EventEnvelope;
import com.engonow.lms.writing.event.OutboxEventCreatedLocalEvent;
import com.engonow.lms.writing.event.WritingEvaluationRequestedPayload;
import com.engonow.lms.writing.exception.WritingSubmissionNotFoundException;
import com.engonow.lms.writing.exception.WritingSubmissionProcessingException;
import com.engonow.lms.writing.repository.WritingResultRepository;
import com.engonow.lms.writing.repository.WritingSubmissionRepository;
import com.engonow.lms.writing.service.WritingSubmissionService;
import com.engonow.lms.writing.util.CambridgeRoundingUtil;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import com.engonow.lms.repository.InboxEventRepository;
import com.engonow.lms.writing.event.WritingEvaluationCompletedPayload;
import com.engonow.lms.writing.event.WritingEvaluationFailedPayload;

import java.util.Map;
import java.util.UUID;

@Service
@Transactional
@RequiredArgsConstructor
@Slf4j
public class WritingSubmissionServiceImpl implements WritingSubmissionService {

    public static final String WRITING_EVALUATION_REQUESTED_TOPIC = "engonow.writing.evaluation-requested.v1";
    public static final String EVENT_TYPE_WRITING_EVALUATION_REQUESTED = "WRITING_EVALUATION_REQUESTED";
    public static final String AGGREGATE_TYPE_WRITING_SUBMISSION = "WRITING_SUBMISSION";

    private final WritingSubmissionRepository writingSubmissionRepository;
    private final WritingResultRepository writingResultRepository;
    private final OutboxEventRepository outboxEventRepository;
    private final InboxEventRepository inboxEventRepository;
    private final ApplicationEventPublisher applicationEventPublisher;
    private final ObjectMapper objectMapper;

    @Override
    public WritingSubmissionResponseDTO submitEssay(WritingSubmissionRequestDTO request) {
        log.info("Received IELTS Writing submission request for student: {}, taskType: {}",
            request.studentId(), request.taskType());

        // 1. Persist submission in PENDING status atomically
        int wordCount = WritingSubmissionRequestDTO.countWords(request.essayText());

        WritingSubmission submission = new WritingSubmission();
        submission.setStudentId(request.studentId());
        submission.setTaskType(request.taskType());
        submission.setTaskPrompt(request.taskPrompt());
        submission.setEssayText(request.essayText());
        submission.setWordCount(wordCount);
        submission.setStatus(SubmissionStatus.PENDING);

        WritingSubmission savedSubmission = writingSubmissionRepository.save(submission);

        // 2. Build canonical domain payload and Event Envelope
        WritingEvaluationRequestedPayload payload = new WritingEvaluationRequestedPayload(
            savedSubmission.getId(),
            savedSubmission.getStudentId(),
            savedSubmission.getTaskType(),
            savedSubmission.getTaskPrompt(),
            savedSubmission.getEssayText(),
            savedSubmission.getWordCount()
        );

        String traceId = java.util.Optional.ofNullable(org.slf4j.MDC.get("traceId"))
            .orElseGet(() -> UUID.randomUUID().toString());
        String correlationId = java.util.Optional.ofNullable(org.slf4j.MDC.get("correlationId"))
            .orElseGet(() -> savedSubmission.getId().toString());

        EventEnvelope<WritingEvaluationRequestedPayload> envelope = EventEnvelope.of(
            EVENT_TYPE_WRITING_EVALUATION_REQUESTED,
            savedSubmission.getId(),
            correlationId,
            traceId,
            "engonow-lms-backend",
            payload
        );

        String serializedEnvelope;
        try {
            serializedEnvelope = objectMapper.writeValueAsString(envelope);
        } catch (JsonProcessingException e) {
            log.error("Failed to serialize writing evaluation event envelope: {}", e.getMessage(), e);
            throw new IllegalArgumentException("Failed to serialize writing evaluation event envelope to JSON", e);
        }

        // 3. Persist corresponding Transactional Outbox event
        OutboxEvent outboxEvent = OutboxEvent.builder()
            .aggregateType(AGGREGATE_TYPE_WRITING_SUBMISSION)
            .aggregateId(savedSubmission.getId().toString())
            .eventType(EVENT_TYPE_WRITING_EVALUATION_REQUESTED)
            .schemaVersion("1.0")
            .traceId(traceId)
            .correlationId(correlationId)
            .payload(serializedEnvelope)
            .status(OutboxStatus.PENDING)
            .retryCount(0)
            .build();

        OutboxEvent savedOutboxEvent = outboxEventRepository.save(outboxEvent);

        // 4. Publish Spring local event for non-blocking eager Kafka dispatching after commit
        applicationEventPublisher.publishEvent(new OutboxEventCreatedLocalEvent(
            savedOutboxEvent.getId(),
            WRITING_EVALUATION_REQUESTED_TOPIC,
            savedSubmission.getId().toString(),
            serializedEnvelope,
            Map.of(
                "eventId", envelope.eventId().toString().getBytes(StandardCharsets.UTF_8),
                "traceId", envelope.traceId().getBytes(StandardCharsets.UTF_8),
                "eventType", envelope.eventType().getBytes(StandardCharsets.UTF_8),
                "schemaVersion", envelope.schemaVersion().getBytes(StandardCharsets.UTF_8),
                "producedAt", envelope.producedAt().toString().getBytes(StandardCharsets.UTF_8),
                "retryCount", String.valueOf(envelope.retryCount()).getBytes(StandardCharsets.UTF_8),
                "source", envelope.source().getBytes(StandardCharsets.UTF_8),
                "correlationId", envelope.correlationId().getBytes(StandardCharsets.UTF_8)
            )
        ));

        log.info("Successfully created writing submission {} and corresponding outbox event {}",
            savedSubmission.getId(), savedOutboxEvent.getId());
        return WritingSubmissionResponseDTO.from(savedSubmission);
    }

    @Override
    @Transactional(readOnly = true)
    public WritingResultResponseDTO getSubmissionResult(UUID submissionId, UUID studentId) {
        log.debug("Fetching writing submission result for submissionId: {}, studentId: {}", submissionId, studentId);

        WritingSubmission submission = writingSubmissionRepository.findByIdAndStudentId(submissionId, studentId)
            .orElseThrow(() -> new WritingSubmissionNotFoundException(submissionId, studentId));

        if (submission.getStatus() != SubmissionStatus.SCORED) {
            log.warn("Writing submission {} is not in SCORED status (current: {})", submissionId, submission.getStatus());
            throw new WritingSubmissionProcessingException(submissionId, submission.getStatus());
        }

        WritingResult result = writingResultRepository.findBySubmissionIdAndIsCurrentTrue(submissionId)
            .orElseThrow(() -> new WritingSubmissionNotFoundException("Active evaluated result not found for submission: " + submissionId));

        return WritingResultResponseDTO.from(result);
    }

    @Override
    public void processEvaluationWebhook(WritingWebhookPayloadDTO payload) {
        log.info("Processing writing evaluation webhook for submissionId: {}, status: {}",
            payload.submissionId(), payload.status());

        WritingSubmission submission = writingSubmissionRepository.findById(payload.submissionId())
            .orElseThrow(() -> new WritingSubmissionNotFoundException(payload.submissionId()));

        if (!payload.isSuccess()) {
            log.error("AI Writing evaluation pipeline reported failure for submission {}: {}",
                payload.submissionId(), payload.errorMessage());
            submission.setStatus(SubmissionStatus.FAILED);
            writingSubmissionRepository.save(submission);
            return;
        }

        // Invalidate previous active result atomically
        writingResultRepository.invalidateCurrentResult(submission.getId());

        // Calculate official Cambridge IELTS rounded overall band
        BigDecimal overallBand = CambridgeRoundingUtil.calculateOverallBand(
            payload.taskAchievementScore(),
            payload.coherenceCohesionScore(),
            payload.lexicalResourceScore(),
            payload.grammaticalRangeScore()
        );

        List<WritingResult> pastResults = writingResultRepository.findBySubmissionIdOrderByResultVersionDesc(submission.getId());
        int nextVersion = pastResults.isEmpty() ? 1 : pastResults.get(0).getResultVersion() + 1;

        WritingResult result = new WritingResult();
        result.setSubmission(submission);
        result.setTaskAchievementScore(payload.taskAchievementScore());
        result.setCoherenceCohesionScore(payload.coherenceCohesionScore());
        result.setLexicalResourceScore(payload.lexicalResourceScore());
        result.setGrammaticalRangeScore(payload.grammaticalRangeScore());
        result.setOverallBand(overallBand);
        result.setFeedbackDetail(payload.feedbackDetail());
        result.setAiModelVersion(payload.aiModelVersion());
        result.setEvaluatedBy(EvaluatedBy.AI_AUTO);
        result.setResultVersion(nextVersion);
        result.setIsCurrent(true);
        result.setEvaluatedAt(Instant.now());

        writingResultRepository.save(result);

        submission.markAsScored();
        writingSubmissionRepository.save(submission);

        log.info("Successfully persisted WritingResult for submission {}, overallBand={}, version={}",
            submission.getId(), overallBand, nextVersion);
    }

    @Override
    @Transactional
    public void processEvaluationCompletedEvent(
        EventEnvelope<WritingEvaluationCompletedPayload> envelope,
        String rawPayload
    ) {
        log.info("Processing writing evaluation completed event for submissionId: {}, idempotencyKey: {}",
            envelope.payload().submissionId(), envelope.idempotencyKey());

        // 1. Atomic Inbox Deduplication
        int acquired = inboxEventRepository.tryAcquireInbox(
            envelope.eventId(),
            envelope.idempotencyKey(),
            envelope.eventType(),
            envelope.source(),
            rawPayload
        );

        if (acquired == 0) {
            log.warn("[DUPLICATE EVENT] IdempotencyKey {} already processed in Inbox. Skipping.", envelope.idempotencyKey());
            return;
        }

        // 2. Find WritingSubmission
        WritingSubmission submission = writingSubmissionRepository.findById(envelope.payload().submissionId())
            .orElseThrow(() -> new WritingSubmissionNotFoundException(envelope.payload().submissionId()));

        WritingEvaluationCompletedPayload payload = envelope.payload();

        // 3. Invalidate old active result atomically
        writingResultRepository.invalidateCurrentResult(submission.getId());

        // 4. Calculate official Cambridge IELTS rounded overall band
        BigDecimal overallBand = CambridgeRoundingUtil.calculateOverallBand(
            payload.taskAchievementScore(),
            payload.coherenceCohesionScore(),
            payload.lexicalResourceScore(),
            payload.grammaticalRangeScore()
        );

        List<WritingResult> pastResults = writingResultRepository.findBySubmissionIdOrderByResultVersionDesc(submission.getId());
        int nextVersion = pastResults.isEmpty() ? 1 : pastResults.get(0).getResultVersion() + 1;

        // 5. Build and save new WritingResult
        WritingResult result = new WritingResult();
        result.setSubmission(submission);
        result.setTaskAchievementScore(payload.taskAchievementScore());
        result.setCoherenceCohesionScore(payload.coherenceCohesionScore());
        result.setLexicalResourceScore(payload.lexicalResourceScore());
        result.setGrammaticalRangeScore(payload.grammaticalRangeScore());
        result.setOverallBand(overallBand);
        result.setFeedbackDetail(payload.feedbackDetail());
        result.setAiModelVersion("gemini-2.5-flash");
        result.setEvaluatedBy(EvaluatedBy.AI_AUTO);
        result.setResultVersion(nextVersion);
        result.setIsCurrent(true);
        result.setEvaluatedAt(Instant.now());

        writingResultRepository.save(result);

        // 6. Transition WritingSubmission to SCORED
        submission.markAsScored();
        writingSubmissionRepository.save(submission);

        log.info("Successfully processed evaluation completed event and saved WritingResult for submission {}, overallBand={}, version={}",
            submission.getId(), overallBand, nextVersion);
    }

    @Override
    @Transactional
    public void processEvaluationFailedEvent(
        EventEnvelope<WritingEvaluationFailedPayload> envelope,
        String rawPayload
    ) {
        log.warn("Processing writing evaluation failed event for submissionId: {}, error: {}",
            envelope.payload().submissionId(), envelope.payload().errorMessage());

        // 1. Atomic Inbox Deduplication
        int acquired = inboxEventRepository.tryAcquireInbox(
            envelope.eventId(),
            envelope.idempotencyKey(),
            envelope.eventType(),
            envelope.source(),
            rawPayload
        );

        if (acquired == 0) {
            log.warn("[DUPLICATE EVENT] IdempotencyKey {} already processed in Inbox. Skipping.", envelope.idempotencyKey());
            return;
        }

        // 2. Find WritingSubmission and transition to FAILED
        WritingSubmission submission = writingSubmissionRepository.findById(envelope.payload().submissionId())
            .orElseThrow(() -> new WritingSubmissionNotFoundException(envelope.payload().submissionId()));

        submission.setStatus(SubmissionStatus.FAILED);
        writingSubmissionRepository.save(submission);

        log.info("Successfully marked submission {} as FAILED following evaluation failure event", submission.getId());
    }
}
