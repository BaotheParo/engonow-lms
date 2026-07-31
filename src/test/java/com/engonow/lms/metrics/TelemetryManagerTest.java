package com.engonow.lms.metrics;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import com.engonow.lms.repository.OutboxEventRepository;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@SpringBootTest(
        classes = {
            TelemetryManager.class,
            TelemetryManagerTest.MetricsTestConfiguration.class
        })
class TelemetryManagerTest {

    @Autowired
    private TelemetryManager telemetryManager;

    @Autowired
    private MeterRegistry meterRegistry;

    @Test
    void incrementsIdempotencyConflictCounter() {
        telemetryManager.incrementIdempotencyConflict("TEST");

        assertThat(
                        meterRegistry
                                .get("engonow_idempotency_conflicts_total")
                                .tag("aggregate_type", "TEST")
                                .counter()
                                .count())
                .isEqualTo(1.0);
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class MetricsTestConfiguration {

        @Bean
        MeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }

        @Bean
        OutboxEventRepository outboxEventRepository() {
            return mock(OutboxEventRepository.class);
        }
    }
}
