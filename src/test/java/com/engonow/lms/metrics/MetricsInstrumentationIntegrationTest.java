package com.engonow.lms.metrics;

import com.engonow.lms.config.MetricsConfig;
import com.engonow.lms.metrics.impl.CalibrationMetricsServiceImpl;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

public class MetricsInstrumentationIntegrationTest {

    private MeterRegistry meterRegistry;
    private CalibrationMetricsService metricsService;

    @BeforeEach
    void setUp() {
        meterRegistry = new SimpleMeterRegistry();
        MetricsConfig config = new MetricsConfig();
        config.metricsCommonCustomizer().customize(meterRegistry);
        metricsService = new CalibrationMetricsServiceImpl(meterRegistry);
    }

    @Test
    @DisplayName("Test 1: Record submission received increments submission.received.total counter")
    void testRecordSubmissionReceivedCounter() {
        metricsService.recordSubmissionReceived("WRITING", "TASK2");
        metricsService.recordSubmissionReceived("WRITING", "TASK2");
        metricsService.recordSubmissionReceived("SPEAKING", "PART_1");

        Counter writingCounter = meterRegistry.find("submission.received.total")
            .tags("subsystem", "writing", "task_type", "TASK2")
            .counter();
        assertThat(writingCounter).isNotNull();
        assertThat(writingCounter.count()).isEqualTo(2.0);

        Counter speakingCounter = meterRegistry.find("submission.received.total")
            .tags("subsystem", "speaking", "task_type", "PART_1")
            .counter();
        assertThat(speakingCounter).isNotNull();
        assertThat(speakingCounter.count()).isEqualTo(1.0);
    }

    @Test
    @DisplayName("Test 2: Record result persisted updates distribution and result.persisted.total counter")
    void testRecordResultPersistedDistribution() {
        metricsService.recordResultPersisted("WRITING", "AI_AUTO", 6.5, "TASK2");
        metricsService.recordResultPersisted("WRITING", "AI_AUTO", 7.0, "TASK2");

        Counter persistedCounter = meterRegistry.find("result.persisted.total")
            .tags("subsystem", "writing", "evaluated_by", "AI_AUTO", "task_type", "TASK2")
            .counter();
        assertThat(persistedCounter).isNotNull();
        assertThat(persistedCounter.count()).isEqualTo(2.0);

        DistributionSummary summary = meterRegistry.find("writing.result.overall_band")
            .tags("task_type", "TASK2")
            .summary();
        assertThat(summary).isNotNull();
        assertThat(summary.count()).isEqualTo(2);
        assertThat(summary.totalAmount()).isEqualTo(13.5);
    }

    @Test
    @DisplayName("Test 3: Record AI call latency updates ai.call.latency timer")
    void testRecordAiCallLatencyTimer() {
        metricsService.recordAiCallLatency("WRITING", "gemini-2.5-flash", "SUCCESS", 1250);

        Timer timer = meterRegistry.find("ai.call.latency")
            .tags("subsystem", "writing", "model_version", "gemini-2.5-flash", "outcome", "SUCCESS")
            .timer();
        assertThat(timer).isNotNull();
        assertThat(timer.count()).isEqualTo(1);
        assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(1250.0);
    }

    @Test
    @DisplayName("Test 4: Update Outbox backlog and Rater Pool ICC gauges")
    void testUpdateGauges() {
        metricsService.updateOutboxBacklog("engonow.writing.evaluation-requested.v1", 15, 45);
        metricsService.updateRaterPoolIcc("WRITING", 0.885);

        Gauge outboxCountGauge = meterRegistry.find("outbox.unpublished.count")
            .tags("topic", "engonow.writing.evaluation-requested.v1")
            .gauge();
        assertThat(outboxCountGauge).isNotNull();
        assertThat(outboxCountGauge.value()).isEqualTo(15.0);

        Gauge outboxAgeGauge = meterRegistry.find("outbox.oldest.unpublished.age.seconds")
            .tags("topic", "engonow.writing.evaluation-requested.v1")
            .gauge();
        assertThat(outboxAgeGauge).isNotNull();
        assertThat(outboxAgeGauge.value()).isEqualTo(45.0);

        Gauge iccGauge = meterRegistry.find("calibration.rater_pool.icc")
            .tags("subsystem", "writing")
            .gauge();
        assertThat(iccGauge).isNotNull();
        assertThat(iccGauge.value()).isEqualTo(0.885);
    }

    @Test
    @DisplayName("Test 5: PrometheusMeterRegistry scrape contains IELTS buckets and custom metrics")
    void testPrometheusScrapeOutput() {
        io.micrometer.prometheus.PrometheusMeterRegistry promRegistry =
            new io.micrometer.prometheus.PrometheusMeterRegistry(io.micrometer.prometheus.PrometheusConfig.DEFAULT);
        MetricsConfig config = new MetricsConfig();
        config.metricsCommonCustomizer().customize(promRegistry);
        CalibrationMetricsService promMetricsService = new CalibrationMetricsServiceImpl(promRegistry);

        promMetricsService.recordSubmissionReceived("WRITING", "TASK2");
        promMetricsService.recordResultPersisted("WRITING", "AI_AUTO", 6.5, "TASK2");
        promMetricsService.recordAiCallLatency("WRITING", "gemini-2.5-flash", "SUCCESS", 850);
        promMetricsService.updateOutboxBacklog("engonow.writing.evaluation-requested.v1", 10, 30);
        promMetricsService.updateRaterPoolIcc("WRITING", 0.85);

        String scrape = promRegistry.scrape();
        assertThat(scrape).contains("submission_received_total");
        assertThat(scrape).contains("result_persisted_total");
        assertThat(scrape).contains("writing_result_overall_band_bucket");
        assertThat(scrape).contains("le=\"6.5\"");
        assertThat(scrape).contains("ai_call_latency_seconds");
        assertThat(scrape).contains("outbox_unpublished_count");
        assertThat(scrape).contains("calibration_rater_pool_icc");
    }
}
