package com.engonow.lms.controller;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.when;

import com.engonow.lms.dto.SpeakingEvaluationEventPayload;
import com.engonow.lms.dto.SpeakingSubmissionRequestDTO;
import com.engonow.lms.dto.SpeakingSubmissionResponseDTO;
import com.engonow.lms.entity.MockTestBooking;
import com.engonow.lms.entity.OutboxEvent;
import com.engonow.lms.entity.SpeakingSessionResult;
import com.engonow.lms.entity.TutorAvailabilitySlot;
import com.engonow.lms.entity.User;
import com.engonow.lms.enums.BookingStatus;
import com.engonow.lms.enums.OutboxStatus;
import com.engonow.lms.enums.SlotStatus;
import com.engonow.lms.enums.SpeakingEvaluationStatus;
import com.engonow.lms.listener.SpeakingResultListener;
import com.engonow.lms.publisher.LocalMessagePublisher;
import com.engonow.lms.publisher.LocalMessagePublisher.LocalOutboxMessage;
import com.engonow.lms.repository.IdempotencyRepository;
import com.engonow.lms.repository.MockTestBookingRepository;
import com.engonow.lms.repository.OutboxEventRepository;
import com.engonow.lms.repository.SpeakingSessionResultRepository;
import com.engonow.lms.repository.TutorAvailabilitySlotRepository;
import com.engonow.lms.repository.UserRepository;
import com.engonow.lms.scheduler.OutboxRelayScheduler;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BooleanSupplier;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Answers;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.event.EventListener;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.TaskScheduler;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
            "app.seeding.enabled=false",
            "engonow.broker.type=LOCAL",
            "engonow.outbox.relay-delay-ms=100",
            "spring.datasource.url=${PIPELINE_IT_DB_URL:"
                    + "jdbc:mysql://localhost:3306/engonow_lms_pipeline_it"
                    + "?createDatabaseIfNotExist=true"
                    + "&useSSL=false"
                    + "&serverTimezone=UTC"
                    + "&allowPublicKeyRetrieval=true"
                    + "&characterEncoding=UTF-8"
                    + "&rewriteBatchedStatements=true}",
            "spring.jpa.hibernate.ddl-auto=create-drop",
            "spring.jpa.show-sql=false",
            "logging.level.org.hibernate.SQL=WARN"
        })
@Import(SpeakingPipelineIntegrationIT.LocalWorkerTestConfiguration.class)
class SpeakingPipelineIntegrationIT {

    private static final String SPEAKING_SUBMISSION_URL =
            "/api/v1/submissions/speaking";
    private static final int BURST_SIZE = 30;
    private static final int WORKER_CONCURRENCY = 5;
    private static final Duration HTTP_BURST_TIMEOUT = Duration.ofSeconds(10);
    private static final Duration PIPELINE_TIMEOUT = Duration.ofSeconds(30);
    private static final BigDecimal MIN_IELTS_BAND = BigDecimal.ONE;
    private static final BigDecimal MAX_IELTS_BAND = BigDecimal.valueOf(9);

    @Autowired
    private TestRestTemplate restTemplate;

    @Autowired
    private OutboxEventRepository outboxEventRepository;

    @Autowired
    private SpeakingSessionResultRepository speakingSessionResultRepository;

    @Autowired
    private OutboxRelayScheduler outboxRelayScheduler;

    @Autowired
    private SpeakingResultListener speakingResultListener;

    @Autowired
    private MockTestBookingRepository mockTestBookingRepository;

    @Autowired
    private TutorAvailabilitySlotRepository tutorAvailabilitySlotRepository;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private LocalSpeakingWorkerBridge localSpeakingWorkerBridge;

    /**
     * Replaces the scheduler clock only. The real relay bean remains available and
     * is invoked explicitly after the test has audited the PENDING rows.
     */
    @MockBean(name = "taskScheduler", answer = Answers.RETURNS_MOCKS)
    private TaskScheduler taskScheduler;

    /**
     * Keeps this LOCAL integration test independent of Redis while preserving the
     * same acquire/complete/release state transitions used by the real repository.
     */
    @MockBean
    private IdempotencyRepository idempotencyRepository;

