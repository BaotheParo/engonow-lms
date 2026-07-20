package com.engonow.lms.service.impl;

import com.engonow.lms.dto.SpeakingEvidenceDTO;
import com.engonow.lms.dto.SpeakingWebhookPayload;
import com.engonow.lms.entity.MockTestBooking;
import com.engonow.lms.entity.SpeakingSessionResult;
import com.engonow.lms.enums.SpeakingEvaluationStatus;
import com.engonow.lms.mapper.SpeakingMapper;
import com.engonow.lms.repository.MockTestBookingRepository;
import com.engonow.lms.repository.SpeakingSessionResultRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.Spy;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.util.Collections;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
public class WebhookServiceImplTest {

    @Mock
    private SpeakingSessionResultRepository speakingSessionResultRepository;

    @Mock
    private MockTestBookingRepository mockTestBookingRepository;

    @Mock
    private SpeakingMapper speakingMapper;

    @Spy
    private ObjectMapper objectMapper = new ObjectMapper();

    @InjectMocks
    private WebhookServiceImpl webhookService;

    // Helper evidences to satisfy Business Rule 2 (preventing automatic override to 7.0 when score < 7.0)
    private static final List<SpeakingEvidenceDTO> EVIDENCES_WITH_MINIMUM_REQUIRED_COUNT = List.of(
            new SpeakingEvidenceDTO("GRAMMAR", "PART_1", "Q1", "Quote 1", "Error 1", "Corr 1", "Expl 1"),
            new SpeakingEvidenceDTO("GRAMMAR", "PART_1", "Q2", "Quote 2", "Error 2", "Corr 2", "Expl 2"),
            new SpeakingEvidenceDTO("LEXICAL", "PART_1", "Q1", "Quote 1", "Error 1", "Corr 1", "Expl 1"),
            new SpeakingEvidenceDTO("LEXICAL", "PART_1", "Q2", "Quote 2", "Error 2", "Corr 2", "Expl 2"),
            new SpeakingEvidenceDTO("FLUENCY", "PART_1", "Q1", "Quote 1", "Error 1", "Corr 1", "Expl 1"),
            new SpeakingEvidenceDTO("FLUENCY", "PART_1", "Q2", "Quote 2", "Error 2", "Corr 2", "Expl 2")
    );

