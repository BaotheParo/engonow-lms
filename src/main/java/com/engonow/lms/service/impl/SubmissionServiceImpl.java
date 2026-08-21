package com.engonow.lms.service.impl;

import com.engonow.lms.dto.AudioReferenceDTO;
import com.engonow.lms.dto.OmrAnswer;
import com.engonow.lms.dto.SpeakingEvaluationEventPayload;
import com.engonow.lms.dto.SpeakingSubmissionRequestDTO;
import com.engonow.lms.dto.SpeakingSubmissionResponseDTO;
import com.engonow.lms.dto.SubmissionResponseDTO;
import com.engonow.lms.entity.AnswerKey;
import com.engonow.lms.entity.Exam;
import com.engonow.lms.entity.MockTestBooking;
import com.engonow.lms.entity.OutboxEvent;
import com.engonow.lms.entity.SpeakingSessionResult;
import com.engonow.lms.entity.SubmissionDetail;
import com.engonow.lms.entity.TestSubmission;
import com.engonow.lms.entity.User;
import com.engonow.lms.enums.OutboxStatus;
import com.engonow.lms.enums.SpeakingEvaluationStatus;
import com.engonow.lms.exception.DuplicateWebhookException;
import com.engonow.lms.mapper.SubmissionMapper;
import com.engonow.lms.repository.ExamRepository;
import com.engonow.lms.repository.MockTestBookingRepository;
import com.engonow.lms.repository.OutboxEventRepository;
import com.engonow.lms.repository.SpeakingSessionResultRepository;
import com.engonow.lms.repository.TestSubmissionRepository;
import com.engonow.lms.repository.UserRepository;
import com.engonow.lms.service.SubmissionService;
import com.engonow.lms.speaking.event.SpeakingEvaluationRequestedPayload;
import com.engonow.lms.writing.event.EventEnvelope;
import com.engonow.lms.writing.event.OutboxEventCreatedLocalEvent;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;

import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
@Slf4j
public class SubmissionServiceImpl implements SubmissionService {

    public static final String SPEAKING_EVALUATION_REQUESTED_TOPIC = "engonow.speaking.evaluation-requested.v1";
    public static final String AGGREGATE_TYPE_SPEAKING_ATTEMPT = "SPEAKING_ATTEMPT";
    public static final String EVENT_TYPE_SPEAKING_EVALUATION_REQUESTED = "SPEAKING_EVALUATION_REQUESTED";

    private static final Set<String> ALLOWED_AUDIO_TYPES = Set.of(
        "audio/mpeg", "audio/mp3", "audio/wav", "audio/m4a", "audio/webm", "audio/mp4", "audio/ogg", "audio/x-wav"
    );

    private final ExamRepository examRepository;
    private final TestSubmissionRepository testSubmissionRepository;
    private final UserRepository userRepository;
    private final WebClient aiWebClient;
    private final SubmissionMapper submissionMapper;
    private final CloudinaryStorageMock cloudinaryStorageMock;
    private final MockTestBookingRepository mockTestBookingRepository;
    private final SpeakingSessionResultRepository speakingSessionResultRepository;
    private final OutboxEventRepository outboxEventRepository;
    private final ObjectMapper objectMapper;
    private ApplicationEventPublisher applicationEventPublisher;

    public SubmissionServiceImpl(
            ExamRepository examRepository,
            TestSubmissionRepository testSubmissionRepository,
            UserRepository userRepository,
            @Qualifier("aiWebClient") WebClient aiWebClient,
            SubmissionMapper submissionMapper,
            CloudinaryStorageMock cloudinaryStorageMock,
            MockTestBookingRepository mockTestBookingRepository,
            SpeakingSessionResultRepository speakingSessionResultRepository,
            OutboxEventRepository outboxEventRepository,
            ObjectMapper objectMapper) {
        this.examRepository = examRepository;
        this.testSubmissionRepository = testSubmissionRepository;
        this.userRepository = userRepository;
        this.aiWebClient = aiWebClient;
        this.submissionMapper = submissionMapper;
        this.cloudinaryStorageMock = cloudinaryStorageMock;
        this.mockTestBookingRepository = mockTestBookingRepository;
        this.speakingSessionResultRepository = speakingSessionResultRepository;
        this.outboxEventRepository = outboxEventRepository;
        this.objectMapper = objectMapper;
    }

    @Autowired(required = false)
    public void setApplicationEventPublisher(ApplicationEventPublisher applicationEventPublisher) {
        this.applicationEventPublisher = applicationEventPublisher;
    }