    private final Map<String, String> idempotencyStates = new ConcurrentHashMap<>();
    private final List<Long> createdBookingIds = new ArrayList<>();
    private final List<Long> createdSlotIds = new ArrayList<>();
    private final List<Long> createdUserIds = new ArrayList<>();

    @BeforeEach
    void setUp() throws InterruptedException {
        assertTrue(
                localSpeakingWorkerBridge.awaitIdle(Duration.ofSeconds(5)),
                "The LOCAL worker must be idle before test setup");

        outboxEventRepository.deleteAllInBatch();
        speakingSessionResultRepository.deleteAllInBatch();
        localSpeakingWorkerBridge.reset();
        configureInMemoryIdempotencyGuard();

        assertNotNull(
                speakingResultListener,
                "The production SpeakingResultListener must be present");
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        assertTrue(
                localSpeakingWorkerBridge.awaitIdle(Duration.ofSeconds(5)),
                "The LOCAL worker must drain before database teardown");

        speakingSessionResultRepository.deleteAllInBatch();
        outboxEventRepository.deleteAllInBatch();

        if (!createdBookingIds.isEmpty()) {
            mockTestBookingRepository.deleteAllByIdInBatch(createdBookingIds);
        }
        if (!createdSlotIds.isEmpty()) {
            tutorAvailabilitySlotRepository.deleteAllByIdInBatch(createdSlotIds);
        }
        if (!createdUserIds.isEmpty()) {
            userRepository.deleteAllByIdInBatch(createdUserIds);
        }

        createdBookingIds.clear();
        createdSlotIds.clear();
        createdUserIds.clear();
        idempotencyStates.clear();
        localSpeakingWorkerBridge.reset();
    }

