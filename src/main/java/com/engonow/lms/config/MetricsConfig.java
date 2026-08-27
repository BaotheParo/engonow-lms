package com.engonow.lms.config;

import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.distribution.DistributionStatisticConfig;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

@Configuration
public class MetricsConfig {

    // Micrometer SLA boundaries must be strictly > 0
    private static final double[] IELTS_BAND_BUCKETS = {
        0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5,
        5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0
    };

    private static final double[] CALIBRATION_ERROR_BUCKETS = {
        0.25, 0.5, 0.75, 1.0, 1.5, 2.0
    };

    private static final double[] AI_CALL_LATENCY_SLAS = {
        Duration.ofMillis(500).toNanos(),
        Duration.ofSeconds(1).toNanos(),
        Duration.ofSeconds(2).toNanos(),
        Duration.ofSeconds(3).toNanos(),
        Duration.ofSeconds(5).toNanos(),
        Duration.ofSeconds(8).toNanos(),
        Duration.ofSeconds(13).toNanos(),
        Duration.ofSeconds(21).toNanos(),
        Duration.ofSeconds(34).toNanos()
    };

    @Bean
    public MeterRegistryCustomizer<MeterRegistry> metricsCommonCustomizer() {
        return registry -> registry.config().meterFilter(new MeterFilter() {
            @Override
            public DistributionStatisticConfig configure(Meter.Id id, DistributionStatisticConfig config) {
                String name = id.getName();
                if ("writing.result.overall_band".equals(name) || "speaking.result.overall_band".equals(name)) {
                    return DistributionStatisticConfig.builder()
                        .serviceLevelObjectives(IELTS_BAND_BUCKETS)
                        .build()
                        .merge(config);
                }
                if ("calibration.sample.error.absolute".equals(name)) {
                    return DistributionStatisticConfig.builder()
                        .serviceLevelObjectives(CALIBRATION_ERROR_BUCKETS)
                        .build()
                        .merge(config);
                }
                if ("ai.call.latency".equals(name)) {
                    return DistributionStatisticConfig.builder()
                        .serviceLevelObjectives(AI_CALL_LATENCY_SLAS)
                        .build()
                        .merge(config);
                }
                return config;
            }
        });
    }
}
