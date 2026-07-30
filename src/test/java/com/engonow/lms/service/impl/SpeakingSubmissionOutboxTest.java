package com.engonow.lms.service.impl;

import com.engonow.lms.dto.SpeakingSubmissionRequestDTO;
import com.engonow.lms.dto.SpeakingSubmissionResponseDTO;
import com.engonow.lms.entity.MockTestBooking;
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
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.reactive.function.client.WebClient;

import java.lang.reflect.Method;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class SpeakingSubmissionOutboxTest {

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

    private ObjectMapper objectMapper;
    private SubmissionServiceImpl submissionService;

    @BeforeEach
    void setUp() {
        objectMapper = new ObjectMapper().findAndRegisterModules();
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
                objectMapper);
    }

    @Test
    void savesPendingResultAndOutboxWithoutCallingAiService() throws Exception {
        MockTestBooking booking = MockTestBooking.builder().id(42L).build();
        when(mockTestBookingRepository.findById(42L)).thenReturn(Optional.of(booking));
        when(speakingSessionResultRepository.findBySessionId("42"))
                .thenReturn(Optional.empty());

        JsonNode questionsMetadata = objectMapper.readTree(
                """
                [{"part":"PART_1","question":"Where do you live?"}]
                """);
        SpeakingSubmissionRequestDTO request = new SpeakingSubmissionRequestDTO(
                "42",
                questionsMetadata,
                "https://cdn.example.test/speaking/42.mp3");

        SpeakingSubmissionResponseDTO response =
                submissionService.submitSpeakingEvaluation(request);

        ArgumentCaptor<SpeakingSessionResult> resultCaptor =
                ArgumentCaptor.forClass(SpeakingSessionResult.class);
        verify(speakingSessionResultRepository).save(resultCaptor.capture());
        SpeakingSessionResult pendingResult = resultCaptor.getValue();
        assertEquals("42", pendingResult.getSessionId());
        assertEquals(booking, pendingResult.getBooking());
        assertEquals(SpeakingEvaluationStatus.PENDING,
                pendingResult.getEvaluationStatus());
        assertFalse(pendingResult.getIsComplete());

        ArgumentCaptor<OutboxEvent> outboxCaptor =
                ArgumentCaptor.forClass(OutboxEvent.class);
        verify(outboxEventRepository).save(outboxCaptor.capture());
        OutboxEvent outboxEvent = outboxCaptor.getValue();
        assertEquals("SPEAKING_SESSION", outboxEvent.getAggregateType());
        assertEquals("42", outboxEvent.getAggregateId());
        assertEquals("SPEAKING_EVALUATION_REQUESTED", outboxEvent.getEventType());
        assertEquals(OutboxStatus.PENDING, outboxEvent.getStatus());
        assertEquals(0, outboxEvent.getRetryCount());

        JsonNode payload = objectMapper.readTree(outboxEvent.getPayload());
        assertEquals("42", payload.path("sessionId").asText());
        assertEquals(questionsMetadata, payload.path("questionsMetadata"));
        assertEquals(request.audioUrl(), payload.path("audioUrl").asText());
        assertTrue(payload.hasNonNull("createdAt"));

        assertEquals(SpeakingEvaluationStatus.PENDING, response.status());
        verifyNoInteractions(aiWebClient);
    }

    @Test
    void speakingSubmissionMethodDefinesTheTransactionBoundary() throws Exception {
        Method method = SubmissionServiceImpl.class.getMethod(
                "submitSpeakingEvaluation",
                SpeakingSubmissionRequestDTO.class);

        Transactional transactional = method.getAnnotation(Transactional.class);

        assertNotNull(transactional);
    }
}