    @Test
    void testEndToEndPipeline_ConcurrentSubmissionBurst_ProcessesAllRequestsWithoutLoss()
            throws InterruptedException {
        List<String> sessionIds = createSpeakingSessions(BURST_SIZE);
        List<String> generatedSessionIds =
                Collections.synchronizedList(new ArrayList<>());
        ConcurrentLinkedQueue<String> intakeFailures =
                new ConcurrentLinkedQueue<>();
        AtomicInteger http202Count = new AtomicInteger();
        CountDownLatch readyLatch = new CountDownLatch(BURST_SIZE);
        CountDownLatch startLatch = new CountDownLatch(1);
        CountDownLatch doneLatch = new CountDownLatch(BURST_SIZE);
        ExecutorService executor = Executors.newFixedThreadPool(BURST_SIZE);

        try {
            for (String sessionId : sessionIds) {
                executor.submit(() -> {
                    SpeakingSubmissionRequestDTO request =
                            createSubmissionRequest(
                                    sessionId,
                                    "memory://valid-audio/" + sessionId + ".wav");
                    generatedSessionIds.add(sessionId);
                    readyLatch.countDown();

                    try {
                        startLatch.await();
                        ResponseEntity<SpeakingSubmissionResponseDTO> response =
                                restTemplate.postForEntity(
                                        SPEAKING_SUBMISSION_URL,
                                        request,
                                        SpeakingSubmissionResponseDTO.class);

                        if (response.getStatusCode() == HttpStatus.ACCEPTED) {
                            http202Count.incrementAndGet();
                        } else {
                            intakeFailures.add(
                                    sessionId + " returned HTTP "
                                            + response.getStatusCode().value());
                        }
                    } catch (InterruptedException exception) {
                        Thread.currentThread().interrupt();
                        intakeFailures.add(sessionId + " was interrupted");
                    } catch (Exception exception) {
                        intakeFailures.add(
                                sessionId + " failed: " + exception.getMessage());
                    } finally {
                        doneLatch.countDown();
                    }
                });
            }

            assertTrue(
                    readyLatch.await(
                            HTTP_BURST_TIMEOUT.toMillis(),
                            TimeUnit.MILLISECONDS),
                    "All HTTP request threads must reach the common starting line");

            long burstStartedAt = System.nanoTime();
            startLatch.countDown();

            assertTrue(
                    doneLatch.await(
                            HTTP_BURST_TIMEOUT.toMillis(),
                            TimeUnit.MILLISECONDS),
                    "All concurrent submissions must return within 10 seconds");
            Duration burstDuration =
                    Duration.ofNanos(System.nanoTime() - burstStartedAt);

            assertEquals(
                    BURST_SIZE,
                    http202Count.get(),
                    "100% of concurrent submissions must return HTTP 202");
            assertTrue(
                    intakeFailures.isEmpty(),
                    () -> "Unexpected intake failures: " + intakeFailures);
            assertTrue(
                    burstDuration.compareTo(HTTP_BURST_TIMEOUT) < 0,
                    () -> "The HTTP burst took too long: " + burstDuration);
        } finally {
            startLatch.countDown();
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }

        assertEquals(
                Set.copyOf(sessionIds),
                Set.copyOf(generatedSessionIds),
                "Every prepared session must participate in the synchronized burst");

        List<OutboxEvent> pendingEvents = outboxEventRepository.findAll();
        assertEquals(
                BURST_SIZE,
                pendingEvents.size(),
                "Every accepted submission must atomically create one outbox event");
        assertTrue(
                pendingEvents.stream()
                        .allMatch(event -> event.getStatus() == OutboxStatus.PENDING),
                "Every outbox event must remain PENDING before relay execution");
        assertEquals(
                BURST_SIZE,
                speakingSessionResultRepository.count(),
                "Every accepted submission must atomically create one pending result row");

        outboxRelayScheduler.processPendingOutboxEvents();

        awaitCondition(
                "All speaking result events must be persisted",
                PIPELINE_TIMEOUT,
                () -> allSessionsTerminal(sessionIds));

        List<OutboxEvent> relayedEvents = outboxEventRepository.findAll();
        assertEquals(BURST_SIZE, relayedEvents.size());
        assertTrue(
                relayedEvents.stream()
                        .allMatch(event -> event.getStatus() == OutboxStatus.SENT),
                "Every outbox event must transition to SENT");
        assertTrue(
                relayedEvents.stream().allMatch(event -> event.getRetryCount() == 0),
                "The deterministic LOCAL pipeline must not consume relay retries");
        assertTrue(
                localSpeakingWorkerBridge.failures().isEmpty(),
                () -> "LOCAL worker failures: "
                        + localSpeakingWorkerBridge.failures());
        assertTrue(
                localSpeakingWorkerBridge.maxObservedConcurrency()
                        <= WORKER_CONCURRENCY,
                "The worker must enforce its configured concurrency ceiling");

        for (String sessionId : sessionIds) {
            SpeakingSessionResult result = speakingSessionResultRepository
                    .findBySessionId(sessionId)
                    .orElseThrow(() -> new AssertionError(
                            "Missing speaking result for session " + sessionId));

            assertTrue(
                    Boolean.TRUE.equals(result.getIsComplete()),
                    "Speaking result must be complete for session " + sessionId);
            assertTrue(
                    result.getEvaluationStatus() == SpeakingEvaluationStatus.SUCCESS
                            || result.getEvaluationStatus()
                            == SpeakingEvaluationStatus
                                    .PARTIAL_SUCCESS_LOW_AUDIO_CONF,
                    "Unexpected evaluation status for session " + sessionId);
            assertValidBand(result.getPronunciationScore(), "pronunciation", sessionId);
            assertValidBand(result.getFluencyScore(), "fluency", sessionId);
            assertValidBand(result.getGrammarScore(), "grammar", sessionId);
            assertValidBand(result.getLexicalScore(), "lexical", sessionId);
            assertValidBand(result.getAiScore(), "AI", sessionId);
            assertValidBand(result.getOverallBand(), "overall", sessionId);

            BigDecimal emittedCoverage =
                    localSpeakingWorkerBridge.genuineWordCoverage(sessionId);
            assertNotNull(
                    emittedCoverage,
                    "The standardized worker result must contain genuine_word_coverage");
            assertTrue(
                    emittedCoverage.compareTo(BigDecimal.ZERO) >= 0,
                    "genuine_word_coverage must not be negative");
        }
    }

