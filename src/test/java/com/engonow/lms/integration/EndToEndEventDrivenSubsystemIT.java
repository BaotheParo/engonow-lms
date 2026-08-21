package com.engonow.lms.integration;

import com.engonow.lms.dto.AudioReferenceDTO;
import com.engonow.lms.dto.SpeakingSubmissionRequestDTO;
import com.engonow.lms.dto.SpeakingSubmissionResponseDTO;
import com.engonow.lms.entity.InboxEvent;
import com.engonow.lms.entity.OutboxEvent;
import com.engonow.lms.entity.SpeakingSessionResult;
import com.engonow.lms.enums.OutboxStatus;
import com.engonow.lms.enums.SpeakingEvaluationStatus;
import com.engonow.lms.repository.ExamRepository;
import com.engonow.lms.repository.InboxEventRepository;
import com.engonow.lms.repository.MockTestBookingRepository;
import com.engonow.lms.repository.OutboxEventRepository;
import com.engonow.lms.repository.SpeakingSessionResultRepository;
import com.engonow.lms.repository.TestSubmissionRepository;
import com.engonow.lms.repository.UserRepository;
import com.engonow.lms.service.impl.CloudinaryStorageMock;
import com.engonow.lms.service.impl.SubmissionServiceImpl;
import com.engonow.lms.speaking.event.SpeakingEvaluationCompletedPayload;
import com.engonow.lms.speaking.event.SpeakingEvaluationFailedPayload;
import com.engonow.lms.speaking.listener.SpeakingResultKafkaListener;
import com.engonow.lms.writing.domain.entity.WritingResult;
import com.engonow.lms.writing.domain.entity.WritingSubmission;
import com.engonow.lms.writing.domain.enums.SubmissionStatus;
import com.engonow.lms.writing.domain.enums.TaskType;
import com.engonow.lms.writing.domain.enums.WritingCriterion;
import com.engonow.lms.writing.domain.feedback.CohesiveDeviceAnalysis;
import com.engonow.lms.writing.domain.feedback.CriterionFeedback;
import com.engonow.lms.writing.domain.feedback.EssayMetrics;
import com.engonow.lms.writing.domain.feedback.WritingFeedbackDetail;
import com.engonow.lms.writing.dto.WritingSubmissionRequestDTO;
import com.engonow.lms.writing.dto.WritingSubmissionResponseDTO;
import com.engonow.lms.writing.event.EventEnvelope;
import com.engonow.lms.writing.event.OutboxEventCreatedLocalEvent;
import com.engonow.lms.writing.event.WritingEvaluationCompletedPayload;
import com.engonow.lms.writing.listener.WritingResultKafkaListener;
import com.engonow.lms.writing.repository.WritingResultRepository;
import com.engonow.lms.writing.repository.WritingSubmissionRepository;
import com.engonow.lms.writing.service.impl.WritingSubmissionServiceImpl;
import com.engonow.lms.writing.util.CambridgeRoundingUtil;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.Spy;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.web.reactive.function.client.WebClient;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
public class EndToEndEventDrivenSubsystemIT {

    @Spy
    private ObjectMapper objectMapper = new ObjectMapper().findAndRegisterModules();

    @Mock
    private WritingSubmissionRepository writingSubmissionRepository;

    @Mock
    private WritingResultRepository writingResultRepository;

    @Mock
    private SpeakingSessionResultRepository speakingSessionResultRepository;

    @Mock
    private OutboxEventRepository outboxEventRepository;

    @Mock
    private InboxEventRepository inboxEventRepository;

    @Mock
    private ApplicationEventPublisher applicationEventPublisher;

    @Mock
    private Acknowledgment acknowledgment;

    @Mock
    private ExamRepository examRepository;
    @Mock
    private TestSubmissionRepository testSubmissionRepository;
    @Mock
    private UserRepository userRepository;
    @Mock
    private WebClient aiWebClient;
    @Mock
    private CloudinaryStorageMock cloudinaryStorageMock;
    @Mock
    private MockTestBookingRepository mockTestBookingRepository;