    @Test
    public void testPartialSuccessLowAudioConfidenceIsPersistedWithScores() {
        String sessionId = "456";
        SpeakingWebhookPayload payload = new SpeakingWebhookPayload(
                sessionId,
                BigDecimal.valueOf(7),
                BigDecimal.valueOf(7),
                BigDecimal.valueOf(7),
                BigDecimal.valueOf(7),
                EVIDENCES_WITH_MINIMUM_REQUIRED_COUNT,
                Collections.emptyList(),
                "Pronunciation score is for reference only.",
                SpeakingEvaluationStatus.PARTIAL_SUCCESS_LOW_AUDIO_CONF
        );
        MockTestBooking booking = new MockTestBooking();
        booking.setId(456L);
        SpeakingSessionResult resultEntity = new SpeakingSessionResult();
        resultEntity.setSessionId(sessionId);

        when(speakingSessionResultRepository.findBySessionId(sessionId)).thenReturn(Optional.empty());
        when(mockTestBookingRepository.findById(456L)).thenReturn(Optional.of(booking));
        when(speakingMapper.toEntity(payload)).thenReturn(resultEntity);
        when(speakingSessionResultRepository.save(any(SpeakingSessionResult.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        webhookService.handleAiSpeakingCallback(payload);

        assertEquals(
                SpeakingEvaluationStatus.PARTIAL_SUCCESS_LOW_AUDIO_CONF,
                resultEntity.getEvaluationStatus()
        );
        assertEquals(0, BigDecimal.valueOf(7).compareTo(resultEntity.getPronunciationScore()));
    }

    /**
     * Helper method to assert the scoring output.
     * Mocks dependencies, runs handleAiSpeakingCallback, and asserts the saved result.
     */
    private void assertScoring(
            Double prInput, Double fcInput, Double lrInput, Double graInput,
            double expectedPr, double expectedFc, double expectedLr, double expectedGra,
            double expectedFinalScore) {
        
        String sessionId = "123";
        SpeakingWebhookPayload payload = new SpeakingWebhookPayload(
                sessionId,
                prInput != null ? BigDecimal.valueOf(prInput) : null,
                fcInput != null ? BigDecimal.valueOf(fcInput) : null,
                lrInput != null ? BigDecimal.valueOf(lrInput) : null,
                graInput != null ? BigDecimal.valueOf(graInput) : null,
                EVIDENCES_WITH_MINIMUM_REQUIRED_COUNT,
                Collections.emptyList(),
                "Good attempt"
        );

        MockTestBooking booking = new MockTestBooking();
        booking.setId(123L);

        when(speakingSessionResultRepository.findBySessionId(sessionId)).thenReturn(Optional.empty());
        when(mockTestBookingRepository.findById(123L)).thenReturn(Optional.of(booking));
        
        SpeakingSessionResult resultEntity = new SpeakingSessionResult();
        resultEntity.setSessionId(sessionId);
        when(speakingMapper.toEntity(payload)).thenReturn(resultEntity);

        ArgumentCaptor<SpeakingSessionResult> resultCaptor = ArgumentCaptor.forClass(SpeakingSessionResult.class);
        when(speakingSessionResultRepository.save(resultCaptor.capture())).thenAnswer(invocation -> invocation.getArgument(0));

        webhookService.handleAiSpeakingCallback(payload);

        SpeakingSessionResult savedResult = resultCaptor.getValue();
        assertNotNull(savedResult);
        
        // Assert modified sub-scores
        assertEquals(0, BigDecimal.valueOf(expectedPr).compareTo(savedResult.getPronunciationScore()), 
                "Pronunciation score mismatch. Expected: " + expectedPr + ", Actual: " + savedResult.getPronunciationScore());
        assertEquals(0, BigDecimal.valueOf(expectedFc).compareTo(savedResult.getFluencyScore()), 
                "Fluency score mismatch. Expected: " + expectedFc + ", Actual: " + savedResult.getFluencyScore());
        assertEquals(0, BigDecimal.valueOf(expectedLr).compareTo(savedResult.getLexicalScore()), 
                "Lexical score mismatch. Expected: " + expectedLr + ", Actual: " + savedResult.getLexicalScore());
        assertEquals(0, BigDecimal.valueOf(expectedGra).compareTo(savedResult.getGrammarScore()), 
                "Grammar score mismatch. Expected: " + expectedGra + ", Actual: " + savedResult.getGrammarScore());
        
        // Assert final Cambridge-rounded average band score
        assertEquals(0, BigDecimal.valueOf(expectedFinalScore).compareTo(savedResult.getAiScore()), 
                "AI/Final overall score mismatch. Expected: " + expectedFinalScore + ", Actual: " + savedResult.getAiScore());
    }

    /**
     * Test Phase 3 rounding logic without triggering Phase 2 penalties.
     * Ensures raw decimal scores are normalized to integers first, and then the final average rounds
     * correctly according to the Cambridge 0.25 / 0.75 thresholds.
     */
    @ParameterizedTest
    @CsvSource({
        // prInput, fcInput, lrInput, graInput, expectedPr, expectedFc, expectedLr, expectedGra, expectedFinalScore
        "7.4, 7.4, 7.4, 7.4, 7.0, 7.0, 7.0, 7.0, 7.0", // Perfect alignment
        "9.0, 4.0, 9.0, 4.0, 9.0, 4.0, 9.0, 4.0, 6.5", // Extreme variance that would have triggered Asymmetry, but now shouldn't (Avg: 26/4 = 6.5)
        "9.0, 4.0, 9.0, 5.0, 9.0, 4.0, 9.0, 5.0, 7.0", // Extreme variance triggering floor rounding up (Avg: 27/4 = 6.75 -> 7.0)
        "8.0, 8.0, 8.0, 9.0, 8.0, 8.0, 8.0, 9.0, 8.5", // Avg: 33/4 = 8.25 -> 8.5
        "5.0, 5.0, 5.0, 6.0, 5.0, 5.0, 5.0, 6.0, 5.5", // Avg: 21/4 = 5.25 -> 5.5
        "6.0, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0"  // Avg: 24/4 = 6.0
    })
    public void testPhase3_CambridgeOfficialRounding(
            Double prInput, Double fcInput, Double lrInput, Double graInput,
            double expectedPr, double expectedFc, double expectedLr, double expectedGra,
            double expectedFinalScore) {
        assertScoring(prInput, fcInput, lrInput, graInput, expectedPr, expectedFc, expectedLr, expectedGra, expectedFinalScore);
    }

    // DEFERRED PER CTO DIRECTIVE: Tests disabled because IELTS criteria are now graded independently without cross-skill penalization.
    /*
    @ParameterizedTest
    @CsvSource({
        // prInput, fcInput, lrInput, graInput, expectedPr, expectedFc, expectedLr, expectedGra, expectedFinalScore
        "4.0, 5.0, 5.0, 5.0, 4.0, 5.0, 5.0, 5.0, 5.0", // min is 4.0 (< 5) -> Floor Cap triggered. Avg = 4.75 -> 5.0 <= 5.5
        "4.0, 6.0, 6.0, 6.0, 4.0, 6.0, 5.0, 6.0, 5.5", // min is 4.0 (< 5) -> Floor Cap triggered. LR capped to 5.0 (PR <= 4). Avg = 5.25 -> 5.5 <= 5.5
        "4.0, 8.0, 8.0, 8.0, 4.0, 6.0, 5.0, 6.0, 5.5", // min is 4.0. Asymmetry Penalty caps others to 6. LR capped to 5.0. Avg = 5.25 -> 5.5
        "3.0, 5.0, 5.0, 5.0, 3.0, 5.0, 5.0, 5.0, 4.5", // min is 3.0 (< 5) -> Floor Cap triggered. Asymmetry Penalty caps other scores to 5. Avg = 4.5 -> 4.5 <= 5.5
        "3.0, 6.0, 6.0, 6.0, 3.0, 5.0, 5.0, 5.0, 4.5"  // min is 3.0 (< 5). Asymmetry Penalty caps scores to 5. Avg = 4.5 -> 4.5 <= 5.5
    })
    public void testPhase1_CriticalFloorCap(
            Double prInput, Double fcInput, Double lrInput, Double graInput,
            double expectedPr, double expectedFc, double expectedLr, double expectedGra,
            double expectedFinalScore) {
        assertScoring(prInput, fcInput, lrInput, graInput, expectedPr, expectedFc, expectedLr, expectedGra, expectedFinalScore);
    }
    */

    // DEFERRED PER CTO DIRECTIVE: Tests disabled because IELTS criteria are now graded independently without cross-skill penalization.
    /*
    @ParameterizedTest
    @CsvSource({
        // prInput, fcInput, lrInput, graInput, expectedPr, expectedFc, expectedLr, expectedGra, expectedFinalScore
        "5.0, 9.0, 9.0, 9.0, 5.0, 7.0, 7.0, 7.0, 6.5", // delta = 4 > 2 -> capped to 7.0. Avg = 6.5
        "6.0, 6.0, 9.0, 6.0, 6.0, 6.0, 8.0, 6.0, 6.5", // delta = 3 > 2 -> capped to 8.0. Avg = 6.5
        "5.0, 8.0, 5.0, 5.0, 5.0, 7.0, 5.0, 5.0, 5.5"  // delta = 3 > 2 -> capped to 7.0. Avg = 5.5
    })
    public void testPhase2_AsymmetryPenalty(
            Double prInput, Double fcInput, Double lrInput, Double graInput,
            double expectedPr, double expectedFc, double expectedLr, double expectedGra,
            double expectedFinalScore) {
        assertScoring(prInput, fcInput, lrInput, graInput, expectedPr, expectedFc, expectedLr, expectedGra, expectedFinalScore);
    }
    */

    // DEFERRED PER CTO DIRECTIVE: Tests disabled because IELTS criteria are now graded independently without cross-skill penalization.
    /*
    @ParameterizedTest
    @CsvSource({
        // prInput, fcInput, lrInput, graInput, expectedPr, expectedFc, expectedLr, expectedGra, expectedFinalScore
        "4.0, 8.0, 4.0, 4.0, 4.0, 6.0, 4.0, 4.0, 4.5", // delta = 4 > 2 -> Asymmetry caps to 6.0. Rule 3A checks 4.0 + 2 = 6.0 limit. Avg = 4.5
        "3.0, 7.0, 3.0, 3.0, 3.0, 5.0, 3.0, 3.0, 3.5", // delta = 4 > 2 -> Asymmetry caps to 5.0. Avg = 3.5
        "4.0, 7.0, 5.0, 4.0, 4.0, 6.0, 5.0, 4.0, 5.0"  // delta = 3 > 2 -> Asymmetry caps to 6.0. Avg = 4.75 -> 5.0
    })
    public void testPhase2_GravityPull_GrammarDragsFluency(
            Double prInput, Double fcInput, Double lrInput, Double graInput,
            double expectedPr, double expectedFc, double expectedLr, double expectedGra,
            double expectedFinalScore) {
        assertScoring(prInput, fcInput, lrInput, graInput, expectedPr, expectedFc, expectedLr, expectedGra, expectedFinalScore);
    }
    */

    // DEFERRED PER CTO DIRECTIVE: Tests disabled because IELTS criteria are now graded independently without cross-skill penalization.
    /*
    @ParameterizedTest
    @CsvSource({
        // prInput, fcInput, lrInput, graInput, expectedPr, expectedFc, expectedLr, expectedGra, expectedFinalScore
        "4.0, 6.0, 6.0, 6.0, 4.0, 6.0, 5.0, 6.0, 5.5", // delta = 2 <= 2 (no asymmetry). Rule 3B caps LR to 5.0. Avg = 5.25 -> 5.5
        "4.0, 6.0, 8.0, 6.0, 4.0, 6.0, 5.0, 6.0, 5.5", // delta = 4 > 2 -> Asymmetry caps LR to 6.0, then Rule 3B caps LR to 5.0. Avg = 5.25 -> 5.5
        "3.0, 5.0, 5.0, 5.0, 3.0, 5.0, 5.0, 5.0, 4.5"  // delta = 2 <= 2. Rule 3B checks but LR is 5.0. Avg = 4.5
    })
    public void testPhase2_GravityPull_PronunciationIsolatesLexical(
            Double prInput, Double fcInput, Double lrInput, Double graInput,
            double expectedPr, double expectedFc, double expectedLr, double expectedGra,
            double expectedFinalScore) {
        assertScoring(prInput, fcInput, lrInput, graInput, expectedPr, expectedFc, expectedLr, expectedGra, expectedFinalScore);
    }
    */
}
