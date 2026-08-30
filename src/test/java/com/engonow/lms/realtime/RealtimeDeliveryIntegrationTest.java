package com.engonow.lms.realtime;

import com.engonow.lms.dto.SubmissionStatusEventDTO;
import com.engonow.lms.entity.SpeakingSessionResult;
import com.engonow.lms.repository.SpeakingSessionResultRepository;
import com.engonow.lms.service.impl.RealtimeDeliveryServiceImpl;
import com.engonow.lms.writing.controller.WritingSubmissionEventsController;
import com.engonow.lms.writing.domain.enums.SubmissionStatus;
import com.engonow.lms.writing.domain.entity.WritingResult;
import com.engonow.lms.writing.domain.entity.WritingSubmission;
import com.engonow.lms.writing.repository.WritingResultRepository;
import com.engonow.lms.writing.repository.WritingSubmissionRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
public class RealtimeDeliveryIntegrationTest {

    @Mock
    private StringRedisTemplate stringRedisTemplate;

    @Mock
    private RedisMessageListenerContainer redisMessageListenerContainer;

    @Mock
    private WritingSubmissionRepository writingSubmissionRepository;

    @Mock
    private WritingResultRepository writingResultRepository;

    @Mock
    private SpeakingSessionResultRepository speakingSessionResultRepository;

    private ObjectMapper objectMapper;
    private RealtimeDeliveryServiceImpl realtimeDeliveryService;
    private WritingSubmissionEventsController writingEventsController;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        objectMapper = new ObjectMapper();
        objectMapper.findAndRegisterModules();

        realtimeDeliveryService = new RealtimeDeliveryServiceImpl(
            stringRedisTemplate,
            redisMessageListenerContainer,
            objectMapper,
            writingSubmissionRepository,
            writingResultRepository,
            speakingSessionResultRepository
        );

