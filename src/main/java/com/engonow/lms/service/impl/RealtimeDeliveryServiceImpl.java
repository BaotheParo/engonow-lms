package com.engonow.lms.service.impl;

import com.engonow.lms.dto.SubmissionStatusEventDTO;
import com.engonow.lms.entity.SpeakingSessionResult;
import com.engonow.lms.repository.SpeakingSessionResultRepository;
import com.engonow.lms.service.RealtimeDeliveryService;
import com.engonow.lms.writing.domain.entity.WritingResult;
import com.engonow.lms.writing.domain.entity.WritingSubmission;
import com.engonow.lms.writing.repository.WritingResultRepository;
import com.engonow.lms.writing.repository.WritingSubmissionRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

@Service
@RequiredArgsConstructor
@Slf4j
public class RealtimeDeliveryServiceImpl implements RealtimeDeliveryService {

    private static final long SSE_TIMEOUT_MS = 300_000L; // 5 minutes

    private final StringRedisTemplate stringRedisTemplate;
    private final RedisMessageListenerContainer redisMessageListenerContainer;
    private final ObjectMapper objectMapper;
    private final WritingSubmissionRepository writingSubmissionRepository;
    private final WritingResultRepository writingResultRepository;
    private final SpeakingSessionResultRepository speakingSessionResultRepository;

    // In-memory mapping of active SSE connections per submissionId
    private final ConcurrentHashMap<UUID, CopyOnWriteArrayList<SseEmitter>> activeEmitters = new ConcurrentHashMap<>();
    // In-memory mapping of active dynamic Redis subscriptions per submissionId
    private final ConcurrentHashMap<UUID, MessageListener> activeSubscriptions = new ConcurrentHashMap<>();

    @Override
    public SseEmitter subscribeToSubmissionEvents(String subsystem, UUID submissionId) {
        SseEmitter emitter = new SseEmitter(SSE_TIMEOUT_MS);

        // 1. Register lifecycle callbacks for clean resource disposal
        emitter.onCompletion(() -> removeEmitter(submissionId, emitter));
        emitter.onTimeout(() -> {
            log.debug("[SSE TIMEOUT] Emitter timed out for submissionId={}", submissionId);
            emitter.complete();
            removeEmitter(submissionId, emitter);
        });
        emitter.onError(ex -> {
            log.debug("[SSE ERROR] Emitter error for submissionId={}: {}", submissionId, ex.getMessage());
            removeEmitter(submissionId, emitter);
        });

        // 2. Fetch current state from Database (Immediate Current-State Replay)
        String currentStatus = "PENDING";
        UUID resultId = null;

        if ("WRITING".equalsIgnoreCase(subsystem)) {
            Optional<WritingSubmission> optSub = writingSubmissionRepository.findById(submissionId);
            if (optSub.isPresent()) {
                WritingSubmission sub = optSub.get();
                currentStatus = sub.getStatus() != null ? sub.getStatus().name() : "PENDING";
                if ("SCORED".equalsIgnoreCase(currentStatus)) {
                    resultId = writingResultRepository.findBySubmissionIdAndIsCurrentTrue(submissionId)
                        .map(WritingResult::getId)
                        .orElse(null);
                }
            }
        } else if ("SPEAKING".equalsIgnoreCase(subsystem)) {
            Optional<SpeakingSessionResult> optRes = speakingSessionResultRepository.findBySessionId(submissionId.toString());
            if (optRes.isPresent()) {
                currentStatus = "SCORED";
                SpeakingSessionResult res = optRes.get();
                if (res.getId() != null) {
                    resultId = UUID.nameUUIDFromBytes(res.getId().toString().getBytes(StandardCharsets.UTF_8));
                }
            }
        }

        // 3. Immediately emit initial status event to client
        SubmissionStatusEventDTO initialEvent = SubmissionStatusEventDTO.builder()
            .status(currentStatus)
            .submissionId(submissionId)
            .resultId(resultId)
            .subsystem(subsystem.toUpperCase())
            .timestamp(Instant.now())
            .build();

        try {
            emitter.send(SseEmitter.event().name("status").data(initialEvent));
        } catch (Exception ex) {
            log.error("[SSE ERROR] Failed to send initial status event for submissionId={}", submissionId, ex);
            emitter.completeWithError(ex);
            return emitter;
        }

        // 4. If current state is terminal (SCORED or FAILED), complete emitter immediately
        if ("SCORED".equalsIgnoreCase(currentStatus) || "FAILED".equalsIgnoreCase(currentStatus)) {
            log.info("[SSE TERMINAL] Submission {} is in terminal state {}, completing emitter immediately", submissionId, currentStatus);
            emitter.complete();
            return emitter;
        }

        // 5. Register active emitter and subscribe dynamically to Redis Pub/Sub channel if first subscriber
        activeEmitters.computeIfAbsent(submissionId, k -> new CopyOnWriteArrayList<>()).add(emitter);

        activeSubscriptions.computeIfAbsent(submissionId, k -> {
            ChannelTopic topic = new ChannelTopic("sse:submission:" + submissionId);
            MessageListener listener = (message, pattern) -> {
                String payload = new String(message.getBody(), StandardCharsets.UTF_8);
                String channel = new String(message.getChannel(), StandardCharsets.UTF_8);
                handleRedisMessage(channel, payload);
            };
            if (redisMessageListenerContainer != null) {
                redisMessageListenerContainer.addMessageListener(listener, topic);
                log.info("[REDIS PUB/SUB] Subscribed to channel {} for submissionId={}", topic.getTopic(), submissionId);
            }
            return listener;
        });

        return emitter;
    }

