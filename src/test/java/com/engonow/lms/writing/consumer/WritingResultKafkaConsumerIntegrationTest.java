package com.engonow.lms.writing.consumer;

import com.engonow.lms.entity.InboxEvent;
import com.engonow.lms.repository.InboxEventRepository;
import com.engonow.lms.writing.domain.entity.WritingResult;
import com.engonow.lms.writing.domain.entity.WritingSubmission;
import com.engonow.lms.writing.domain.enums.SubmissionStatus;
import com.engonow.lms.writing.domain.enums.TaskType;
import com.engonow.lms.writing.domain.feedback.WritingFeedbackDetail;
import com.engonow.lms.writing.event.EventEnvelope;
import com.engonow.lms.writing.event.WritingEvaluationCompletedPayload;
import com.engonow.lms.writing.event.WritingEvaluationFailedPayload;
import com.engonow.lms.writing.repository.WritingResultRepository;
import com.engonow.lms.writing.repository.WritingSubmissionRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(properties = {
    "engonow.broker.type=KAFKA",
    "spring.flyway.clean-disabled=false"
})
@Testcontainers
class WritingResultKafkaConsumerIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:15-alpine")
        .withDatabaseName("engonow_lms")
        .withUsername("postgres")
        .withPassword("postgres");

    @Container
    static KafkaContainer kafka = new KafkaContainer(DockerImageName.parse("confluentinc/cp-kafka:7.6.0"));

    @DynamicPropertySource
    static void configureProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.kafka.bootstrap-servers", kafka::getBootstrapServers);
    }

    @Autowired
    private WritingSubmissionRepository submissionRepository;

    @Autowired
    private WritingResultRepository resultRepository;

    @Autowired
    private InboxEventRepository inboxEventRepository;

    @Autowired
    private ObjectMapper objectMapper;

    private KafkaTemplate<String, String> producerTemplate;

    @BeforeEach
    void setUp() {
        inboxEventRepository.deleteAllInBatch();
        resultRepository.deleteAllInBatch();
        submissionRepository.deleteAllInBatch();

        Map<String, Object> props = new HashMap<>();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, kafka.getBootstrapServers());
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);

        producerTemplate = new KafkaTemplate<>(new DefaultKafkaProducerFactory<>(props));
    }

    @AfterEach
    void tearDown() {
        if (producerTemplate != null) {
            producerTemplate.destroy();
        }
    }

    @Test
    @DisplayName("Test 1: Successful Result consumption, Cambridge rounding to 5.5, and Inbox record creation")
    void testSuccessfulResultConsumptionAndCambridgeScoring() throws Exception {
        // 1. Create a WritingSubmission in PENDING state
        WritingSubmission submission = new WritingSubmission();
        submission.setStudentId(UUID.randomUUID());
        submission.setTaskType(TaskType.TASK2);
        submission.setTaskPrompt("Some prompt");
        submission.setEssayText("Some student essay text.");
        submission.setWordCount(250);
        submission.setStatus(SubmissionStatus.PENDING);
        submission = submissionRepository.save(submission);

        UUID submissionId = submission.getId();
        UUID eventId = UUID.randomUUID();
        UUID idempotencyKey = UUID.randomUUID();

        // 2. Build completion event payload with (6.0, 5.0, 6.0, 5.0) -> Average 5.5
        WritingFeedbackDetail feedbackDetail = sampleFeedbackDetail("Good effort with balanced paragraph structure.");

        WritingEvaluationCompletedPayload payload = new WritingEvaluationCompletedPayload(
            submissionId,
            BigDecimal.valueOf(6.0),
            BigDecimal.valueOf(5.0),
            BigDecimal.valueOf(6.0),
            BigDecimal.valueOf(5.0),
            BigDecimal.valueOf(5.5),
            feedbackDetail
        );

        EventEnvelope<WritingEvaluationCompletedPayload> envelope = EventEnvelope.of(
            "WRITING_EVALUATION_COMPLETED",
            idempotencyKey,
            submissionId.toString(),
            "trace-123",
            "engonow-ai-writing-service",
            payload
        );

        String json = objectMapper.writeValueAsString(envelope);

        // 3. Produce to Kafka topic
        producerTemplate.send(new ProducerRecord<>("engonow.writing.evaluation-completed.v1", submissionId.toString(), json)).get();

        // 4. Await asynchronous processing by Kafka listener
        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            WritingSubmission updated = submissionRepository.findById(submissionId).orElseThrow();
            assertThat(updated.getStatus()).isEqualTo(SubmissionStatus.SCORED);

            Optional<WritingResult> optResult = resultRepository.findBySubmissionIdAndIsCurrentTrue(submissionId);
            assertThat(optResult).isPresent();
            WritingResult result = optResult.get();
            assertThat(result.getOverallBand()).isEqualByComparingTo(BigDecimal.valueOf(5.5));
            assertThat(result.getFeedbackDetail()).isNotNull();
            assertThat(result.getFeedbackDetail().examinerSummary()).isEqualTo("Good effort with balanced paragraph structure.");

            Optional<InboxEvent> inboxEvent = inboxEventRepository.findByIdempotencyKey(idempotencyKey);
            assertThat(inboxEvent).isPresent();
            assertThat(inboxEvent.get().getStatus()).isEqualTo("PROCESSED");
        });
    }

    @Test
    @DisplayName("Test 2: Duplicate result event is safely deduplicated via Inbox table")
    void testDuplicateResultEventIsDeduplicated() throws Exception {
        WritingSubmission submission = new WritingSubmission();
        submission.setStudentId(UUID.randomUUID());
        submission.setTaskType(TaskType.TASK2);
        submission.setTaskPrompt("Some prompt");
        submission.setEssayText("Some student essay text.");
        submission.setWordCount(250);
        submission.setStatus(SubmissionStatus.PENDING);
        submission = submissionRepository.save(submission);

        UUID submissionId = submission.getId();
        UUID idempotencyKey = UUID.randomUUID();

        WritingEvaluationCompletedPayload payload = new WritingEvaluationCompletedPayload(
            submissionId,
            BigDecimal.valueOf(7.0),
            BigDecimal.valueOf(7.0),
            BigDecimal.valueOf(7.0),
            BigDecimal.valueOf(7.0),
            BigDecimal.valueOf(7.0),
            sampleFeedbackDetail("Excellent")
        );

        EventEnvelope<WritingEvaluationCompletedPayload> envelope = EventEnvelope.of(
            "WRITING_EVALUATION_COMPLETED",
            idempotencyKey,
            submissionId.toString(),
            "trace-dup",
            "engonow-ai-writing-service",
            payload
        );

        String json = objectMapper.writeValueAsString(envelope);

        // Send 1st message
        producerTemplate.send(new ProducerRecord<>("engonow.writing.evaluation-completed.v1", submissionId.toString(), json)).get();

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            assertThat(resultRepository.findBySubmissionIdOrderByResultVersionDesc(submissionId)).hasSize(1);
        });

        // Send 2nd duplicate message with exact same idempotencyKey
        producerTemplate.send(new ProducerRecord<>("engonow.writing.evaluation-completed.v1", submissionId.toString(), json)).get();

        TimeUnit.MILLISECONDS.sleep(1500);

        // Verify only 1 result exists in database (deduplicated)
        List<WritingResult> allResults = resultRepository.findBySubmissionIdOrderByResultVersionDesc(submissionId);
        assertThat(allResults).hasSize(1);
    }

    @Test
    @DisplayName("Test 3: Failed event transitions submission to FAILED status")
    void testFailedEventTransitionsSubmissionToFailed() throws Exception {
        WritingSubmission submission = new WritingSubmission();
        submission.setStudentId(UUID.randomUUID());
        submission.setTaskType(TaskType.TASK2);
        submission.setTaskPrompt("Some prompt");
        submission.setEssayText("Some student essay text.");
        submission.setWordCount(250);
        submission.setStatus(SubmissionStatus.PENDING);
        submission = submissionRepository.save(submission);

        UUID submissionId = submission.getId();
        UUID idempotencyKey = UUID.randomUUID();

        WritingEvaluationFailedPayload payload = new WritingEvaluationFailedPayload(
            submissionId,
            "GEMINI_TIMEOUT",
            "Service unavailable",
            false,
            Instant.now()
        );

        EventEnvelope<WritingEvaluationFailedPayload> envelope = EventEnvelope.of(
            "WRITING_EVALUATION_FAILED",
            idempotencyKey,
            submissionId.toString(),
            "trace-fail",
            "engonow-ai-writing-service",
            payload
        );

        String json = objectMapper.writeValueAsString(envelope);

        producerTemplate.send(new ProducerRecord<>("engonow.writing.evaluation-failed.v1", submissionId.toString(), json)).get();

        await().atMost(10, TimeUnit.SECONDS).untilAsserted(() -> {
            WritingSubmission updated = submissionRepository.findById(submissionId).orElseThrow();
            assertThat(updated.getStatus()).isEqualTo(SubmissionStatus.FAILED);

            Optional<InboxEvent> inbox = inboxEventRepository.findByIdempotencyKey(idempotencyKey);
            assertThat(inbox).isPresent();
        });
    }

    private WritingFeedbackDetail sampleFeedbackDetail(String summary) {
        return new WritingFeedbackDetail(
            summary,
            new com.engonow.lms.writing.domain.feedback.EssayMetrics(250, 120, new BigDecimal("0.50"), new BigDecimal("15.0"), new BigDecimal("0.50")),
            List.of(),
            List.of(),
            new com.engonow.lms.writing.domain.feedback.CohesiveDeviceAnalysis(List.of(), List.of(), List.of()),
            List.of(),
            List.of()
        );
    }
}
