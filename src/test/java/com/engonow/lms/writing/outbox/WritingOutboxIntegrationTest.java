package com.engonow.lms.writing.outbox;

import com.engonow.lms.entity.OutboxEvent;
import com.engonow.lms.enums.OutboxStatus;
import com.engonow.lms.repository.OutboxEventRepository;
import com.engonow.lms.writing.domain.entity.WritingSubmission;
import com.engonow.lms.writing.domain.enums.SubmissionStatus;
import com.engonow.lms.writing.dto.WritingSubmissionRequestDTO;
import com.engonow.lms.writing.repository.WritingSubmissionRepository;
import com.engonow.lms.writing.service.WritingSubmissionService;
import com.engonow.lms.scheduler.OutboxRelayScheduler;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import java.time.Duration;
import java.util.Collections;
import java.util.List;
import java.util.Properties;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(properties = {
    "engonow.broker.type=KAFKA",
    "spring.flyway.clean-disabled=false"
})
@Testcontainers
class WritingOutboxIntegrationTest {

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
    private WritingSubmissionService submissionService;

    @Autowired
    private WritingSubmissionRepository submissionRepository;

    @Autowired
    private OutboxEventRepository outboxEventRepository;

    @Autowired
    private OutboxRelayScheduler outboxRelayScheduler;

    @Autowired
    private TransactionTemplate transactionTemplate;

    private KafkaConsumer<String, String> consumer;

    @BeforeEach
    void setUp() {
        outboxEventRepository.deleteAllInBatch();
        submissionRepository.deleteAllInBatch();

        Properties props = new Properties();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, kafka.getBootstrapServers());
        props.put(ConsumerConfig.GROUP_ID_CONFIG, "test-group-" + UUID.randomUUID());
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

        consumer = new KafkaConsumer<>(props);
        consumer.subscribe(Collections.singletonList("engonow.writing.evaluation-requested.v1"));
    }

    @AfterEach
    void tearDown() {
        if (consumer != null) {
            consumer.close();
        }
    }

    @Test
    @DisplayName("Test 1: Transaction failure rolls back both submission and outbox row")
    void testOutboxRollbackOnTransactionFailure() {
        WritingSubmissionRequestDTO request = new WritingSubmissionRequestDTO(
            UUID.randomUUID(),
            com.engonow.lms.writing.domain.enums.TaskType.TASK2,
            "Discuss the pros and cons of remote work.",
            "Remote work has become increasingly common..."
        );

        assertThrows(RuntimeException.class, () -> {
            transactionTemplate.execute(status -> {
                submissionService.submitEssay(request);
                throw new RuntimeException("Simulated transaction rollback");
            });
        });

        // Ensure database state was completely rolled back
        List<WritingSubmission> submissions = submissionRepository.findAll();
        List<OutboxEvent> outboxEvents = outboxEventRepository.findAll();

        assertThat(submissions).isEmpty();
        assertThat(outboxEvents).isEmpty();
    }

    @Test
    @DisplayName("Test 2: Successful submission eagerly dispatches message and marks outbox PUBLISHED")
    void testEagerDispatchSuccess() throws Exception {
        WritingSubmissionRequestDTO request = new WritingSubmissionRequestDTO(
            UUID.randomUUID(),
            com.engonow.lms.writing.domain.enums.TaskType.TASK2,
            "Discuss the pros and cons of remote work.",
            "Remote work has become increasingly common..."
        );

        // Submit outside explicit transaction (submitEssay manages its own transaction and eagerness)
        var response = submissionService.submitEssay(request);

        // Verify database state contains PENDING or PUBLISHED (depending on eager speed)
        // Wait a brief moment for async Kafka callback to trigger and update status
        TimeUnit.MILLISECONDS.sleep(1200);

        List<OutboxEvent> outboxEvents = outboxEventRepository.findAll();
        assertThat(outboxEvents).hasSize(1);
        assertThat(outboxEvents.get(0).getStatus()).isEqualTo(OutboxStatus.PUBLISHED);

        // Verify event was successfully written to Kafka topic
        ConsumerRecords<String, String> records = consumer.poll(Duration.ofSeconds(5));
        assertThat(records.count()).isEqualTo(1);
        ConsumerRecord<String, String> record = records.iterator().next();
        assertThat(record.key()).isEqualTo(response.id().toString());
        assertThat(record.value()).contains("Remote work has become increasingly common");
    }

    @Test
    @DisplayName("Test 3: Reconciliation scheduler sweeps and dispatches PENDING outbox events")
    void testReconciliationSchedulerRecoversOrphans() throws Exception {
        UUID submissionId = UUID.randomUUID();
        // Insert a PENDING outbox event manually to simulate an eager dispatch failure/missing state
        OutboxEvent orphan = OutboxEvent.builder()
            .aggregateType("WRITING_SUBMISSION")
            .aggregateId(submissionId.toString())
            .eventType("WRITING_EVALUATION_REQUESTED")
            .schemaVersion("1.0")
            .traceId(UUID.randomUUID().toString())
            .correlationId(submissionId.toString())
            .payload("{\"submissionId\":\"" + submissionId + "\", \"essayText\":\"Orphan recovery essay content\"}")
            .status(OutboxStatus.PENDING)
            .build();

        transactionTemplate.execute(status -> {
            outboxEventRepository.save(orphan);
            return null;
        });

        // Trigger the outbox sweep manually
        outboxRelayScheduler.processPendingOutboxEvents();

        // Verify database status was updated to PUBLISHED
        OutboxEvent updated = outboxEventRepository.findById(orphan.getId()).orElseThrow();
        assertThat(updated.getStatus()).isEqualTo(OutboxStatus.PUBLISHED);

        // Verify Kafka consumer picked it up
        ConsumerRecords<String, String> records = consumer.poll(Duration.ofSeconds(5));
        assertThat(records.count()).isEqualTo(1);
        ConsumerRecord<String, String> record = records.iterator().next();
        assertThat(record.value()).contains("Orphan recovery essay content");
    }
}