    @Override
    public void broadcastStatusChange(SubmissionStatusEventDTO event) {
        if (event == null || event.getSubmissionId() == null) {
            return;
        }
        try {
            if (event.getTimestamp() == null) {
                event.setTimestamp(Instant.now());
            }
            String json = objectMapper.writeValueAsString(event);
            String channel = "sse:submission:" + event.getSubmissionId();
            stringRedisTemplate.convertAndSend(channel, json);
            log.info("[REDIS PUB/SUB] Broadcasted status event {} to channel {}", event.getStatus(), channel);
        } catch (Exception ex) {
            log.error("[REDIS PUB/SUB] Failed to broadcast status change for submissionId={}", event.getSubmissionId(), ex);
        }
    }

    @Override
    public void handleRedisMessage(String channel, String messagePayload) {
        try {
            SubmissionStatusEventDTO event = objectMapper.readValue(messagePayload, SubmissionStatusEventDTO.class);
            UUID submissionId = event.getSubmissionId();
            if (submissionId == null) {
                return;
            }

            CopyOnWriteArrayList<SseEmitter> emitters = activeEmitters.get(submissionId);
            if (emitters != null && !emitters.isEmpty()) {
                boolean isTerminal = "SCORED".equalsIgnoreCase(event.getStatus()) || "FAILED".equalsIgnoreCase(event.getStatus());

                for (SseEmitter emitter : emitters) {
                    try {
                        emitter.send(SseEmitter.event().name("status").data(event));
                        if (isTerminal) {
                            emitter.complete();
                        }
                    } catch (Exception ex) {
                        emitter.completeWithError(ex);
                        emitters.remove(emitter);
                    }
                }

                if (isTerminal || emitters.isEmpty()) {
                    activeEmitters.remove(submissionId);
                    unsubscribeFromRedis(submissionId);
                }
            }
        } catch (Exception ex) {
            log.error("[REDIS PUB/SUB] Failed to handle incoming message on channel {}: {}", channel, messagePayload, ex);
        }
    }

    private void removeEmitter(UUID submissionId, SseEmitter emitter) {
        CopyOnWriteArrayList<SseEmitter> list = activeEmitters.get(submissionId);
        if (list != null) {
            list.remove(emitter);
            if (list.isEmpty()) {
                activeEmitters.remove(submissionId);
                unsubscribeFromRedis(submissionId);
            }
        }
    }

    @org.springframework.scheduling.annotation.Scheduled(fixedRate = 25_000)
    public void sendKeepAlivePings() {
        if (activeEmitters.isEmpty()) {
            return;
        }
        for (var entry : activeEmitters.entrySet()) {
            UUID submissionId = entry.getKey();
            CopyOnWriteArrayList<SseEmitter> emitters = entry.getValue();
            for (SseEmitter emitter : emitters) {
                try {
                    // Send SSE heartbeat comment (": ping\n\n") to keep reverse proxies alive
                    emitter.send(SseEmitter.event().comment("ping"));
                } catch (Exception ex) {
                    log.debug("[SSE PING] Failed to send heartbeat to emitter for submissionId={}, removing: {}",
                        submissionId, ex.getMessage());
                    removeEmitter(submissionId, emitter);
                }
            }
        }
    }

    private void unsubscribeFromRedis(UUID submissionId) {
        MessageListener listener = activeSubscriptions.remove(submissionId);
        if (listener != null && redisMessageListenerContainer != null) {
            redisMessageListenerContainer.removeMessageListener(listener, new ChannelTopic("sse:submission:" + submissionId));
            log.info("[REDIS PUB/SUB] Unsubscribed from channel sse:submission:{}", submissionId);
        }
    }
}
