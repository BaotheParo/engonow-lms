package com.engonow.lms.admin;

import com.engonow.lms.admin.dto.DlqReplayRequestDTO;
import com.engonow.lms.repository.InboxEventRepository;
import com.engonow.lms.writing.domain.entity.WritingResult;
import com.engonow.lms.writing.domain.entity.WritingSubmission;
import com.engonow.lms.writing.domain.enums.SubmissionStatus;
import com.engonow.lms.writing.domain.enums.TaskType;
import com.engonow.lms.writing.domain.feedback.CohesiveDeviceAnalysis;
import com.engonow.lms.writing.domain.feedback.EssayMetrics;
import com.engonow.lms.writing.domain.feedback.WritingFeedbackDetail;
import com.engonow.lms.writing.event.EventEnvelope;
import com.engonow.lms.writing.event.WritingEvaluationCompletedPayload;
import com.engonow.lms.writing.repository.WritingResultRepository;
import com.engonow.lms.writing.repository.WritingSubmissionRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "engonow.broker.type=KAFKA",
    "spring.flyway.clean-disabled=false"
})
@AutoConfigureMockMvc
@Testcontainers
class KafkaDlqAdminIntegrationTest {

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
    private MockMvc mockMvc;

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
    @DisplayName("Test 1: Poison pill message on completed topic is forwarded to DLQ by Spring Error Handler")
    void testPoisonPillResultSentToDlqBySpringErrorHandler() throws Exception {
        String poisonPillValue = "INVALID_UNPARSEABLE_JSON_MESSAGE_{{";
        String poisonPillKey = UUID.randomUUID().toString();

        // Produce directly to primary topic
        producerTemplate.send(new ProducerRecord<>("engonow.writing.evaluation-completed.v1", poisonPillKey, poisonPillValue)).get();

        // Create a test consumer to assert arrival on the DLQ topic
        Map<String, Object> consumerProps = new HashMap<>();
        consumerProps.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, kafka.getBootstrapServers());
        consumerProps.put(ConsumerConfig.GROUP_ID_CONFIG, "test-dlq-verifier-" + UUID.randomUUID());
        consumerProps.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
        consumerProps.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
        consumerProps.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

        try (Consumer<String, String> testConsumer = new DefaultKafkaConsumerFactory<String, String>(consumerProps).createConsumer()) {
            testConsumer.subscribe(Collections.singletonList("engonow.writing.evaluation-completed.v1.dlq"));

            await().atMost(15, TimeUnit.SECONDS).untilAsserted(() -> {
                ConsumerRecords<String, String> records = testConsumer.poll(Duration.ofMillis(1000));
                assertThat(records.isEmpty()).isFalse();
                assertThat(records.iterator().next().value()).isEqualTo(poisonPillValue);
            });
        }
    }

    @Test
    @DisplayName("Test 2: Admin REST endpoint POST /api/v1/admin/kafka/dlq/replay replays message from DLQ to target topic")
    void testAdminReplayRestEndpointSuccessfullyReplaysMessage() throws Exception {
        // 1. Create a submission in PENDING state
        WritingSubmission submission = new WritingSubmission();
        submission.setStudentId(UUID.randomUUID());
        submission.setTaskType(TaskType.TASK2);
        submission.setTaskPrompt("Some prompt");
        submission.setEssayText("Student essay content.");
        submission.setWordCount(200);
        submission.setStatus(SubmissionStatus.PENDING);
        submission = submissionRepository.save(submission);

        UUID submissionId = submission.getId();
        UUID idempotencyKey = UUID.randomUUID();

        WritingFeedbackDetail feedbackDetail = new WritingFeedbackDetail(
            "Replayed evaluation feedback",
            new EssayMetrics(200, 100, new BigDecimal("0.50"), new BigDecimal("14.0"), new BigDecimal("0.50")),
            List.of(),
            List.of(),
            new CohesiveDeviceAnalysis(List.of(), List.of(), List.of()),
            List.of(),
            List.of()
        );

        WritingEvaluationCompletedPayload payload = new WritingEvaluationCompletedPayload(
            submissionId,
            BigDecimal.valueOf(6.5),
            BigDecimal.valueOf(6.5),
            BigDecimal.valueOf(6.5),
            BigDecimal.valueOf(6.5),
            BigDecimal.valueOf(6.5),
            feedbackDetail
        );

        EventEnvelope<WritingEvaluationCompletedPayload> envelope = EventEnvelope.of(
            "WRITING_EVALUATION_COMPLETED",
            idempotencyKey,
            submissionId.toString(),
            "trace-replay",
            "engonow-ai-writing-service",
            payload
        );

        String validJson = objectMapper.writeValueAsString(envelope);

        // 2. Publish message directly to DLQ topic
        producerTemplate.send(new ProducerRecord<>("engonow.writing.evaluation-completed.v1.dlq", submissionId.toString(), validJson)).get();

        // 3. Invoke Admin Replay REST endpoint
        DlqReplayRequestDTO replayRequest = new DlqReplayRequestDTO(
            "engonow.writing.evaluation-completed.v1.dlq",
            "engonow.writing.evaluation-completed.v1",
            10,
            submissionId.toString()
        );

        mockMvc.perform(post("/api/v1/admin/kafka/dlq/replay")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(replayRequest)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.messagesRead").value(1))
            .andExpect(jsonPath("$.messagesReplayed").value(1));

        // 4. Assert that the replayed event is picked up by listener and processed
        await().atMost(15, TimeUnit.SECONDS).untilAsserted(() -> {
            WritingSubmission updated = submissionRepository.findById(submissionId).orElseThrow();
            assertThat(updated.getStatus()).isEqualTo(SubmissionStatus.SCORED);

            Optional<WritingResult> result = resultRepository.findBySubmissionIdAndIsCurrentTrue(submissionId);
            assertThat(result).isPresent();
            assertThat(result.get().getOverallBand()).isEqualByComparingTo(BigDecimal.valueOf(6.5));
        });
    }
}
