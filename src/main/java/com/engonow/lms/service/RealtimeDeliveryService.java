package com.engonow.lms.service;

import com.engonow.lms.dto.SubmissionStatusEventDTO;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.UUID;

public interface RealtimeDeliveryService {

    /**
     * Subscribes a client to live Server-Sent Events (SSE) for a specific submission.
     * Immediately emits the current state from the database and subscribes to Redis Pub/Sub
     * if the state is non-terminal.
     *
     * @param subsystem "WRITING" or "SPEAKING"
     * @param submissionId target submission UUID
     * @return active SseEmitter instance
     */
    SseEmitter subscribeToSubmissionEvents(String subsystem, UUID submissionId);

    /**
     * Broadcasts a status change event across the horizontally scaled cluster via Redis Pub/Sub.
     *
     * @param event status event DTO
     */
    void broadcastStatusChange(SubmissionStatusEventDTO event);

    /**
     * Handles an incoming Redis Pub/Sub message from a cluster peer and forwards it to local SSE emitters.
     *
     * @param channel Redis channel name (e.g. sse:submission:{id})
     * @param messagePayload serialized JSON payload
     */
    void handleRedisMessage(String channel, String messagePayload);
}
