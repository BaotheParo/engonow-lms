package com.engonow.lms.controller;

import com.engonow.lms.dto.SpeakingEvidenceDTO;
import com.engonow.lms.dto.SpeakingWebhookPayload;
import com.engonow.lms.entity.MockTestBooking;
import com.engonow.lms.entity.SpeakingSessionResult;
import com.engonow.lms.repository.MockTestBookingRepository;
import com.engonow.lms.repository.SpeakingSessionResultRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;
import java.util.Collections;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "app.seeding.enabled=true")
@AutoConfigureMockMvc
public class WebhookCallbackControllerIT {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private SpeakingSessionResultRepository speakingSessionResultRepository;

    @Autowired
    private MockTestBookingRepository mockTestBookingRepository;

    @AfterEach
    public void cleanUp() {
        speakingSessionResultRepository.deleteAllInBatch();
    }

    @Test
    public void testHandleWebhook_Success_WithEvidenceOverriding() throws Exception {
        // Arrange
        MockTestBooking mockBooking = mockTestBookingRepository.findAll().stream()
                .findFirst()
                .orElseThrow(() -> new AssertionError("No test booking seeded in the database"));
        String sessionId = mockBooking.getId().toString();

        // Create evidence list containing only ONE grammar evidence
        List<SpeakingEvidenceDTO> evidences = List.of(
                new SpeakingEvidenceDTO(
                        "GRAMMAR",
                        "Yesterday I go to the marketplace with my family",
                        "Verb Tense",
                        "Yesterday I went to the marketplace with my family",
                        "Learner used present simple 'go' instead of past simple 'went' for a past action."
                )
        );

        SpeakingWebhookPayload payload = new SpeakingWebhookPayload(
                sessionId,
                BigDecimal.valueOf(7.0),
                BigDecimal.valueOf(7.5),
                BigDecimal.valueOf(8.0),
                BigDecimal.valueOf(6.0), // Under 7.0, triggers override
                evidences,
                "Feedback text"
        );

        // Act
        mockMvc.perform(post("/api/v1/callback/ai-grading")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isOk());

        // Assert
        SpeakingSessionResult savedResult = speakingSessionResultRepository.findBySessionId(sessionId)
                .orElseThrow(() -> new AssertionError("SpeakingSessionResult was not saved to database"));

        // Grammar score should be overridden to 7.0 from 6.0
        assertEquals(0, BigDecimal.valueOf(7.0).compareTo(savedResult.getGrammarScore()));
        // Lexical score is 8.0 (no override)
        assertEquals(0, BigDecimal.valueOf(8.0).compareTo(savedResult.getLexicalScore()));
        // Corrected average AI score = (7.0 + 7.5 + 8.0 + 7.0) / 4 = 7.375 (rounded to 7.38)
        assertEquals(0, BigDecimal.valueOf(7.38).compareTo(savedResult.getAiScore()));
    }

    @Test
    public void testHandleWebhook_Success_IeltsRounding() throws Exception {
        // Arrange
        MockTestBooking mockBooking = mockTestBookingRepository.findAll().stream()
                .findFirst()
                .orElseThrow(() -> new AssertionError("No test booking seeded in the database"));
        String sessionId = mockBooking.getId().toString();

        // Design mock dataset:
        // Pronunciation: 7.5, Fluency: 7.5, Lexical: 8.0, Grammar: 7.5 -> Avg AI: 7.625
        // Tutor fallback: 6.0
        // Weighted average raw = 7.625 * 0.8 + 6.0 * 0.2 = 6.1 + 1.2 = 7.3
        // IELTS rounding should round raw 7.3 to nearest 0.5 -> 7.5
        SpeakingWebhookPayload payload = new SpeakingWebhookPayload(
                sessionId,
                BigDecimal.valueOf(7.5),
                BigDecimal.valueOf(7.5),
                BigDecimal.valueOf(8.0),
                BigDecimal.valueOf(7.5),
                Collections.emptyList(),
                "Feedback text"
        );

        // Act
        mockMvc.perform(post("/api/v1/callback/ai-grading")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isOk());

        // Assert
        SpeakingSessionResult savedResult = speakingSessionResultRepository.findBySessionId(sessionId)
                .orElseThrow(() -> new AssertionError("SpeakingSessionResult was not saved to database"));

        // Weighted average 7.3 should be rounded to 7.5 overall band
        assertEquals(0, BigDecimal.valueOf(7.5).compareTo(savedResult.getOverallBand()));
    }

    @Test
    public void testHandleWebhook_DuplicateSession_ThrowsException() throws Exception {
        // Arrange
        MockTestBooking mockBooking = mockTestBookingRepository.findAll().stream()
                .findFirst()
                .orElseThrow(() -> new AssertionError("No test booking seeded in the database"));

        // Pre-save the session result to make it a duplicate
        SpeakingSessionResult existingResult = SpeakingSessionResult.builder()
                .booking(mockBooking)
                .sessionId("dup_session_123")
                .pronunciationScore(BigDecimal.valueOf(7.0))
                .fluencyScore(BigDecimal.valueOf(7.0))
                .lexicalScore(BigDecimal.valueOf(7.0))
                .grammarScore(BigDecimal.valueOf(7.0))
                .aiScore(BigDecimal.valueOf(7.0))
                .overallBand(BigDecimal.valueOf(7.0))
                .feedbackText("Pre-existing")
                .isComplete(true)
                .build();
        speakingSessionResultRepository.save(existingResult);

        SpeakingWebhookPayload payload = new SpeakingWebhookPayload(
                "dup_session_123",
                BigDecimal.valueOf(7.0),
                BigDecimal.valueOf(7.5),
                BigDecimal.valueOf(8.0),
                BigDecimal.valueOf(7.0),
                Collections.emptyList(),
                "Feedback text"
        );

        // Act & Assert
        mockMvc.perform(post("/api/v1/callback/ai-grading")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isConflict());
    }
}