    private WritingSubmissionServiceImpl writingSubmissionService;
    private SubmissionServiceImpl speakingSubmissionService;
    private WritingResultKafkaListener writingResultKafkaListener;
    private SpeakingResultKafkaListener speakingResultKafkaListener;

    private UUID studentId;

    @BeforeEach
    void setUp() {
        studentId = UUID.randomUUID();

        writingSubmissionService = new WritingSubmissionServiceImpl(
            writingSubmissionRepository,
            writingResultRepository,
            outboxEventRepository,
            inboxEventRepository,
            applicationEventPublisher,
            objectMapper
        );

        speakingSubmissionService = new SubmissionServiceImpl(
            examRepository,
            testSubmissionRepository,
            userRepository,
            aiWebClient,
            null,
            cloudinaryStorageMock,
            mockTestBookingRepository,
            speakingSessionResultRepository,
            outboxEventRepository,
            objectMapper
        );
        speakingSubmissionService.setApplicationEventPublisher(applicationEventPublisher);

        writingResultKafkaListener = new WritingResultKafkaListener(
            writingSubmissionService,
            objectMapper
        );

        speakingResultKafkaListener = new SpeakingResultKafkaListener(
            speakingSessionResultRepository,
            inboxEventRepository,
            objectMapper
        );
    }

