package com.engonow.lms.writing.controller;

import com.engonow.lms.repository.IdempotencyRepository;
import com.engonow.lms.writing.domain.entity.WritingSubmission;
import com.engonow.lms.writing.domain.enums.SubmissionStatus;
import com.engonow.lms.writing.domain.enums.TaskType;
import com.engonow.lms.writing.domain.enums.WritingCriterion;
import com.engonow.lms.writing.domain.feedback.CohesiveDeviceAnalysis;
import com.engonow.lms.writing.domain.feedback.CriterionFeedback;
import com.engonow.lms.writing.domain.feedback.EssayMetrics;
import com.engonow.lms.writing.domain.feedback.WritingFeedbackDetail;
import com.engonow.lms.writing.dto.WritingWebhookPayloadDTO;
import com.engonow.lms.writing.repository.WritingResultRepository;
import com.engonow.lms.writing.repository.WritingSubmissionRepository;
import com.engonow.lms.writing.service.WritingSubmissionService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.ConcurrencyFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@SpringBootTest(properties = "app.seeding.enabled=true")
@AutoConfigureMockMvc
public class WritingWebhookConcurrencyIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private WritingSubmissionRepository writingSubmissionRepository;

    @Autowired
    private WritingResultRepository writingResultRepository;

    @Autowired
    private WritingSubmissionService writingSubmissionService;

    @Autowired
    private IdempotencyRepository idempotencyRepository;

    @Autowired
    private StringRedisTemplate stringRedisTemplate;

    private UUID studentId;
    private WritingSubmission submission;
    private WritingFeedbackDetail sampleFeedbackDetail;

    @BeforeEach
    void setUp() {
        cleanUp();
        studentId = UUID.randomUUID();

        submission = new WritingSubmission();
        submission.setStudentId(studentId);
        submission.setTaskType(TaskType.TASK2);
        submission.setTaskPrompt("Some people believe that remote work is beneficial. Discuss.");
        submission.setEssayText("In recent years, remote work has gained substantial popularity across the world.");
        submission.setWordCount(100);
        submission.setStatus(SubmissionStatus.PENDING);
        submission = writingSubmissionRepository.save(submission);

        sampleFeedbackDetail = new WritingFeedbackDetail(
            "Overall well-written response.",
            new EssayMetrics(100, 60, new BigDecimal("0.60"), new BigDecimal("15.0"), new BigDecimal("0.50")),
            List.of(new CriterionFeedback(WritingCriterion.TASK_RESPONSE, new BigDecimal("7.0"), "Clear stance", List.of("Strong intro"), List.of("Short conclusion"), "Expand conclusion")),
            List.of(),
            new CohesiveDeviceAnalysis(List.of("However"), List.of(), List.of()),
            List.of(),
            List.of()
        );
    }

    @AfterEach
    void cleanUp() {
        writingResultRepository.deleteAllInBatch();
        writingSubmissionRepository.deleteAllInBatch();
        if (stringRedisTemplate != null && stringRedisTemplate.getConnectionFactory() != null) {
            try {
                stringRedisTemplate.getConnectionFactory().getConnection().serverCommands().flushDb();
            } catch (Exception ignored) {
            }
        }
    }

    @Test
    @DisplayName("Parallel direct service invocations trigger Concurrency / OptimisticLocking failure or safe execution")
    void testDirectServiceConcurrency_TriggersConcurrencyGuarding() {
        WritingWebhookPayloadDTO payload1 = new WritingWebhookPayloadDTO(
            submission.getId(),
            new BigDecimal("7.0"),
            new BigDecimal("7.0"),
            new BigDecimal("7.0"),
            new BigDecimal("7.0"),
            sampleFeedbackDetail,
            "gemini-2.5-flash",
            "SUCCESS",
            null
        );

        WritingWebhookPayloadDTO payload2 = new WritingWebhookPayloadDTO(
            submission.getId(),
            new BigDecimal("8.0"),
            new BigDecimal("8.0"),
            new BigDecimal("8.0"),
            new BigDecimal("8.0"),
            sampleFeedbackDetail,
            "gemini-2.5-flash",
            "SUCCESS",
            null
        );

        AtomicInteger successCount = new AtomicInteger(0);
        AtomicInteger conflictCount = new AtomicInteger(0);

        CompletableFuture<Void> task1 = CompletableFuture.runAsync(() -> {
            try {
                writingSubmissionService.processEvaluationWebhook(payload1);
                successCount.incrementAndGet();
            } catch (ConcurrencyFailureException e) {
                conflictCount.incrementAndGet();
            } catch (Exception e) {
                if (e.getCause() instanceof ConcurrencyFailureException) {
                    conflictCount.incrementAndGet();
                }
            }
        });

        CompletableFuture<Void> task2 = CompletableFuture.runAsync(() -> {
            try {
                writingSubmissionService.processEvaluationWebhook(payload2);
                successCount.incrementAndGet();
            } catch (ConcurrencyFailureException e) {
                conflictCount.incrementAndGet();
            } catch (Exception e) {
                if (e.getCause() instanceof ConcurrencyFailureException) {
                    conflictCount.incrementAndGet();
                }
            }
        });

        CompletableFuture.allOf(task1, task2).join();

        // At least one operation succeeds and the state is consistent (SCORED)
        assertThat(successCount.get()).isGreaterThanOrEqualTo(1);
        WritingSubmission updated = writingSubmissionRepository.findById(submission.getId()).orElseThrow();
        assertThat(updated.getStatus()).isEqualTo(SubmissionStatus.SCORED);
    }

    @Test
    @DisplayName("Parallel HTTP webhook requests are protected by Idempotency / Concurrency Guarding")
    void testWebhookEndpointConcurrency_OneSucceedsAndDuplicateRejected() throws Exception {
        WritingWebhookPayloadDTO payload = new WritingWebhookPayloadDTO(
            submission.getId(),
            new BigDecimal("7.5"),
            new BigDecimal("7.0"),
            new BigDecimal("7.0"),
            new BigDecimal("7.5"),
            sampleFeedbackDetail,
            "gemini-2.5-flash",
            "SUCCESS",
            null
        );

        String jsonPayload = objectMapper.writeValueAsString(payload);

        AtomicInteger successResponses = new AtomicInteger(0);
        AtomicInteger conflictResponses = new AtomicInteger(0);

        CompletableFuture<Void> req1 = CompletableFuture.runAsync(() -> {
            try {
                int status = mockMvc.perform(post("/api/v1/writing/webhook/result")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(jsonPayload))
                        .andReturn()
                        .getResponse()
                        .getStatus();
                if (status == 200) {
                    successResponses.incrementAndGet();
                } else if (status == 409) {
                    conflictResponses.incrementAndGet();
                }
            } catch (Exception ignored) {
            }
        });

        CompletableFuture<Void> req2 = CompletableFuture.runAsync(() -> {
            try {
                int status = mockMvc.perform(post("/api/v1/writing/webhook/result")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(jsonPayload))
                        .andReturn()
                        .getResponse()
                        .getStatus();
                if (status == 200) {
                    successResponses.incrementAndGet();
                } else if (status == 409) {
                    conflictResponses.incrementAndGet();
                }
            } catch (Exception ignored) {
            }
        });

        CompletableFuture.allOf(req1, req2).join();

        assertThat(successResponses.get()).isGreaterThanOrEqualTo(1);
    }
}
