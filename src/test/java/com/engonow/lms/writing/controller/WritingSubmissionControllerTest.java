package com.engonow.lms.writing.controller;

import com.engonow.lms.writing.domain.enums.EvaluatedBy;
import com.engonow.lms.writing.domain.enums.SubmissionStatus;
import com.engonow.lms.writing.domain.enums.TaskType;
import com.engonow.lms.writing.domain.enums.WritingCriterion;
import com.engonow.lms.writing.domain.feedback.CohesiveDeviceAnalysis;
import com.engonow.lms.writing.domain.feedback.CriterionFeedback;
import com.engonow.lms.writing.domain.feedback.EssayMetrics;
import com.engonow.lms.writing.domain.feedback.WritingFeedbackDetail;
import com.engonow.lms.writing.dto.WritingResultResponseDTO;
import com.engonow.lms.writing.dto.WritingSubmissionRequestDTO;
import com.engonow.lms.writing.dto.WritingSubmissionResponseDTO;
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
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class WritingSubmissionControllerTest {

    private MockMvc mockMvc;

    @Mock
    private WritingSubmissionService writingSubmissionService;

    @InjectMocks
    private WritingSubmissionController writingSubmissionController;

    private ObjectMapper objectMapper;
    private UUID studentId;
    private UUID submissionId;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(writingSubmissionController).build();
        objectMapper = new ObjectMapper();
        studentId = UUID.randomUUID();
        submissionId = UUID.randomUUID();
    }

    @Test
    @DisplayName("POST /api/v1/writing/submissions/submit returns 202 Accepted")
    void submitEssay_ReturnsAccepted() throws Exception {
        String essay = "In modern society, educational reforms have sparked widespread discussions regarding mandatory community service for secondary school students. Proponents argue that voluntary initiatives cultivate civic responsibility, whereas opponents assert that compulsory mandates undermine genuine altruism.";
        WritingSubmissionRequestDTO request = new WritingSubmissionRequestDTO(
            studentId,
            TaskType.TASK2,
            "Should community service be compulsory in high schools?",
            essay
        );

        WritingSubmissionResponseDTO responseDTO = new WritingSubmissionResponseDTO(
            submissionId,
            studentId,
            TaskType.TASK2,
            WritingSubmissionRequestDTO.countWords(essay),
            SubmissionStatus.PENDING,
            Instant.now()
        );

        when(writingSubmissionService.submitEssay(any(WritingSubmissionRequestDTO.class)))
            .thenReturn(responseDTO);

        mockMvc.perform(post("/api/v1/writing/submissions/submit")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(request)))
            .andExpect(status().isAccepted())
            .andExpect(jsonPath("$.id").value(submissionId.toString()))
            .andExpect(jsonPath("$.studentId").value(studentId.toString()))
            .andExpect(jsonPath("$.status").value("PENDING"));
    }

    @Test
    @DisplayName("GET /api/v1/writing/submissions/{submissionId} returns 200 OK with result")
    void getSubmissionResult_ReturnsResult() throws Exception {
        WritingFeedbackDetail feedbackDetail = new WritingFeedbackDetail(
            "Overall well-structured essay.",
            new EssayMetrics(250, 120, new BigDecimal("0.48"), new BigDecimal("16.5"), new BigDecimal("0.55")),
            List.of(new CriterionFeedback(WritingCriterion.TASK_RESPONSE, new BigDecimal("7.0"), "Good response", List.of("Strong intro"), List.of("Short conclusion"), "Expand conclusion")),
            List.of(),
            new CohesiveDeviceAnalysis(List.of("Furthermore"), List.of(), List.of()),
            List.of(),
            List.of()
        );

        WritingResultResponseDTO responseDTO = new WritingResultResponseDTO(
            submissionId,
            new BigDecimal("7.0"),
            new BigDecimal("7.0"),
            new BigDecimal("7.0"),
            new BigDecimal("7.0"),
            new BigDecimal("7.0"),
            feedbackDetail,
            EvaluatedBy.AI_AUTO,
            1,
            Instant.now()
        );

        when(writingSubmissionService.getSubmissionResult(submissionId, studentId))
            .thenReturn(responseDTO);

        mockMvc.perform(get("/api/v1/writing/submissions/{submissionId}", submissionId)
                .param("studentId", studentId.toString()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.submissionId").value(submissionId.toString()))
            .andExpect(jsonPath("$.overallBand").value(7.0))
            .andExpect(jsonPath("$.evaluatedBy").value("AI_AUTO"));
    }
}