    @Test
    void testPipeline_WhenPythonWorkerReturnsError_PersistsFailureGracefully()
            throws InterruptedException {
        String sessionId = createSpeakingSessions(1).get(0);
        SpeakingSubmissionRequestDTO request =
                createSubmissionRequest(
                        sessionId,
                        "invalid://missing-audio/" + sessionId + ".wav");

        ResponseEntity<SpeakingSubmissionResponseDTO> response =
                restTemplate.postForEntity(
                        SPEAKING_SUBMISSION_URL,
                        request,
                        SpeakingSubmissionResponseDTO.class);

        assertEquals(
                HttpStatus.ACCEPTED,
                response.getStatusCode(),
                "Invalid media must still be accepted into the asynchronous pipeline");
        assertEquals(1, outboxEventRepository.count());
        assertEquals(
                OutboxStatus.PENDING,
                outboxEventRepository.findAll().get(0).getStatus());

        outboxRelayScheduler.processPendingOutboxEvents();

        awaitCondition(
                "The worker error result must be persisted",
                PIPELINE_TIMEOUT,
                () -> speakingSessionResultRepository
                        .findBySessionId(sessionId)
                        .map(result ->
                                result.getEvaluationStatus()
                                        == SpeakingEvaluationStatus.SYSTEM_ERROR)
                        .orElse(false));

        OutboxEvent outboxEvent = outboxEventRepository.findAll().get(0);
        assertEquals(
                OutboxStatus.SENT,
                outboxEvent.getStatus(),
                "A handled AI failure is still a successfully delivered event");
        assertEquals(0, outboxEvent.getRetryCount());

        SpeakingSessionResult result = speakingSessionResultRepository
                .findBySessionId(sessionId)
                .orElseThrow(() -> new AssertionError(
                        "Missing failure result for session " + sessionId));
        assertEquals(
                SpeakingEvaluationStatus.SYSTEM_ERROR,
                result.getEvaluationStatus());
        assertTrue(Boolean.TRUE.equals(result.getIsComplete()));
        assertNotNull(result.getFeedbackText());
        assertFalse(result.getFeedbackText().isBlank());
        assertTrue(
                result.getFeedbackText().contains("Invalid audio reference"),
                "Failure feedback must retain the worker's diagnostic detail");
        assertTrue(
                localSpeakingWorkerBridge.failures().isEmpty(),
                () -> "LOCAL worker failures: "
                        + localSpeakingWorkerBridge.failures());
    }

    private void configureInMemoryIdempotencyGuard() {
        reset(idempotencyRepository);
        idempotencyStates.clear();

        when(idempotencyRepository.tryLock(anyString(), anyLong()))
                .thenAnswer(invocation -> {
                    String key = invocation.getArgument(0);
                    return idempotencyStates.putIfAbsent(key, "PROCESSING") == null;
                });
        doAnswer(invocation -> {
            String key = invocation.getArgument(0);
            idempotencyStates.computeIfPresent(
                    key,
                    (ignored, state) -> "COMPLETED");
            return null;
        }).when(idempotencyRepository).completeLock(anyString(), anyLong());
        doAnswer(invocation -> {
            idempotencyStates.remove(invocation.getArgument(0, String.class));
            return null;
        }).when(idempotencyRepository).releaseLock(anyString());
    }

    private List<String> createSpeakingSessions(int count) {
        String testRunId = UUID.randomUUID().toString();
        User student = userRepository.save(User.builder()
                .username("pipeline_student_" + testRunId)
                .email("pipeline_student_" + testRunId + "@example.test")
                .password("integration-test-password-hash")
                .fullName("Pipeline Integration Student")
                .isActive(true)
                .build());
        User tutor = userRepository.save(User.builder()
                .username("pipeline_tutor_" + testRunId)
                .email("pipeline_tutor_" + testRunId + "@example.test")
                .password("integration-test-password-hash")
                .fullName("Pipeline Integration Tutor")
                .isActive(true)
                .build());
        createdUserIds.add(student.getId());
        createdUserIds.add(tutor.getId());

        List<String> sessionIds = new ArrayList<>(count);
        for (int index = 0; index < count; index++) {
            TutorAvailabilitySlot slot =
                    tutorAvailabilitySlotRepository.save(
                            TutorAvailabilitySlot.builder()
                                    .tutor(tutor)
                                    .slotDate(LocalDate.now().plusDays(index + 1L))
                                    .startTime(LocalTime.of(9, 0))
                                    .endTime(LocalTime.of(10, 0))
                                    .slotStatus(SlotStatus.BOOKED)
                                    .build());
            createdSlotIds.add(slot.getId());

            MockTestBooking booking =
                    mockTestBookingRepository.save(
                            MockTestBooking.builder()
                                    .student(student)
                                    .slot(slot)
                                    .bookingStatus(BookingStatus.CONFIRMED)
                                    .notes("Phase 3 asynchronous pipeline integration test")
                                    .build());
            createdBookingIds.add(booking.getId());
            sessionIds.add(booking.getId().toString());
        }
        return sessionIds;
    }

