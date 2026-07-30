package com.engonow.lms.service.impl;

import com.engonow.lms.dto.SpeakingEvidenceDTO;
import com.engonow.lms.dto.SpeakingWebhookPayload;
import com.engonow.lms.entity.MockTestBooking;
import com.engonow.lms.entity.SpeakingSessionResult;
import com.engonow.lms.enums.SpeakingEvaluationStatus;
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
        SpeakingSessionResult existingResult = speakingSessionResultRepository
                .findBySessionId(payload.sessionId())
                .orElse(null);

        // A PENDING row is the submission created with its outbox event. Any
        // terminal row means this callback has already been applied.
        if (existingResult != null
                && existingResult.getEvaluationStatus() != SpeakingEvaluationStatus.PENDING) {
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

        // Complete the pending submission row when present. The fallback path
        // preserves compatibility with callbacks created before the outbox flow.
        SpeakingSessionResult result = existingResult != null
                ? existingResult
                : speakingMapper.toEntity(payload);
        result.setSessionId(payload.sessionId());
        result.setFeedbackText(payload.feedbackText());
        result.setEvaluationStatus(
                payload.status() != null ? payload.status() : SpeakingEvaluationStatus.SUCCESS
        );
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
                    .filter(e -> !"PART_3".equalsIgnoreCase(e.part()))
                    .count();
        }
        if (fluencyScore.compareTo(BigDecimal.valueOf(7.0)) < 0 && fluencyEvidenceCount < 2) {
            log.warn("AI penalized fluency score to {} with only {} evidences. Overriding to 7.0 to protect the learner.", fluencyScore, fluencyEvidenceCount);
            fluencyScore = BigDecimal.valueOf(7.0);
        }

        BigDecimal pronunciationScore = payload.pronunciationScore() != null ? payload.pronunciationScore() : BigDecimal.ZERO;

        // --- PHASE 1: DATA NORMALIZATION & FLOOR CAP ---
        pronunciationScore = pronunciationScore.setScale(0, RoundingMode.HALF_UP);
        fluencyScore = fluencyScore.setScale(0, RoundingMode.HALF_UP);
        lexicalScore = lexicalScore.setScale(0, RoundingMode.HALF_UP);
        grammarScore = grammarScore.setScale(0, RoundingMode.HALF_UP);

        // DEFERRED PER CTO DIRECTIVE: IELTS criteria are graded independently without cross-skill penalization.
        /*
        boolean isFloorCapTriggered = false;
        BigDecimal minCriterion = pronunciationScore.min(fluencyScore).min(lexicalScore).min(grammarScore);
        if (minCriterion.compareTo(BigDecimal.valueOf(5)) < 0) {
            isFloorCapTriggered = true;
            log.warn("[GATEKEEPER - CRITICAL FLOOR CAP] Detected a critical breakdown in criteria. Min score is {}. The final holistic band score will be capped at 5.5.", minCriterion);
        }
        */
        // --- END OF PHASE 1 ---

        // DEFERRED PER CTO DIRECTIVE: IELTS criteria are graded independently without cross-skill penalization.
        /*
        // ─── PHASE 2: CROSS-SKILL PENALTIES ───
        // 1. PILLAR II: ASYMMETRY PENALTY (Luật Phạt Lệch Trần)
        BigDecimal maxCriterion = pronunciationScore.max(fluencyScore).max(lexicalScore).max(grammarScore);
        BigDecimal scoreDelta = maxCriterion.subtract(minCriterion);
        if (scoreDelta.compareTo(BigDecimal.valueOf(2)) > 0) {
            BigDecimal allowedMax = minCriterion.add(BigDecimal.valueOf(2));
            if (pronunciationScore.compareTo(allowedMax) > 0) {
                pronunciationScore = allowedMax;
            }
            if (fluencyScore.compareTo(allowedMax) > 0) {
                fluencyScore = allowedMax;
            }
            if (lexicalScore.compareTo(allowedMax) > 0) {
                lexicalScore = allowedMax;
            }
            if (grammarScore.compareTo(allowedMax) > 0) {
                grammarScore = allowedMax;
            }
            log.warn("[GATEKEEPER - ASYMMETRY PENALTY] Detected extreme score variance (Delta = {}). Capping outlier high scores to allowed maximum: {}", scoreDelta, allowedMax);
        }

        // 2. PILLAR III: CROSS-SKILL GRAVITY PULL (Luật Bù Trừ Kỹ Năng)
        // Rule 3A (Grammar drags down Fluency)
        if (grammarScore.compareTo(BigDecimal.valueOf(4)) <= 0) {
            BigDecimal fcLimit = grammarScore.add(BigDecimal.valueOf(2));
            if (fluencyScore.compareTo(fcLimit) > 0) {
                fluencyScore = fcLimit;
                log.warn("[GATEKEEPER - COHERENCE BOUNDARY] Broken grammar (GRA <= 4) naturally degrades fluency. Capping FC score to: {}", fcLimit);
            }
        }

        // Rule 3B (Unintelligible Pronunciation isolates Lexical Resource)
        if (pronunciationScore.compareTo(BigDecimal.valueOf(4)) <= 0) {
            if (lexicalScore.compareTo(BigDecimal.valueOf(5)) > 0) {
                lexicalScore = BigDecimal.valueOf(5);
                log.warn("[GATEKEEPER - LEXICAL ISOLATION] Unintelligible pronunciation (PR <= 4) voids advanced vocabulary. Capping LR score to 5.");
            }
        }
        // ─── END OF PHASE 2 ───
        */

        // Set the final validated AI sub-scores on the entity
        result.setGrammarScore(grammarScore);
        result.setLexicalScore(lexicalScore);
        result.setFluencyScore(fluencyScore);
        result.setPronunciationScore(pronunciationScore);

        // ─── PHASE 3: OFFICIAL CAMBRIDGE ROUNDING ───
        BigDecimal sum = pronunciationScore.add(fluencyScore).add(lexicalScore).add(grammarScore);
        BigDecimal rawAverage = sum.divide(BigDecimal.valueOf(4), 3, RoundingMode.HALF_UP);

        double val = rawAverage.doubleValue();
        double floor = Math.floor(val);
        double remainder = val - floor;
        double roundedValue;
        if (remainder < 0.25) {
            roundedValue = floor;
        } else if (remainder >= 0.25 && remainder < 0.75) {
            roundedValue = floor + 0.5;
        } else {
            roundedValue = floor + 1.0;
        }
        BigDecimal finalScore = BigDecimal.valueOf(roundedValue).setScale(1, RoundingMode.HALF_UP);

        log.info("[GATEKEEPER] Independent Cambridge Floor Rounding applied. Raw Avg: {} -> Final Band: {}", rawAverage, finalScore);

        result.setAiScore(finalScore);
        // ─── END OF PHASE 3 ───

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