    @Test
    @DisplayName("1. E2E Writing Subsystem: Submit -> Outbox -> Worker Result -> Inbox -> SCORED")
    void testWritingSubsystemFullRoundTrip() throws Exception {
        // Step 1: Submit essay
        WritingSubmissionRequestDTO request = new WritingSubmissionRequestDTO(
            studentId,
            TaskType.TASK2,
            "Some people think technology increases freedom.",
            "In recent decades, the rapid proliferation of digital technology has fundamentally transformed how individuals communicate and conduct business. Many argue that technology provides unprecedented freedom..."
        );

        when(writingSubmissionRepository.save(any(WritingSubmission.class))).thenAnswer(i -> {
            WritingSubmission sub = i.getArgument(0);
            sub.setId(UUID.randomUUID());
            return sub;
        });

        when(outboxEventRepository.save(any(OutboxEvent.class))).thenAnswer(i -> {
            OutboxEvent event = i.getArgument(0);
            event.setId(UUID.randomUUID());
            return event;
        });

        WritingSubmissionResponseDTO response = writingSubmissionService.submitEssay(request);
        assertThat(response).isNotNull();
        assertThat(response.status()).isEqualTo(SubmissionStatus.PENDING);
        UUID submissionId = response.id();

        // Step 2: Verify Outbox LocalEvent published for Kafka dispatcher
        ArgumentCaptor<OutboxEventCreatedLocalEvent> localEventCaptor = ArgumentCaptor.forClass(OutboxEventCreatedLocalEvent.class);
        verify(applicationEventPublisher).publishEvent(localEventCaptor.capture());
        assertThat(localEventCaptor.getValue().topic()).isEqualTo("engonow.writing.evaluation-requested.v1");

        // Step 3: Simulate Python AI Worker completed response
        WritingFeedbackDetail feedbackDetail = new WritingFeedbackDetail(
            "Clear argumentation with well-developed ideas.",
            new EssayMetrics(280, 140, new BigDecimal("0.50"), new BigDecimal("18.0"), new BigDecimal("0.60")),
            List.of(
                new CriterionFeedback(WritingCriterion.TASK_RESPONSE, new BigDecimal("6.0"), "Addresses task", List.of("Clear position"), List.of("Minor repetition"), "Expand examples"),
                new CriterionFeedback(WritingCriterion.COHERENCE_COHESION, new BigDecimal("5.0"), "Cohesion", List.of("Linking"), List.of("Repetitive connectors"), "Vary transitionals"),
                new CriterionFeedback(WritingCriterion.LEXICAL_RESOURCE, new BigDecimal("6.0"), "Vocabulary", List.of("Topic lexicon"), List.of("Collocation slips"), "Use precise collocations"),
                new CriterionFeedback(WritingCriterion.GRAMMATICAL_RANGE_ACCURACY, new BigDecimal("5.0"), "Grammar", List.of("Complex clauses"), List.of("Occasional slip"), "Proofread SVA")
            ),
            List.of(),
            new CohesiveDeviceAnalysis(List.of("Furthermore"), List.of(), List.of()),
            List.of(),
            List.of()
        );

        // (6.0 + 5.0 + 6.0 + 5.0) / 4 = 5.5
        WritingEvaluationCompletedPayload payload = new WritingEvaluationCompletedPayload(
            submissionId,
            new BigDecimal("6.0"),
            new BigDecimal("5.0"),
            new BigDecimal("6.0"),
            new BigDecimal("5.0"),
            new BigDecimal("5.5"),
            feedbackDetail
        );

        UUID eventId = UUID.randomUUID();
        UUID idempotencyKey = UUID.randomUUID();
        EventEnvelope<WritingEvaluationCompletedPayload> envelope = new EventEnvelope<>(
            eventId,
            idempotencyKey,
            "WRITING_EVALUATION_COMPLETED",
            "1.0",
            Instant.now(),
            Instant.now(),
            "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            submissionId.toString(),
            "engonow-ai-writing-worker",
            0,
            payload
        );

        String envelopeJson = objectMapper.writeValueAsString(envelope);
        ConsumerRecord<String, String> record = new ConsumerRecord<>(
            "engonow.writing.evaluation-completed.v1",
            0,
            0L,
            submissionId.toString(),
            envelopeJson
        );

        WritingSubmission pendingSubmission = new WritingSubmission();
        pendingSubmission.setId(submissionId);
        pendingSubmission.setStatus(SubmissionStatus.PENDING);
        pendingSubmission.setStudentId(studentId);

        when(inboxEventRepository.tryAcquireInbox(eq(eventId), eq(idempotencyKey), eq("WRITING_EVALUATION_COMPLETED"), any(), any()))
            .thenReturn(1);
        when(writingSubmissionRepository.findById(submissionId)).thenReturn(Optional.of(pendingSubmission));

        // Step 4: Handle completed event in Kafka consumer
        writingResultKafkaListener.handleEvaluationCompleted(record, acknowledgment);

        // Step 5: Verify WritingResult saved with Cambridge rounded overall band 5.5 and status SCORED
        ArgumentCaptor<WritingResult> resultCaptor = ArgumentCaptor.forClass(WritingResult.class);
        verify(writingResultRepository).save(resultCaptor.capture());
        WritingResult savedResult = resultCaptor.getValue();
        assertThat(savedResult.getOverallBand()).isEqualByComparingTo("5.5");
        assertThat(savedResult.getTaskAchievementScore()).isEqualByComparingTo("6.0");
        assertThat(savedResult.getCoherenceCohesionScore()).isEqualByComparingTo("5.0");
        assertThat(savedResult.getIsCurrent()).isTrue();

        assertThat(pendingSubmission.getStatus()).isEqualTo(SubmissionStatus.SCORED);
        verify(acknowledgment).acknowledge();
    }

