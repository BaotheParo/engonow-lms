package com.engonow.lms.metrics.impl;

import com.engonow.lms.metrics.CalibrationMetricsService;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tag;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.Timer;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

@Service
@RequiredArgsConstructor
@Slf4j
public class CalibrationMetricsServiceImpl implements CalibrationMetricsService {

    private final MeterRegistry meterRegistry;

    // Gauges tracking state
    private final Map<String, AtomicReference<Double>> raterPoolIccGauges = new ConcurrentHashMap<>();
    private final Map<String, AtomicInteger> outboxBacklogGauges = new ConcurrentHashMap<>();
    private final Map<String, AtomicLong> outboxAgeGauges = new ConcurrentHashMap<>();

    @Override
    public void recordSubmissionReceived(String subsystem, String taskType) {
        Counter.builder("submission.received.total")
            .description("Total number of submissions received")
            .tags("subsystem", subsystem.toLowerCase(), "task_type", taskType)
            .register(meterRegistry)
            .increment();
    }

    @Override
    public void recordResultPersisted(String subsystem, String evaluatedBy, double overallBand, String taskType) {
        String subKey = subsystem.toLowerCase();

        // 1. Result persisted counter
        Counter.builder("result.persisted.total")
            .description("Total number of evaluation results persisted")
            .tags("subsystem", subKey, "evaluated_by", evaluatedBy, "task_type", taskType)
            .register(meterRegistry)
            .increment();

        // 2. Exact IELTS Band DistributionSummary (writing.result.overall_band / speaking.result.overall_band)
        String metricName = subKey + ".result.overall_band";
        DistributionSummary.builder(metricName)
            .description("Distribution of overall IELTS band scores")
            .tags("task_type", taskType)
            .register(meterRegistry)
            .record(overallBand);
    }

    @Override
    public void recordAiCallLatency(String subsystem, String modelVersion, String outcome, long durationMs) {
        Timer.builder("ai.call.latency")
            .description("Latency of AI model evaluation invocations")
            .tags("subsystem", subsystem.toLowerCase(), "model_version", modelVersion, "outcome", outcome)
            .register(meterRegistry)
            .record(durationMs, TimeUnit.MILLISECONDS);
    }

    @Override
    public void recordCalibrationError(String subsystem, String criterion, double absoluteError) {
        DistributionSummary.builder("calibration.sample.error.absolute")
            .description("Absolute error of AI evaluation vs Human reference score")
            .tags("subsystem", subsystem.toLowerCase(), "criterion", criterion)
            .register(meterRegistry)
            .record(absoluteError);
    }

    @Override
    public void updateRaterPoolIcc(String subsystem, double icc) {
        String subKey = subsystem.toLowerCase();
        raterPoolIccGauges.computeIfAbsent(subKey, k -> {
            AtomicReference<Double> ref = new AtomicReference<>(icc);
            meterRegistry.gauge("calibration.rater_pool.icc", Tags.of("subsystem", subKey), ref, AtomicReference::get);
            return ref;
        }).set(icc);
    }

    @Override
    public void updateOutboxBacklog(String topic, int count, long oldestAgeSeconds) {
        outboxBacklogGauges.computeIfAbsent(topic, t -> {
            AtomicInteger val = new AtomicInteger(count);
            meterRegistry.gauge("outbox.unpublished.count", Tags.of("topic", t), val, AtomicInteger::get);
            return val;
        }).set(count);

        outboxAgeGauges.computeIfAbsent(topic, t -> {
            AtomicLong val = new AtomicLong(oldestAgeSeconds);
            meterRegistry.gauge("outbox.oldest.unpublished.age.seconds", Tags.of("topic", t), val, AtomicLong::get);
            return val;
        }).set(oldestAgeSeconds);
    }
}
