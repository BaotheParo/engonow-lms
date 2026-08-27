package com.engonow.lms.metrics;

public interface CalibrationMetricsService {

    void recordSubmissionReceived(String subsystem, String taskType);

    void recordResultPersisted(String subsystem, String evaluatedBy, double overallBand, String taskType);

    void recordAiCallLatency(String subsystem, String modelVersion, String outcome, long durationMs);

    void recordCalibrationError(String subsystem, String criterion, double absoluteError);

    void updateRaterPoolIcc(String subsystem, double icc);

    void updateOutboxBacklog(String topic, int count, long oldestAgeSeconds);
}
