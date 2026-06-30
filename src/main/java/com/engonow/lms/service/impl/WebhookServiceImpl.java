package com.engonow.lms.service.impl;

import com.engonow.lms.dto.SpeakingEvidenceDTO;
import com.engonow.lms.dto.SpeakingWebhookPayload;
import com.engonow.lms.entity.MockTestBooking;
import com.engonow.lms.entity.SpeakingSessionResult;
import com.engonow.lms.exception.DuplicateWebhookException;
import com.engonow.lms.mapper.SpeakingMapper;
import com.engonow.lms.repository.MockTestBookingRepository;
import com.engonow.lms.repository.SpeakingSessionResultRepository;
import com.engonow.lms.service.WebhookService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.regex.Pattern;

@Slf4j
@Service
@RequiredArgsConstructor
public class WebhookServiceImpl implements WebhookService {

    private final SpeakingSessionResultRepository speakingSessionResultRepository;
    private final MockTestBookingRepository mockTestBookingRepository;
    private final SpeakingMapper speakingMapper;
    private final ObjectMapper objectMapper;

    @Override
    @Transactional
    public void handleAiSpeakingCallback(SpeakingWebhookPayload payload) {
        // Idempotency protection
        if (speakingSessionResultRepository.findBySessionId(payload.sessionId()).isPresent()) {
            throw new DuplicateWebhookException("Speaking session result with sessionId " + payload.sessionId() + " already exists.");
        }

        // Fetch MockTestBooking (sessionId represents bookingId)
        Long bookingId;
        try {
            bookingId = Long.parseLong(payload.sessionId());
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("Session ID must be a valid numeric booking ID: " + payload.sessionId());
        }

        MockTestBooking booking = mockTestBookingRepository.findById(bookingId)
                .orElseThrow(() -> new IllegalArgumentException("MockTestBooking not found for ID: " + bookingId));

        // Use SpeakingMapper to populate entity fields from payload (e.g. feedbackText)
        SpeakingSessionResult result = speakingMapper.toEntity(payload);
        result.setBooking(booking);

        // --- Business Rule 1: Evidence Filtering & Null-Safety with Regex Boundaries ---
        List<SpeakingEvidenceDTO> filteredEvidences = new ArrayList<>();
        List<SpeakingEvidenceDTO> inputEvidences = payload.evidences() != null ? payload.evidences() : Collections.emptyList();
        List<SpeakingWebhookPayload.SpeakingSelfCorrectionDTO> selfCorrections = payload.selfCorrections() != null ? payload.selfCorrections() : Collections.emptyList();

        for (SpeakingEvidenceDTO evidence : inputEvidences) {
            if (evidence != null) {
                boolean isGrammar = "GRAMMAR".equalsIgnoreCase(evidence.criterion());
                boolean shouldDrop = false;
                if (isGrammar && evidence.quote() != null) {
                    for (SpeakingWebhookPayload.SpeakingSelfCorrectionDTO selfCorr : selfCorrections) {
                        if (selfCorr != null && selfCorr.original() != null) {
                            String regex = "(?i)\\b" + Pattern.quote(selfCorr.original()) + "\\b";
                            Pattern pattern = Pattern.compile(regex);
                            if (pattern.matcher(evidence.quote()).find()) {
                                shouldDrop = true;
                                break;
                            }
                        }
                    }
                }
                if (!shouldDrop) {
                    filteredEvidences.add(evidence);
                }
            }
        }

        // --- Business Rule 2: Score Gatekeeper (Grammar, Lexical & Fluency) ---
        BigDecimal grammarScore = payload.grammarScore() != null ? payload.grammarScore().setScale(1, RoundingMode.HALF_UP) : BigDecimal.ZERO;
        long grammarEvidenceCount = filteredEvidences.stream()
                .filter(e -> "GRAMMAR".equalsIgnoreCase(e.criterion()))
                .count();
        if (grammarScore.compareTo(BigDecimal.valueOf(7.0)) < 0 && grammarEvidenceCount < 2) {
            log.warn("Self-corrected grammar penalty detected. Grammar score {} with {} evidences. Overriding score to 7.0.", grammarScore, grammarEvidenceCount);
            grammarScore = BigDecimal.valueOf(7.0);
        }

        BigDecimal lexicalScore = payload.lexicalScore() != null ? payload.lexicalScore().setScale(1, RoundingMode.HALF_UP) : BigDecimal.ZERO;
        long lexicalEvidenceCount = filteredEvidences.stream()
                .filter(e -> "LEXICAL".equalsIgnoreCase(e.criterion()))
                .count();
        if (lexicalScore.compareTo(BigDecimal.valueOf(7.0)) < 0 && lexicalEvidenceCount < 2) {
            log.warn("AI penalized lexical score to {} without sufficient citable evidences. Overriding to 7.0", lexicalScore);
            lexicalScore = BigDecimal.valueOf(7.0);
        }

        BigDecimal fluencyScore = payload.fluencyScore() != null ? payload.fluencyScore().setScale(1, RoundingMode.HALF_UP) : BigDecimal.ZERO;
        long fluencyEvidenceCount = 0L;
        if (payload.evidences() != null) {
            fluencyEvidenceCount = payload.evidences().stream()
                    .filter(e -> e != null && "FLUENCY".equalsIgnoreCase(e.criterion()))
                    .count();
        }
        if (fluencyScore.compareTo(BigDecimal.valueOf(7.0)) < 0 && fluencyEvidenceCount < 2) {
            log.warn("AI penalized fluency score to {} with only {} evidences. Overriding to 7.0 to protect the learner.", fluencyScore, fluencyEvidenceCount);
            fluencyScore = BigDecimal.valueOf(7.0);
        }

        // Set the final validated AI sub-scores on the entity
        result.setGrammarScore(grammarScore);
        result.setLexicalScore(lexicalScore);
        result.setFluencyScore(fluencyScore);

        // Calculate and set aiScore after all evidence overriding is completed (Single source of truth)
        BigDecimal safePronunciation = java.util.Optional.ofNullable(result.getPronunciationScore())
                .map(score -> score.setScale(1, RoundingMode.HALF_UP))
                .orElse(BigDecimal.ZERO);

        BigDecimal sum = safePronunciation
                .add(result.getFluencyScore())
                .add(result.getLexicalScore())
                .add(result.getGrammarScore());
        BigDecimal correctedAiScore = sum.divide(BigDecimal.valueOf(4), 2, RoundingMode.HALF_UP);
        result.setAiScore(correctedAiScore);

        // --- Business Rule 3: DB Persistence of Self-Corrections & Evidences ---
        String selfCorrectionsJson = "[]";
        if (payload.selfCorrections() != null) {
            try {
                selfCorrectionsJson = objectMapper.writeValueAsString(payload.selfCorrections());
            } catch (JsonProcessingException e) {
                log.error("Failed to serialize self-corrections list to JSON string", e);
            }
        }
        result.setSelfCorrectionsText(selfCorrectionsJson);

        // Serialize the filtered evidences list into a beautiful formatted JSON string and store in evidencesText
        String serializedEvidences = "[]";
        try {
            serializedEvidences = objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(filteredEvidences);
        } catch (Exception e) {
            log.error("Failed to serialize speaking evidences", e);
        }
        result.setEvidencesText(serializedEvidences);

        // Fallback tutor scores: 6.0 representing 20% weight
        BigDecimal fallbackTutorScore = BigDecimal.valueOf(6.0);
        result.setTutorFluencyScore(fallbackTutorScore);
        result.setTutorLexicalScore(fallbackTutorScore);
        result.setTutorGrammarScore(fallbackTutorScore);
        result.setTutorPronunciationScore(fallbackTutorScore);
        result.setTutorComments("Fallback automatic base evaluation");

        // Weighted average & IELTS rounding (nearest 0.5 or 0.0) via remainder extraction
        result.computeFinalBand();

        // Save Entity
        speakingSessionResultRepository.save(result);
    }
}