    @Test
    @DisplayName("2. E2E Speaking Subsystem: Claim-Check Submit -> Outbox -> Worker Result -> Inbox -> SUCCESS")
    void testSpeakingClaimCheckRoundTrip() throws Exception {
        // Step 1: Submit speaking recording using AudioReferenceDTO (Claim-Check pattern)
        AudioReferenceDTO audioRef = new AudioReferenceDTO(
            "MINIO",
            "engonow-audio-bucket",
            "recordings/2026/08/attempt-001.wav",
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "audio/wav",
            120.0
        );

        SpeakingSubmissionRequestDTO request = new SpeakingSubmissionRequestDTO(
            studentId,
            "PART_2",
            "Describe an unforgettable journey you have taken.",
            audioRef
        );

        when(outboxEventRepository.save(any(OutboxEvent.class))).thenAnswer(i -> {
            OutboxEvent event = i.getArgument(0);
            event.setId(UUID.randomUUID());
            return event;
        });

        SpeakingSubmissionResponseDTO response = speakingSubmissionService.submitSpeakingEvaluation(request);
        assertThat(response).isNotNull();
        assertThat(response.status()).isEqualTo(SpeakingEvaluationStatus.PENDING);
        String attemptIdStr = response.sessionId();
        UUID attemptId = UUID.fromString(attemptIdStr);

        // Step 2: Verify Outbox event contains ZERO raw binary bytes and points to topic
        ArgumentCaptor<OutboxEventCreatedLocalEvent> localEventCaptor = ArgumentCaptor.forClass(OutboxEventCreatedLocalEvent.class);
        verify(applicationEventPublisher).publishEvent(localEventCaptor.capture());
        assertThat(localEventCaptor.getValue().topic()).isEqualTo("engonow.speaking.evaluation-requested.v1");
        assertThat(localEventCaptor.getValue().rawEnvelopeJson()).contains("recordings/2026/08/attempt-001.wav");
        assertThat(localEventCaptor.getValue().rawEnvelopeJson()).doesNotContain("data:audio");

        // Step 3: Simulate Python acoustic engine emitting completed evaluation
        JsonNode feedbackDetail = objectMapper.readTree("{\"transcript\":\"I would like to describe a trip...\",\"speechMetrics\":{\"wpm\":145.0}}");
        SpeakingEvaluationCompletedPayload completedPayload = new SpeakingEvaluationCompletedPayload(
            attemptId,
            new BigDecimal("7.0"),
            new BigDecimal("7.5"),
            new BigDecimal("7.0"),
            new BigDecimal("7.0"),
            new BigDecimal("7.0"),
            feedbackDetail
        );

        UUID eventId = UUID.randomUUID();
        UUID idempotencyKey = UUID.randomUUID();
        EventEnvelope<SpeakingEvaluationCompletedPayload> envelope = new EventEnvelope<>(
            eventId,
            idempotencyKey,
            "SPEAKING_EVALUATION_COMPLETED",
            "1.0",
            Instant.now(),
            Instant.now(),
            UUID.randomUUID().toString(),
            attemptId.toString(),
            "engonow-ai-speaking-worker",
            0,
            completedPayload
        );

        String envelopeJson = objectMapper.writeValueAsString(envelope);
        ConsumerRecord<String, String> record = new ConsumerRecord<>(
            "engonow.speaking.evaluation-completed.v1",
            0,
            0L,
            attemptId.toString(),
            envelopeJson
        );

        when(inboxEventRepository.tryAcquireInbox(eq(eventId), eq(idempotencyKey), eq("SPEAKING_EVALUATION_COMPLETED"), any(), any()))
            .thenReturn(1);

        SpeakingSessionResult existingSession = SpeakingSessionResult.builder()
            .sessionId(attemptIdStr)
            .evaluationStatus(SpeakingEvaluationStatus.PENDING)
            .build();
        when(speakingSessionResultRepository.findBySessionId(attemptIdStr)).thenReturn(Optional.of(existingSession));

        // Step 4: Handle speaking result in Kafka listener
        speakingResultKafkaListener.handleEvaluationCompleted(record, acknowledgment);

        // Step 5: Verify SpeakingSessionResult is updated to SUCCESS with Cambridge overallBand 7.5
        ArgumentCaptor<SpeakingSessionResult> resultCaptor = ArgumentCaptor.forClass(SpeakingSessionResult.class);
        verify(speakingSessionResultRepository, org.mockito.Mockito.atLeastOnce()).save(resultCaptor.capture());
        SpeakingSessionResult savedResult = resultCaptor.getValue();
        assertThat(savedResult.getEvaluationStatus()).isEqualTo(SpeakingEvaluationStatus.SUCCESS);
        assertThat(savedResult.getIsComplete()).isTrue();
        assertThat(savedResult.getAiScore()).isEqualByComparingTo("7.5");
        verify(acknowledgment).acknowledge();
    }

