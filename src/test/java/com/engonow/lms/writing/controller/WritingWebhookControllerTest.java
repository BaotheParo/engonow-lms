package com.engonow.lms.writing.controller;

import com.engonow.lms.writing.domain.enums.WritingCriterion;
import com.engonow.lms.writing.domain.feedback.CohesiveDeviceAnalysis;
import com.engonow.lms.writing.domain.feedback.CriterionFeedback;
import com.engonow.lms.writing.domain.feedback.EssayMetrics;
import com.engonow.lms.writing.domain.feedback.WritingFeedbackDetail;
import com.engonow.lms.writing.dto.WritingWebhookPayloadDTO;
import com.engonow.lms.writing.service.WritingSubmissionService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class WritingWebhookControllerTest {

    private MockMvc mockMvc;

    @Mock
    private WritingSubmissionService writingSubmissionService;

    @InjectMocks
    private WritingWebhookController writingWebhookController;

    private ObjectMapper objectMapper;
    private UUID submissionId;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(writingWebhookController).build();
        objectMapper = new ObjectMapper();
        submissionId = UUID.randomUUID();
    }

    @Test
    @DisplayName("POST /api/v1/writing/webhook/result acknowledges valid callback with HTTP 200")
    void handleWritingResultCallback_Success() throws Exception {
        WritingFeedbackDetail feedbackDetail = new WritingFeedbackDetail(
            "Evaluation complete.",
            new EssayMetrics(275, 135, new BigDecimal("0.49"), new BigDecimal("17.2"), new BigDecimal("0.60")),
            List.of(new CriterionFeedback(WritingCriterion.TASK_RESPONSE, new BigDecimal("7.0"), "Good position", List.of("Clear position"), List.of("Minor lapse"), "Actionable tip")),
            List.of(),
            new CohesiveDeviceAnalysis(List.of("In addition"), List.of(), List.of()),
            List.of(),
            List.of()
        );

        WritingWebhookPayloadDTO payload = new WritingWebhookPayloadDTO(
            submissionId,
            new BigDecimal("7.0"),
            new BigDecimal("7.0"),
            new BigDecimal("6.5"),
            new BigDecimal("7.5"),
            feedbackDetail,
            "gemini-2.5-flash",
            "SUCCESS",
            null
        );

        mockMvc.perform(post("/api/v1/writing/webhook/result")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(payload)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ACK"));

        verify(writingSubmissionService).processEvaluationWebhook(payload);
    }
}