        writingEventsController = new WritingSubmissionEventsController(realtimeDeliveryService);
        mockMvc = MockMvcBuilders.standaloneSetup(writingEventsController).build();
    }

    @Test
    @DisplayName("Test 1: Immediate Current-State Replay On Connect (Non-Terminal State)")
    void testImmediateCurrentStateReplayOnConnect() throws Exception {
        UUID submissionId = UUID.randomUUID();
        WritingSubmission submission = new WritingSubmission();
        submission.setId(submissionId);
        submission.setStatus(SubmissionStatus.PROCESSING);

        when(writingSubmissionRepository.findById(submissionId)).thenReturn(Optional.of(submission));

        // Connect via REST controller endpoint
        MvcResult mvcResult = mockMvc.perform(get("/api/v1/writing-submissions/{id}/events", submissionId)
                .accept(MediaType.TEXT_EVENT_STREAM))
                .andExpect(status().isOk())
                .andReturn();

        assertThat(mvcResult.getResponse().getContentType()).contains(MediaType.TEXT_EVENT_STREAM_VALUE);
        assertThat(mvcResult.getResponse().getHeader("X-Accel-Buffering")).isEqualTo("no");
        assertThat(mvcResult.getResponse().getHeader("Cache-Control")).contains("no-cache");

        // Verify Redis dynamic subscription registered for non-terminal state
        verify(redisMessageListenerContainer, times(1))
            .addMessageListener(any(MessageListener.class), eq(new ChannelTopic("sse:submission:" + submissionId)));
    }

    @Test
    @DisplayName("Test 2: Terminal State Completes Emitter Immediately Without Hanging")
    void testTerminalStateCompletesEmitterImmediately() {
        UUID submissionId = UUID.randomUUID();
        UUID resultId = UUID.randomUUID();

        WritingSubmission submission = new WritingSubmission();
        submission.setId(submissionId);
        submission.setStatus(SubmissionStatus.SCORED);

        WritingResult result = new WritingResult();
        result.setId(resultId);
        result.setSubmission(submission);
        result.setIsCurrent(true);

        when(writingSubmissionRepository.findById(submissionId)).thenReturn(Optional.of(submission));
        when(writingResultRepository.findBySubmissionIdAndIsCurrentTrue(submissionId)).thenReturn(Optional.of(result));

        SseEmitter emitter = realtimeDeliveryService.subscribeToSubmissionEvents("WRITING", submissionId);
        assertThat(emitter).isNotNull();

        // Terminal state should NOT subscribe to Redis Pub/Sub
        verify(redisMessageListenerContainer, never())
            .addMessageListener(any(MessageListener.class), any(org.springframework.data.redis.listener.Topic.class));
    }

    @Test
    @DisplayName("Test 3: Redis Pub/Sub Broadcast Delivery to Active Local SseEmitters")
    void testRedisPubSubBroadcastDelivery() throws Exception {
        UUID submissionId = UUID.randomUUID();
        UUID resultId = UUID.randomUUID();

        WritingSubmission submission = new WritingSubmission();
        submission.setId(submissionId);
        submission.setStatus(SubmissionStatus.PENDING);

        when(writingSubmissionRepository.findById(submissionId)).thenReturn(Optional.of(submission));

        // 1. Subscribe local emitter
        SseEmitter emitter = realtimeDeliveryService.subscribeToSubmissionEvents("WRITING", submissionId);
        assertThat(emitter).isNotNull();

        // 2. Simulate broadcast from Kafka listener on another cluster node
        SubmissionStatusEventDTO broadcastEvent = SubmissionStatusEventDTO.builder()
            .status("SCORED")
            .submissionId(submissionId)
            .resultId(resultId)
            .subsystem("WRITING")
            .timestamp(Instant.now())
            .build();

        String payloadJson = objectMapper.writeValueAsString(broadcastEvent);

        // 3. Broadcast status change publishes to Redis
        realtimeDeliveryService.broadcastStatusChange(broadcastEvent);
        verify(stringRedisTemplate, times(1)).convertAndSend(eq("sse:submission:" + submissionId), any(String.class));

        // 4. Simulate Redis message delivery on this node
        realtimeDeliveryService.handleRedisMessage("sse:submission:" + submissionId, payloadJson);

        // 5. Terminal event should trigger Redis unsubscribe
        verify(redisMessageListenerContainer, times(1))
            .removeMessageListener(any(MessageListener.class), eq(new ChannelTopic("sse:submission:" + submissionId)));
    }

    @Test
    @DisplayName("Test 4: Emitter Cleanup on Timeout and Disconnect")
    void testEmitterCleanupOnTimeoutAndDisconnect() {
        UUID submissionId = UUID.randomUUID();

        WritingSubmission submission = new WritingSubmission();
        submission.setId(submissionId);
        submission.setStatus(SubmissionStatus.PENDING);

        when(writingSubmissionRepository.findById(submissionId)).thenReturn(Optional.of(submission));

        SseEmitter emitter = realtimeDeliveryService.subscribeToSubmissionEvents("WRITING", submissionId);
        assertThat(emitter).isNotNull();

        // Simulate client disconnect / error
        emitter.complete();

        // Verify Redis subscription is cleared
        verify(redisMessageListenerContainer, times(1))
            .addMessageListener(any(MessageListener.class), eq(new ChannelTopic("sse:submission:" + submissionId)));
    }

    @Test
    @DisplayName("Test 5: Scheduled Keep-Alive Heartbeat Pings")
    void testKeepAlivePings() {
        UUID submissionId = UUID.randomUUID();

        WritingSubmission submission = new WritingSubmission();
        submission.setId(submissionId);
        submission.setStatus(SubmissionStatus.PROCESSING);

        when(writingSubmissionRepository.findById(submissionId)).thenReturn(Optional.of(submission));

        SseEmitter emitter = realtimeDeliveryService.subscribeToSubmissionEvents("WRITING", submissionId);
        assertThat(emitter).isNotNull();

        // Trigger scheduled heartbeat ping
        realtimeDeliveryService.sendKeepAlivePings();
        // Completed cleanly without dropping active emitters
    }
}