    private SpeakingSubmissionRequestDTO createSubmissionRequest(
            String sessionId,
            String audioUrl) {
        ObjectNode questionsMetadata = objectMapper.createObjectNode();
        questionsMetadata.put("test_type", "IELTS_SPEAKING");
        questionsMetadata.put("part", 2);
        questionsMetadata.put(
                "prompt",
                "Describe a useful skill you learned recently.");
        return new SpeakingSubmissionRequestDTO(
                sessionId,
                questionsMetadata,
                audioUrl);
    }

    private boolean allSessionsTerminal(List<String> sessionIds) {
        Map<String, SpeakingSessionResult> resultsBySession =
                speakingSessionResultRepository.findAll().stream()
                        .collect(java.util.stream.Collectors.toMap(
                                SpeakingSessionResult::getSessionId,
                                result -> result));
        return sessionIds.stream().allMatch(sessionId -> {
            SpeakingSessionResult result = resultsBySession.get(sessionId);
            return result != null
                    && result.getEvaluationStatus()
                    != SpeakingEvaluationStatus.PENDING;
        });
    }

    private void awaitCondition(
            String failureMessage,
            Duration timeout,
            BooleanSupplier condition) throws InterruptedException {
        long deadline = System.nanoTime() + timeout.toNanos();
        while (System.nanoTime() < deadline) {
            if (condition.getAsBoolean()) {
                return;
            }
            Thread.sleep(25);
        }
        assertTrue(
                condition.getAsBoolean(),
                () -> failureMessage + "; worker failures="
                        + localSpeakingWorkerBridge.failures());
    }