    @Override
    @Transactional
    public SubmissionResponseDTO processOmrScan(Long examId, Long studentId, MultipartFile file) {
        byte[] fileBytes;
        try {
            fileBytes = file.getBytes();
        } catch (IOException e) {
            throw new RuntimeException("Failed to read file bytes from multipart file", e);
        }

        // Trigger Cloudinary Mock upload asynchronously
        cloudinaryStorageMock.uploadFileAsync(file.getOriginalFilename(), fileBytes);

        // Fetch Exam using JOIN FETCH to avoid N+1 query
        Exam exam = examRepository.findByIdWithAnswerKeys(examId)
                .orElseThrow(() -> new IllegalArgumentException("Exam not found or inactive: " + examId));

        // Fetch Student
        User student = userRepository.findById(studentId)
                .orElseThrow(() -> new IllegalArgumentException("Student not found: " + studentId));

        // Prepare Multipart request for Mock Python AI Scanner service
        MultipartBodyBuilder bodyBuilder = new MultipartBodyBuilder();
        bodyBuilder.part("exam_id", examId);
        bodyBuilder.part("file", new ByteArrayResource(fileBytes) {
            @Override
            public String getFilename() {
                return file.getOriginalFilename() != null ? file.getOriginalFilename() : "sheet.png";
            }
        });

        // Call OMR scanning microservice synchronously
        List<OmrAnswer> omrAnswers = aiWebClient.post()
                .uri("/api/v1/ai/omr-scan")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(BodyInserters.fromMultipartData(bodyBuilder.build()))
                .retrieve()
                .bodyToMono(new ParameterizedTypeReference<List<OmrAnswer>>() {})
                .block();

        if (omrAnswers == null) {
            throw new RuntimeException("Failed to receive response from external OMR AI service.");
        }

        // Map answer keys by question number for O(1) lookups
        Map<Integer, AnswerKey> answerKeyMap = exam.getAnswerKeys().stream()
                .collect(Collectors.toMap(AnswerKey::getQuestionNumber, Function.identity()));

        // Create parent TestSubmission entity
        TestSubmission submission = TestSubmission.builder()
                .student(student)
                .exam(exam)
                .imageUrl("http://cloudinary-mock-url/omr-scans/" + file.getOriginalFilename())
                .isGraded(true)
                .totalQuestions(exam.getTotalQuestions())
                .details(new ArrayList<>())
                .build();

        int totalCorrect = 0;

        // Process details and auto-grade
        for (OmrAnswer omrAnswer : omrAnswers) {
            AnswerKey correctKey = answerKeyMap.get(omrAnswer.questionNumber());
            if (correctKey == null) {
                continue; // Ignore questions that are not defined in the exam
            }

            boolean isCorrect = omrAnswer.studentAnswer() == correctKey.getCorrectOption();
            if (isCorrect) {
                totalCorrect++;
            }

            SubmissionDetail detail = SubmissionDetail.builder()
                    .questionNumber(omrAnswer.questionNumber())
                    .studentAnswer(omrAnswer.studentAnswer())
                    .correctAnswer(correctKey.getCorrectOption())
                    .isCorrect(isCorrect)
                    .build();

            // Link detail using helper method
            submission.addDetail(detail);
        }

        // Calculate and set final scores using BigDecimal
        submission.setScore(totalCorrect);

        BigDecimal correctCount = BigDecimal.valueOf(totalCorrect);
        BigDecimal totalCount = BigDecimal.valueOf(exam.getTotalQuestions());
        BigDecimal percentage = totalCount.compareTo(BigDecimal.ZERO) > 0
                ? correctCount.divide(totalCount, 4, RoundingMode.HALF_UP).multiply(BigDecimal.valueOf(100)).setScale(2, RoundingMode.HALF_UP)
                : BigDecimal.ZERO.setScale(2, RoundingMode.HALF_UP);

        submission.setPercentage(percentage.doubleValue());

        // Persist to Database
        TestSubmission savedSubmission = testSubmissionRepository.save(submission);

        return submissionMapper.toResponseDto(savedSubmission);
    }

    @Override
    @Transactional
    public SpeakingSubmissionResponseDTO submitSpeakingEvaluation(
            SpeakingSubmissionRequestDTO request) {

        // Modern Claim-Check path
        if (request.audioRef() != null) {
            return processClaimCheckSpeakingSubmission(request);
        }

        // Legacy booking session path
        return processLegacyBookingSpeakingSubmission(request);
    }

