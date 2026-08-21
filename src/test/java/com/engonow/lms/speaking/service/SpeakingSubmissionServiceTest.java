package com.engonow.lms.speaking.service;

import com.engonow.lms.dto.AudioReferenceDTO;
import com.engonow.lms.dto.SpeakingSubmissionRequestDTO;
import com.engonow.lms.dto.SpeakingSubmissionResponseDTO;
import com.engonow.lms.entity.OutboxEvent;
import com.engonow.lms.entity.SpeakingSessionResult;
import com.engonow.lms.enums.OutboxStatus;
import com.engonow.lms.enums.SpeakingEvaluationStatus;
import com.engonow.lms.mapper.SubmissionMapper;
import com.engonow.lms.repository.ExamRepository;
import com.engonow.lms.repository.MockTestBookingRepository;
import com.engonow.lms.repository.OutboxEventRepository;
import com.engonow.lms.repository.SpeakingSessionResultRepository;
import com.engonow.lms.repository.TestSubmissionRepository;
import com.engonow.lms.repository.UserRepository;
import com.engonow.lms.service.impl.CloudinaryStorageMock;
import com.engonow.lms.service.impl.SubmissionServiceImpl;
import com.engonow.lms.writing.event.OutboxEventCreatedLocalEvent;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.Spy;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.web.reactive.function.client.WebClient;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
public class SpeakingSubmissionServiceTest {

    @Mock
    private ExamRepository examRepository;
    @Mock
    private TestSubmissionRepository testSubmissionRepository;
    @Mock
    private UserRepository userRepository;
    @Mock
    private WebClient aiWebClient;
    @Mock
    private SubmissionMapper submissionMapper;
    @Mock
    private CloudinaryStorageMock cloudinaryStorageMock;
    @Mock
    private MockTestBookingRepository mockTestBookingRepository;
    @Mock
    private SpeakingSessionResultRepository speakingSessionResultRepository;
    @Mock
    private OutboxEventRepository outboxEventRepository;
    @Mock
    private ApplicationEventPublisher applicationEventPublisher;
    @Spy
    private ObjectMapper objectMapper = new ObjectMapper().findAndRegisterModules();

    private SubmissionServiceImpl submissionService;

    @BeforeEach
    void setUp() {
        submissionService = new SubmissionServiceImpl(
            examRepository,
            testSubmissionRepository,
            userRepository,
            aiWebClient,
            submissionMapper,
            cloudinaryStorageMock,
            mockTestBookingRepository,
            speakingSessionResultRepository,
            outboxEventRepository,
            objectMapper
        );
        submissionService.setApplicationEventPublisher(applicationEventPublisher);
    }

    @Test
    @DisplayName("Submit speaking attempt with Claim-Check audio reference succeeds and publishes outbox event")
    void testSubmitSpeakingClaimCheckSuccess() {
        UUID studentId = UUID.randomUUID();
        AudioReferenceDTO audioRef = new AudioReferenceDTO(
            "MINIO",
            "engonow-audio-recordings",
            "recordings/2026/08/sample.wav",
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "audio/wav",
            120.0
        );

        SpeakingSubmissionRequestDTO request = new SpeakingSubmissionRequestDTO(
            studentId,
            "PART_2",
            "Describe a memorable journey",
            audioRef
        );

        when(outboxEventRepository.save(any(OutboxEvent.class))).thenAnswer(i -> {
            OutboxEvent event = i.getArgument(0);
            event.setId(UUID.randomUUID());
            return event;
        });

        SpeakingSubmissionResponseDTO response = submissionService.submitSpeakingEvaluation(request);

        assertThat(response).isNotNull();
        assertThat(response.status()).isEqualTo(SpeakingEvaluationStatus.PENDING);
        assertThat(response.sessionId()).isNotNull();

        // Verify SpeakingSessionResult saved
        ArgumentCaptor<SpeakingSessionResult> resultCaptor = ArgumentCaptor.forClass(SpeakingSessionResult.class);
        verify(speakingSessionResultRepository).save(resultCaptor.capture());
        assertThat(resultCaptor.getValue().getEvaluationStatus()).isEqualTo(SpeakingEvaluationStatus.PENDING);
        assertThat(resultCaptor.getValue().getIsComplete()).isFalse();

        // Verify Outbox saved
        ArgumentCaptor<OutboxEvent> outboxCaptor = ArgumentCaptor.forClass(OutboxEvent.class);
        verify(outboxEventRepository).save(outboxCaptor.capture());
        OutboxEvent outbox = outboxCaptor.getValue();
        assertThat(outbox.getAggregateType()).isEqualTo("SPEAKING_ATTEMPT");
        assertThat(outbox.getEventType()).isEqualTo("SPEAKING_EVALUATION_REQUESTED");
        assertThat(outbox.getStatus()).isEqualTo(OutboxStatus.PENDING);
        assertThat(outbox.getPayload()).contains("recordings/2026/08/sample.wav");
        assertThat(outbox.getPayload()).doesNotContain("data:audio");

        // Verify LocalEvent published for eager Kafka dispatch
        ArgumentCaptor<OutboxEventCreatedLocalEvent> localEventCaptor = ArgumentCaptor.forClass(OutboxEventCreatedLocalEvent.class);
        verify(applicationEventPublisher).publishEvent(localEventCaptor.capture());
        assertThat(localEventCaptor.getValue().topic()).isEqualTo("engonow.speaking.evaluation-requested.v1");
    }

    @Test
    @DisplayName("Submit speaking attempt fails when audio contentType is unsupported")
    void testSubmitSpeakingUnsupportedAudioType() {
        UUID studentId = UUID.randomUUID();
        AudioReferenceDTO audioRef = new AudioReferenceDTO(
            "MINIO",
            "bucket",
            "sample.txt",
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "text/plain",
            10.0
        );

        SpeakingSubmissionRequestDTO request = new SpeakingSubmissionRequestDTO(
            studentId,
            "PART_1",
            "Topic",
            audioRef
        );

        assertThatThrownBy(() -> submissionService.submitSpeakingEvaluation(request))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("Unsupported audio content type");
    }
}