    private void assertValidBand(
            BigDecimal score,
            String criterion,
            String sessionId) {
        assertNotNull(
                score,
                criterion + " score must exist for session " + sessionId);
        assertTrue(
                score.compareTo(MIN_IELTS_BAND) >= 0,
                criterion + " score must be at least 1.0 for session " + sessionId);
        assertTrue(
                score.compareTo(MAX_IELTS_BAND) <= 0,
                criterion + " score must not exceed 9.0 for session " + sessionId);
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class LocalWorkerTestConfiguration {

        @Bean(destroyMethod = "close")
        LocalSpeakingWorkerBridge localSpeakingWorkerBridge(
                ObjectMapper objectMapper,
                LocalMessagePublisher localMessagePublisher) {
            return new LocalSpeakingWorkerBridge(
                    objectMapper,
                    localMessagePublisher,
                    WORKER_CONCURRENCY);
        }
    }

    /**
     * Deterministic test double for the Python LOCAL worker boundary. Everything
     * before and after this boundary remains production Spring code.
     */
    static final class LocalSpeakingWorkerBridge implements AutoCloseable {

        private final ObjectMapper objectMapper;
        private final LocalMessagePublisher localMessagePublisher;
        private final ExecutorService workerExecutor;
        private final AtomicInteger pendingJobs = new AtomicInteger();
        private final AtomicInteger activeJobs = new AtomicInteger();
        private final AtomicInteger maxObservedConcurrency = new AtomicInteger();
        private final Map<String, BigDecimal> coverageBySession =
                new ConcurrentHashMap<>();
        private final ConcurrentLinkedQueue<String> failures =
                new ConcurrentLinkedQueue<>();

        LocalSpeakingWorkerBridge(
                ObjectMapper objectMapper,
                LocalMessagePublisher localMessagePublisher,
                int concurrency) {
            this.objectMapper = objectMapper;
            this.localMessagePublisher = localMessagePublisher;
            AtomicInteger threadSequence = new AtomicInteger();
            this.workerExecutor = Executors.newFixedThreadPool(
                    concurrency,
                    runnable -> {
                        Thread thread = new Thread(
                                runnable,
                                "local-speaking-worker-"
                                        + threadSequence.incrementAndGet());
                        thread.setDaemon(true);
                        return thread;
                    });
        }

        @EventListener
        public void onEvaluationRequested(LocalOutboxMessage event) {
            if (!"SPEAKING_EVALUATION_REQUESTED".equals(event.eventType())) {
                return;
            }

            pendingJobs.incrementAndGet();
            workerExecutor.execute(() -> process(event));
        }

        private void process(LocalOutboxMessage event) {
            int active = activeJobs.incrementAndGet();
            maxObservedConcurrency.accumulateAndGet(active, Math::max);

            try {
                SpeakingEvaluationEventPayload request =
                        objectMapper.readValue(
                                event.payload(),
                                SpeakingEvaluationEventPayload.class);
                ObjectNode result = request.audioUrl().startsWith("invalid:")
                        ? systemErrorResult(request)
                        : successfulResult(request);
                BigDecimal coverage = result
                        .path("genuine_word_coverage")
                        .decimalValue();
                coverageBySession.put(request.sessionId(), coverage);
                localMessagePublisher.publishResult(
                        objectMapper.writeValueAsString(result));
            } catch (Exception exception) {
                failures.add(
                        event.aggregateId() + ": "
                                + exception.getClass().getSimpleName() + ": "
                                + exception.getMessage());
            } finally {
                activeJobs.decrementAndGet();
                pendingJobs.decrementAndGet();
            }
        }

        private ObjectNode successfulResult(
                SpeakingEvaluationEventPayload request) {
            ObjectNode result = baseResult(request.sessionId());
            result.put("pronunciation_score", 7.5);
            result.put("fluency_score", 7.0);
            result.put("grammar_score", 6.5);
            result.put("lexical_score", 7.5);
            result.put("status", "SUCCESS");
            result.put("genuine_word_coverage", 0.93);
            result.put(
                    "feedback_text",
                    "Clear, coherent response with relevant supporting detail.");
            result.put("processing_time_ms", 5.0);
            result.putObject("provider_metadata")
                    .put("strategy", "DETERMINISTIC_LOCAL_TEST_PROVIDER");
            return result;
        }

        private ObjectNode systemErrorResult(
                SpeakingEvaluationEventPayload request) {
            ObjectNode result = baseResult(request.sessionId());
            result.put("pronunciation_score", 1.0);
            result.put("fluency_score", 1.0);
            result.put("grammar_score", 1.0);
            result.put("lexical_score", 1.0);
            result.put("status", "SYSTEM_ERROR");
            result.put("genuine_word_coverage", 0.0);
            result.put(
                    "feedback_text",
                    "Invalid audio reference: " + request.audioUrl());
            result.put("processing_time_ms", 1.0);
            result.putObject("provider_metadata")
                    .put("error_code", "INVALID_AUDIO_REFERENCE");
            return result;
        }

        private ObjectNode baseResult(String sessionId) {
            ObjectNode result = objectMapper.createObjectNode();
            result.put("session_id", sessionId);
            result.put("provider_used", "LOCAL_TEST_PROVIDER");
            return result;
        }

        BigDecimal genuineWordCoverage(String sessionId) {
            return coverageBySession.get(sessionId);
        }

        int maxObservedConcurrency() {
            return maxObservedConcurrency.get();
        }

        List<String> failures() {
            return List.copyOf(failures);
        }

        boolean awaitIdle(Duration timeout) throws InterruptedException {
            long deadline = System.nanoTime() + timeout.toNanos();
            while (System.nanoTime() < deadline) {
                if (pendingJobs.get() == 0 && activeJobs.get() == 0) {
                    return true;
                }
                Thread.sleep(10);
            }
            return pendingJobs.get() == 0 && activeJobs.get() == 0;
        }

        void reset() {
            if (pendingJobs.get() != 0 || activeJobs.get() != 0) {
                throw new IllegalStateException(
                        "Cannot reset the LOCAL worker while jobs are active");
            }
            coverageBySession.clear();
            failures.clear();
            maxObservedConcurrency.set(0);
        }

        @Override
        public void close() throws InterruptedException {
            workerExecutor.shutdown();
            if (!workerExecutor.awaitTermination(5, TimeUnit.SECONDS)) {
                workerExecutor.shutdownNow();
            }
        }
    }
}