    private SpeakingSubmissionResponseDTO processClaimCheckSpeakingSubmission(SpeakingSubmissionRequestDTO request) {
        AudioReferenceDTO audioRef = request.audioRef();
        if (audioRef.objectKey() == null || audioRef.objectKey().isBlank()) {
            throw new IllegalArgumentException("Audio reference objectKey must not be blank");
        }
        if (audioRef.contentType() == null || !ALLOWED_AUDIO_TYPES.contains(audioRef.contentType().toLowerCase())) {
            throw new IllegalArgumentException("Unsupported audio content type: " + audioRef.contentType());
        }

        UUID attemptId = request.sessionId() != null && isValidUUID(request.sessionId())
            ? UUID.fromString(request.sessionId())
            : UUID.randomUUID();
        UUID studentId = request.studentId() != null ? request.studentId() : UUID.randomUUID();
        String part = request.part() != null ? request.part() : "PART_1";

        SpeakingEvaluationRequestedPayload payload = new SpeakingEvaluationRequestedPayload(
            attemptId,
            studentId,
            part,
            audioRef
        );

        String traceId = UUID.randomUUID().toString();
        EventEnvelope<SpeakingEvaluationRequestedPayload> envelope = EventEnvelope.of(
            EVENT_TYPE_SPEAKING_EVALUATION_REQUESTED,
            attemptId,
            attemptId.toString(),
            traceId,
            "engonow-lms-backend",
            payload
        );

        String serializedEnvelope;
        try {
            serializedEnvelope = objectMapper.writeValueAsString(envelope);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Failed to serialize speaking evaluation event envelope", e);
        }

        // Persist pending speaking result
        SpeakingSessionResult pendingResult = SpeakingSessionResult.builder()
            .sessionId(attemptId.toString())
            .evaluationStatus(SpeakingEvaluationStatus.PENDING)
            .isComplete(false)
            .build();
        speakingSessionResultRepository.save(pendingResult);

        // Persist Transactional Outbox event
        OutboxEvent outboxEvent = OutboxEvent.builder()
            .aggregateType(AGGREGATE_TYPE_SPEAKING_ATTEMPT)
            .aggregateId(attemptId.toString())
            .eventType(EVENT_TYPE_SPEAKING_EVALUATION_REQUESTED)
            .schemaVersion("1.0")
            .traceId(traceId)
            .correlationId(attemptId.toString())
            .payload(serializedEnvelope)
            .status(OutboxStatus.PENDING)
            .retryCount(0)
            .build();
        OutboxEvent savedOutbox = outboxEventRepository.save(outboxEvent);

        if (applicationEventPublisher != null) {
            applicationEventPublisher.publishEvent(new OutboxEventCreatedLocalEvent(
                savedOutbox.getId(),
                SPEAKING_EVALUATION_REQUESTED_TOPIC,
                attemptId.toString(),
                serializedEnvelope,
                Map.of(
                    "eventId", envelope.eventId().toString().getBytes(StandardCharsets.UTF_8),
                    "traceId", traceId.getBytes(StandardCharsets.UTF_8),
                    "correlationId", attemptId.toString().getBytes(StandardCharsets.UTF_8)
                )
            ));
        }

        log.info("[SPEAKING SUBMISSION] Accepted claim-check speaking attempt: {} for student: {}",
            attemptId, studentId);

        return new SpeakingSubmissionResponseDTO(
            attemptId.toString(),
            SpeakingEvaluationStatus.PENDING,
            "Speaking evaluation accepted for asynchronous processing"
        );
    }

    private SpeakingSubmissionResponseDTO processLegacyBookingSpeakingSubmission(SpeakingSubmissionRequestDTO request) {
        Long bookingId = parseBookingId(request.sessionId());

        MockTestBooking booking = mockTestBookingRepository.findById(bookingId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "MockTestBooking not found for session ID: " + request.sessionId()));

        if (speakingSessionResultRepository.findBySessionId(request.sessionId()).isPresent()) {
            throw new DuplicateWebhookException(
                    "Speaking session " + request.sessionId() + " has already been submitted.");
        }

        Instant requestedAt = Instant.now();
        SpeakingEvaluationEventPayload eventPayload =
                new SpeakingEvaluationEventPayload(
                        request.sessionId(),
                        request.questionsMetadata(),
                        request.audioUrl(),
                        requestedAt);

        String serializedPayload;
        try {
            serializedPayload = objectMapper.writeValueAsString(eventPayload);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException(
                    "Failed to serialize speaking evaluation event payload", e);
        }

        SpeakingSessionResult pendingResult = SpeakingSessionResult.builder()
                .booking(booking)
                .sessionId(request.sessionId())
                .evaluationStatus(SpeakingEvaluationStatus.PENDING)
                .isComplete(false)
                .build();
        speakingSessionResultRepository.save(pendingResult);

        OutboxEvent outboxEvent = OutboxEvent.builder()
                .aggregateType("SPEAKING_SESSION")
                .aggregateId(request.sessionId())
                .eventType("SPEAKING_EVALUATION_REQUESTED")
                .payload(serializedPayload)
                .status(OutboxStatus.PENDING)
                .retryCount(0)
                .build();
        outboxEventRepository.save(outboxEvent);

        return new SpeakingSubmissionResponseDTO(
                request.sessionId(),
                SpeakingEvaluationStatus.PENDING,
                "Speaking evaluation accepted for asynchronous processing");
    }

    private Long parseBookingId(String sessionId) {
        try {
            return Long.parseLong(sessionId);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(
                    "Session ID must be a valid numeric booking ID: " + sessionId, e);
        }
    }

    private boolean isValidUUID(String str) {
        try {
            UUID.fromString(str);
            return true;
        } catch (Exception e) {
            return false;
        }
    }
}
