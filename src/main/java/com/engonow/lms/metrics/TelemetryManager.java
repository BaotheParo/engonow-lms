package com.engonow.lms.metrics;

import com.engonow.lms.enums.OutboxStatus;
import com.engonow.lms.repository.OutboxEventRepository;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import jakarta.annotation.PostConstruct;
import java.util.Locale;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
@Slf4j
public class TelemetryManager {

    private static final String UNKNOWN_TAG_VALUE = "UNKNOWN";

    private final MeterRegistry meterRegistry;
    private final OutboxEventRepository outboxEventRepository;

    @PostConstruct
    void registerMetrics() {
        Gauge.builder(
                        "engonow_outbox_pending_size",
                        outboxEventRepository,
                        this::pendingOutboxCount)
                .description("Current number of pending outbox events")
                .register(meterRegistry);
    }

    public void incrementIdempotencyConflict(String aggregateType) {
        incrementCounter(
                "engonow_idempotency_conflicts_total",
                "Total number of idempotency conflicts rejected",
                "aggregate_type",
                normalizeTagValue(aggregateType));
    }

    public void incrementProcessedResults(String status) {
        incrementCounter(
                "engonow_speaking_results_saved_total",
                "Total number of speaking results saved",
                "status",
                normalizeTagValue(status));
    }

    public void incrementOutboxRelayErrors() {
        try {
            Counter.builder("engonow_outbox_relay_errors_total")
                    .description("Total number of outbox relay processing errors")
                    .register(meterRegistry)
                    .increment();
        } catch (RuntimeException exception) {
            log.warn(
                    "[TELEMETRY] Unable to increment outbox relay error counter",
                    exception);
        }
    }

    private void incrementCounter(
            String metricName,
            String description,
            String tagName,
            String tagValue) {
        try {
            Counter.builder(metricName)
                    .description(description)
                    .tag(tagName, tagValue)
                    .register(meterRegistry)
                    .increment();
        } catch (RuntimeException exception) {
            log.warn(
                    "[TELEMETRY] Unable to increment metric {} with {}={}",
                    metricName,
                    tagName,
                    tagValue,
                    exception);
        }
    }

    private double pendingOutboxCount(OutboxEventRepository repository) {
        try {
            return repository.countByStatus(OutboxStatus.PENDING);
        } catch (RuntimeException exception) {
            log.warn(
                    "[TELEMETRY] Unable to read pending outbox queue size",
                    exception);
            return Double.NaN;
        }
    }

    private String normalizeTagValue(String value) {
        if (value == null || value.isBlank()) {
            return UNKNOWN_TAG_VALUE;
        }
        return value.trim().toUpperCase(Locale.ROOT);
    }
}
