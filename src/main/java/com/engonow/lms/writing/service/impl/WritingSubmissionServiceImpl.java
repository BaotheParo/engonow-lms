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
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Service
@Transactional
@RequiredArgsConstructor
@Slf4j
public class WritingSubmissionServiceImpl implements WritingSubmissionService {

    private final WritingSubmissionRepository writingSubmissionRepository;
    private final WritingResultRepository writingResultRepository;
    private final OutboxEventRepository outboxEventRepository;
    private final ObjectMapper objectMapper;

    @Override
    public WritingSubmissionResponseDTO submitEssay(WritingSubmissionRequestDTO request) {
        log.info("Received IELTS Writing submission request for student: {}, taskType: {}",
            request.studentId(), request.taskType());

        // 1. Fail-fast serialization before touching DB or repositories
        String serializedPayload;
        try {
            serializedPayload = objectMapper.writeValueAsString(request);
        } catch (JsonProcessingException e) {
            log.error("Failed to serialize writing submission request to JSON: {}", e.getMessage(), e);
            throw new IllegalArgumentException("Failed to serialize writing submission request to JSON", e);
        }

        // 2. Persist submission in PENDING status
        int wordCount = WritingSubmissionRequestDTO.countWords(request.essayText());

        WritingSubmission submission = new WritingSubmission();
        submission.setStudentId(request.studentId());
        submission.setTaskType(request.taskType());
        submission.setTaskPrompt(request.taskPrompt());
        submission.setEssayText(request.essayText());
        submission.setWordCount(wordCount);
        submission.setStatus(SubmissionStatus.PENDING);

        WritingSubmission savedSubmission = writingSubmissionRepository.save(submission);

        // 3. Persist corresponding Transactional Outbox event
        OutboxEvent outboxEvent = OutboxEvent.builder()
            .aggregateType("WRITING_SUBMISSION")
            .aggregateId(savedSubmission.getId().toString())
            .eventType("WRITING_SUBMISSION_CREATED")
            .payload(serializedPayload)
            .status(OutboxStatus.PENDING)
            .retryCount(0)
            .build();
        outboxEventRepository.save(outboxEvent);

        log.info("Successfully created writing submission {} and corresponding outbox event", savedSubmission.getId());
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
}
