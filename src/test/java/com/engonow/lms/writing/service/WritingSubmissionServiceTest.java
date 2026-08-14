package com.engonow.lms.writing.service;

import com.engonow.lms.entity.OutboxEvent;
import com.engonow.lms.repository.OutboxEventRepository;
import com.engonow.lms.writing.domain.entity.WritingResult;
import com.engonow.lms.writing.domain.entity.WritingSubmission;
import com.engonow.lms.writing.domain.enums.EvaluatedBy;
import com.engonow.lms.writing.domain.enums.SubmissionStatus;
import com.engonow.lms.writing.domain.enums.TaskType;
import com.engonow.lms.writing.domain.enums.WritingCriterion;
import com.engonow.lms.writing.domain.feedback.CohesiveDeviceAnalysis;
import com.engonow.lms.writing.domain.feedback.CriterionFeedback;
import com.engonow.lms.writing.domain.feedback.EssayMetrics;
import com.engonow.lms.writing.domain.feedback.WritingFeedbackDetail;
import com.engonow.lms.writing.dto.WritingResultResponseDTO;
import com.engonow.lms.writing.dto.WritingSubmissionRequestDTO;
import com.engonow.lms.writing.dto.WritingSubmissionResponseDTO;
import com.engonow.lms.writing.dto.WritingWebhookPayloadDTO;
import com.engonow.lms.writing.exception.WritingSubmissionNotFoundException;
import com.engonow.lms.writing.exception.WritingSubmissionProcessingException;
import com.engonow.lms.writing.repository.WritingResultRepository;
import com.engonow.lms.writing.repository.WritingSubmissionRepository;
import com.engonow.lms.writing.service.impl.WritingSubmissionServiceImpl;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.Spy;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class WritingSubmissionServiceTest {

    @Mock
    private WritingSubmissionRepository writingSubmissionRepository;

    @Mock
    private WritingResultRepository writingResultRepository;

    @Mock
    private OutboxEventRepository outboxEventRepository;

    @Spy
    private ObjectMapper objectMapper = new ObjectMapper();

    @InjectMocks
    private WritingSubmissionServiceImpl writingSubmissionService;

    private UUID studentId;
    private UUID submissionId;
    private WritingFeedbackDetail sampleFeedbackDetail;

    @BeforeEach
    void setUp() {
        studentId = UUID.randomUUID();
        submissionId = UUID.randomUUID();

        sampleFeedbackDetail = new WritingFeedbackDetail(
            "Solid Band 7.0 performance.",
            new EssayMetrics(280, 140, new BigDecimal("0.50"), new BigDecimal("18.0"), new BigDecimal("0.60")),
            List.of(
                new CriterionFeedback(WritingCriterion.TASK_RESPONSE, new BigDecimal("7.0"), "Addresses task well", List.of("Clear position"), List.of("Minor repetition"), "Expand ideas for Band 8"),
                new CriterionFeedback(WritingCriterion.COHERENCE_COHESION, new BigDecimal("7.0"), "Clear cohesion", List.of("Good linking"), List.of("Repetitive connector"), "Vary transitionals"),
                new CriterionFeedback(WritingCriterion.LEXICAL_RESOURCE, new BigDecimal("7.0"), "Good vocabulary", List.of("Academic lexicon"), List.of("Collocation slips"), "Use precise collocations"),
                new CriterionFeedback(WritingCriterion.GRAMMATICAL_RANGE_ACCURACY, new BigDecimal("7.0"), "Varied grammar", List.of("Complex sentences"), List.of("Occasional slip"), "Proofread SVA")
            ),
            List.of(),
            new CohesiveDeviceAnalysis(List.of("However"), List.of(), List.of()),
            List.of(),
            List.of()
        );
    }

    @Test
    @DisplayName("submitEssay persists submission and emits outbox event in PENDING state")
    void submitEssay_Success() {
        String essayText = "In recent years, remote work has gained substantial popularity across the globe. Many individuals consider working from home to be significantly more flexible and convenient compared to traditional office environments.";
        WritingSubmissionRequestDTO request = new WritingSubmissionRequestDTO(
            studentId,
            TaskType.TASK2,
            "Discuss the advantages and disadvantages of remote work.",
            essayText
        );

        when(writingSubmissionRepository.save(any(WritingSubmission.class))).thenAnswer(invocation -> {
            WritingSubmission sub = invocation.getArgument(0);
            sub.setId(submissionId);
            sub.setCreatedAt(Instant.now());
            return sub;
        });

        WritingSubmissionResponseDTO response = writingSubmissionService.submitEssay(request);

        assertThat(response).isNotNull();
        assertThat(response.id()).isEqualTo(submissionId);
        assertThat(response.studentId()).isEqualTo(studentId);
        assertThat(response.status()).isEqualTo(SubmissionStatus.PENDING);
        assertThat(response.wordCount()).isGreaterThanOrEqualTo(20);

        ArgumentCaptor<OutboxEvent> outboxCaptor = ArgumentCaptor.forClass(OutboxEvent.class);
        verify(outboxEventRepository).save(outboxCaptor.capture());
        OutboxEvent outboxEvent = outboxCaptor.getValue();
        assertThat(outboxEvent.getAggregateType()).isEqualTo("WRITING_SUBMISSION");
        assertThat(outboxEvent.getAggregateId()).isEqualTo(submissionId.toString());
        assertThat(outboxEvent.getEventType()).isEqualTo("WRITING_SUBMISSION_CREATED");
    }

    @Test
    @DisplayName("getSubmissionResult returns result DTO when submission is in SCORED status")
    void getSubmissionResult_Success() {
        WritingSubmission submission = new WritingSubmission();
        submission.setId(submissionId);
        submission.setStudentId(studentId);
        submission.setStatus(SubmissionStatus.SCORED);

        WritingResult result = new WritingResult();
        result.setId(UUID.randomUUID());
        result.setSubmission(submission);
        result.setTaskAchievementScore(new BigDecimal("7.0"));
        result.setCoherenceCohesionScore(new BigDecimal("7.0"));
        result.setLexicalResourceScore(new BigDecimal("7.0"));
        result.setGrammaticalRangeScore(new BigDecimal("7.0"));
        result.setOverallBand(new BigDecimal("7.0"));
        result.setFeedbackDetail(sampleFeedbackDetail);
        result.setEvaluatedBy(EvaluatedBy.AI_AUTO);
        result.setResultVersion(1);
        result.setIsCurrent(true);
        result.setEvaluatedAt(Instant.now());

        when(writingSubmissionRepository.findByIdAndStudentId(submissionId, studentId))
            .thenReturn(Optional.of(submission));
        when(writingResultRepository.findBySubmissionIdAndIsCurrentTrue(submissionId))
            .thenReturn(Optional.of(result));

        WritingResultResponseDTO response = writingSubmissionService.getSubmissionResult(submissionId, studentId);

        assertThat(response).isNotNull();
        assertThat(response.submissionId()).isEqualTo(submissionId);
        assertThat(response.overallBand()).isEqualByComparingTo("7.0");
        assertThat(response.evaluatedBy()).isEqualTo(EvaluatedBy.AI_AUTO);
    }

    @Test
    @DisplayName("getSubmissionResult throws ProcessingException when submission is PENDING")
    void getSubmissionResult_PendingStatus_ThrowsProcessingException() {
        WritingSubmission submission = new WritingSubmission();
        submission.setId(submissionId);
        submission.setStudentId(studentId);
        submission.setStatus(SubmissionStatus.PENDING);

        when(writingSubmissionRepository.findByIdAndStudentId(submissionId, studentId))
            .thenReturn(Optional.of(submission));

        assertThatThrownBy(() -> writingSubmissionService.getSubmissionResult(submissionId, studentId))
            .isInstanceOf(WritingSubmissionProcessingException.class)
            .hasMessageContaining("PENDING");
    }

    @Test
    @DisplayName("getSubmissionResult throws NotFoundException when submission does not exist")
    void getSubmissionResult_NotFound_ThrowsNotFoundException() {
        when(writingSubmissionRepository.findByIdAndStudentId(submissionId, studentId))
            .thenReturn(Optional.empty());

        assertThatThrownBy(() -> writingSubmissionService.getSubmissionResult(submissionId, studentId))
            .isInstanceOf(WritingSubmissionNotFoundException.class);
    }

    @Test
    @DisplayName("processEvaluationWebhook saves scored result and updates submission status")
    void processEvaluationWebhook_Success() {
        WritingSubmission submission = new WritingSubmission();
        submission.setId(submissionId);
        submission.setStudentId(studentId);
        submission.setStatus(SubmissionStatus.PENDING);

        WritingWebhookPayloadDTO payload = new WritingWebhookPayloadDTO(
            submissionId,
            new BigDecimal("7.0"),
            new BigDecimal("7.0"),
            new BigDecimal("6.5"),
            new BigDecimal("6.5"),
            sampleFeedbackDetail,
            "gemini-2.5-flash",
            "SUCCESS",
            null
        );

        when(writingSubmissionRepository.findById(submissionId)).thenReturn(Optional.of(submission));
        when(writingResultRepository.findBySubmissionIdOrderByResultVersionDesc(submissionId)).thenReturn(List.of());

        writingSubmissionService.processEvaluationWebhook(payload);

        verify(writingResultRepository).invalidateCurrentResult(submissionId);

        ArgumentCaptor<WritingResult> resultCaptor = ArgumentCaptor.forClass(WritingResult.class);
        verify(writingResultRepository).save(resultCaptor.capture());
        WritingResult savedResult = resultCaptor.getValue();
        // (7.0 + 7.0 + 6.5 + 6.5) / 4 = 6.75 -> Cambridge rounded to 7.0
        assertThat(savedResult.getOverallBand()).isEqualByComparingTo("7.0");
        assertThat(savedResult.getIsCurrent()).isTrue();
        assertThat(savedResult.getResultVersion()).isEqualTo(1);

        assertThat(submission.getStatus()).isEqualTo(SubmissionStatus.SCORED);
        verify(writingSubmissionRepository).save(submission);
    }

    @Test
    @DisplayName("processEvaluationWebhook marks submission as FAILED when status is FAILED")
    void processEvaluationWebhook_FailedStatus() {
        WritingSubmission submission = new WritingSubmission();
        submission.setId(submissionId);
        submission.setStudentId(studentId);
        submission.setStatus(SubmissionStatus.PENDING);

        WritingWebhookPayloadDTO payload = new WritingWebhookPayloadDTO(
            submissionId,
            new BigDecimal("0.0"),
            new BigDecimal("0.0"),
            new BigDecimal("0.0"),
            new BigDecimal("0.0"),
            sampleFeedbackDetail,
            "gemini-2.5-flash",
            "FAILED",
            "Quota exceeded"
        );

        when(writingSubmissionRepository.findById(submissionId)).thenReturn(Optional.of(submission));

        writingSubmissionService.processEvaluationWebhook(payload);

        assertThat(submission.getStatus()).isEqualTo(SubmissionStatus.FAILED);
        verify(writingResultRepository, never()).save(any());
        verify(writingSubmissionRepository).save(submission);
    }
}