    @Test
    @DisplayName("3. Dual-Inbox Deduplication: Identical idempotencyKey processed exactly once")
    void testDualInboxDeduplicationEndToEnd() throws Exception {
        UUID attemptId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();
        UUID idempotencyKey = UUID.randomUUID();

        JsonNode feedbackDetail = objectMapper.readTree("{\"speechMetrics\":{}}");
        SpeakingEvaluationCompletedPayload payload = new SpeakingEvaluationCompletedPayload(
            attemptId,
            new BigDecimal("6.0"),
            new BigDecimal("6.0"),
            new BigDecimal("6.0"),
            new BigDecimal("6.0"),
            new BigDecimal("6.0"),
            feedbackDetail
        );

        EventEnvelope<SpeakingEvaluationCompletedPayload> envelope = new EventEnvelope<>(
            eventId,
            idempotencyKey,
            "SPEAKING_EVALUATION_COMPLETED",
            "1.0",
            Instant.now(),
            Instant.now(),
            "trace-dup",
            attemptId.toString(),
            "worker",
            0,
            payload
        );

        String envelopeJson = objectMapper.writeValueAsString(envelope);
        ConsumerRecord<String, String> record = new ConsumerRecord<>(
            "engonow.speaking.evaluation-completed.v1",
            0,
            0L,
            attemptId.toString(),
            envelopeJson
        );

        // First delivery: inbox acquires lock (return 1)
        when(inboxEventRepository.tryAcquireInbox(eq(eventId), eq(idempotencyKey), any(), any(), any()))
            .thenReturn(1);
        when(speakingSessionResultRepository.findBySessionId(attemptId.toString()))
            .thenReturn(Optional.of(SpeakingSessionResult.builder().sessionId(attemptId.toString()).build()));

        speakingResultKafkaListener.handleEvaluationCompleted(record, acknowledgment);
        verify(speakingSessionResultRepository).save(any());

        // Second delivery (duplicate): inbox rejects (return 0)
        when(inboxEventRepository.tryAcquireInbox(eq(eventId), eq(idempotencyKey), any(), any(), any()))
            .thenReturn(0);

        speakingResultKafkaListener.handleEvaluationCompleted(record, acknowledgment);
        // Repository save was only called once for the first delivery
        verify(speakingSessionResultRepository).save(any());
    }

    @Test
    @DisplayName("4. Poison Pill / Failure Event Handling")
    void testPoisonPillDeadLetterQueueRecovery() throws Exception {
        UUID attemptId = UUID.randomUUID();

        SpeakingEvaluationFailedPayload payload = new SpeakingEvaluationFailedPayload(
            attemptId,
            "AUDIO_CORRUPTED",
            "Audio duration is 0 seconds",
            false,
            Instant.now()
        );

        EventEnvelope<SpeakingEvaluationFailedPayload> envelope = new EventEnvelope<>(
            UUID.randomUUID(),
            UUID.randomUUID(),
            "SPEAKING_EVALUATION_FAILED",
            "1.0",
            Instant.now(),
            Instant.now(),
            "trace-fail",
            attemptId.toString(),
            "worker",
            0,
            payload
        );

        String failedEnvelopeJson = objectMapper.writeValueAsString(envelope);
        ConsumerRecord<String, String> record = new ConsumerRecord<>(
            "engonow.speaking.evaluation-failed.v1",
            0,
            0L,
            attemptId.toString(),
            failedEnvelopeJson
        );

        SpeakingSessionResult pending = SpeakingSessionResult.builder()
            .sessionId(attemptId.toString())
            .evaluationStatus(SpeakingEvaluationStatus.PENDING)
            .build();
        when(speakingSessionResultRepository.findBySessionId(attemptId.toString())).thenReturn(Optional.of(pending));

        speakingResultKafkaListener.handleEvaluationFailed(record, acknowledgment);

        verify(speakingSessionResultRepository).save(pending);
        assertThat(pending.getEvaluationStatus()).isEqualTo(SpeakingEvaluationStatus.FAILED);
        verify(acknowledgment).acknowledge();
    }
}
