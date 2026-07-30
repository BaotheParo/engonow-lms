package com.engonow.lms.controller;

import com.engonow.lms.dto.SpeakingSubmissionRequestDTO;
import com.engonow.lms.dto.SpeakingSubmissionResponseDTO;
import com.engonow.lms.enums.SpeakingEvaluationStatus;
import com.engonow.lms.service.SubmissionService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SpeakingSubmissionControllerTest {

    @Test
    void returns202AcceptedWithAsyncResponse() {
        SubmissionService submissionService = mock(SubmissionService.class);
        SubmissionController controller = new SubmissionController(submissionService);
        SpeakingSubmissionRequestDTO request = new SpeakingSubmissionRequestDTO(
                "42",
                new ObjectMapper().createArrayNode(),
                "https://cdn.example.test/speaking/42.mp3");
        SpeakingSubmissionResponseDTO serviceResponse =
                new SpeakingSubmissionResponseDTO(
                        "42",
                        SpeakingEvaluationStatus.PENDING,
                        "Speaking evaluation accepted for asynchronous processing");
        when(submissionService.submitSpeakingEvaluation(request))
                .thenReturn(serviceResponse);

        ResponseEntity<SpeakingSubmissionResponseDTO> response =
                controller.submitSpeakingResponse(request);

        assertEquals(HttpStatus.ACCEPTED, response.getStatusCode());
        assertEquals(serviceResponse, response.getBody());
    }
}
