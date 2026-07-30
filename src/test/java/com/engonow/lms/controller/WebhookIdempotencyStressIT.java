package com.engonow.lms.controller;

import com.engonow.lms.dto.SpeakingWebhookPayload;
import com.engonow.lms.entity.MockTestBooking;
import com.engonow.lms.repository.MockTestBookingRepository;
import com.engonow.lms.repository.SpeakingSessionResultRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;

import java.math.BigDecimal;
import java.util.Collections;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebhookIdempotencyStressIT {

    private static final String API_URL = "/api/v1/callback/ai-grading";
    private static final String IDEMPOTENCY_KEY_PREFIX = "webhook:speaking:";
    private static final int TOTAL_THREADS = 20;

    @Autowired
    private TestRestTemplate restTemplate;

    @Autowired
    private StringRedisTemplate stringRedisTemplate;

    @Autowired
    private MockTestBookingRepository mockTestBookingRepository;

    @Autowired
    private SpeakingSessionResultRepository speakingSessionResultRepository;

    private String sessionId;
    private String finalKey;

    @BeforeEach
    void setUp() {
        flushRedisDatabase();
        speakingSessionResultRepository.deleteAllInBatch();

        MockTestBooking booking = mockTestBookingRepository.findAll().stream()
                .findFirst()
                .orElseThrow(() -> new AssertionError(
                        "No test booking is available for the webhook stress test"));

        sessionId = booking.getId().toString();
        finalKey = IDEMPOTENCY_KEY_PREFIX + sessionId;
    }

    @AfterEach
    void tearDown() {
        speakingSessionResultRepository.deleteAllInBatch();
        flushRedisDatabase();
    }

    @Test
    void testHighConcurrency_IdempotentWebhook_AllowsExactlyOneSuccess()
            throws InterruptedException {

        int totalThreads = TOTAL_THREADS;
        ExecutorService executor = Executors.newFixedThreadPool(totalThreads);
        CountDownLatch readyLatch = new CountDownLatch(totalThreads);
        CountDownLatch startLatch = new CountDownLatch(1);
        CountDownLatch doneLatch = new CountDownLatch(totalThreads);

        AtomicInteger successCount = new AtomicInteger(0);
        AtomicInteger conflictCount = new AtomicInteger(0);
        AtomicInteger otherErrorCount = new AtomicInteger(0);

        SpeakingWebhookPayload payload = new SpeakingWebhookPayload(
                sessionId,
                BigDecimal.valueOf(7.0),
                BigDecimal.valueOf(7.0),
                BigDecimal.valueOf(7.0),
                BigDecimal.valueOf(7.0),
                Collections.emptyList(),
                Collections.emptyList(),
                "High-concurrency Redis idempotency stress test.");

        try {
            for (int index = 0; index < totalThreads; index++) {
                executor.submit(() -> {
                    readyLatch.countDown();
                    try {
                        startLatch.await();

                        ResponseEntity<Void> response =
                                restTemplate.postForEntity(
                                        API_URL,
                                        payload,
                                        Void.class);
                        HttpStatusCode statusCode = response.getStatusCode();

                        if (statusCode.is2xxSuccessful()) {
                            successCount.incrementAndGet();
                        } else if (statusCode.value() == HttpStatus.CONFLICT.value()) {
                            conflictCount.incrementAndGet();
                        } else {
                            otherErrorCount.incrementAndGet();
                        }
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        otherErrorCount.incrementAndGet();
                    } catch (Exception ex) {
                        otherErrorCount.incrementAndGet();
                    } finally {
                        doneLatch.countDown();
                    }
                });
            }

            boolean allWorkersReady = readyLatch.await(10, TimeUnit.SECONDS);
            assertTrue(allWorkersReady, "All request threads must reach the starting line");

            startLatch.countDown();

            boolean allRequestsCompleted = doneLatch.await(10, TimeUnit.SECONDS);
            assertTrue(allRequestsCompleted, "All HTTP requests must complete within 10 seconds");
        } finally {
            startLatch.countDown();
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }

        assertEquals(
                1,
                successCount.get(),
                "Exactly ONE request must acquire the lock and return HTTP 2XX");
        assertEquals(
                19,
                conflictCount.get(),
                "Exactly 19 duplicate requests must be rejected with HTTP 409 Conflict");
        assertEquals(
                0,
                otherErrorCount.get(),
                "No request should fail with infra or unexpected HTTP errors");

        String finalState = stringRedisTemplate.opsForValue().get(finalKey);
        assertEquals(
                "COMPLETED",
                finalState,
                "The Redis idempotency key must finish in the COMPLETED state");
    }

    private void flushRedisDatabase() {
        RedisConnectionFactory connectionFactory =
                stringRedisTemplate.getConnectionFactory();
        assertNotNull(connectionFactory, "RedisConnectionFactory must be configured");

        try (RedisConnection connection = connectionFactory.getConnection()) {
            connection.serverCommands().flushDb();
        }
    }
}
