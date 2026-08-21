package com.engonow.lms.entity;

import com.engonow.lms.enums.SpeakingEvaluationStatus;
import jakarta.persistence.*;
import lombok.*;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * Stores the combined Speaking Test result: AI grading (80%) + Tutor rubric (20%).
 *
 * Design notes:
 *  - Linked to MockTestBooking via @OneToOne (owning side, holds the FK).
 *  - AI Score (0-9 IELTS band): stored as DECIMAL(4,2) for precision (e.g., 6.50).
 *  - Tutor rubric scores: 4 IELTS criteria (Fluency, Lexical, Grammar, Pronunciation).
 *  - overallBand: computed and stored on save — avoids recalculation on every read.
 *  - sessionId: the opaque ID returned by the AI service in the webhook callback,
 *    used for idempotency (re-delivered webhooks with same sessionId are ignored).
 */
@Entity
@Table(name = "speaking_session_results",
       uniqueConstraints = @UniqueConstraint(
           name = "uk_session_id",
           columnNames = "session_id"
       ))
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SpeakingSessionResult extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /**
     * Owning side of @OneToOne — holds FK column booking_id.
     */
    @OneToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(name = "booking_id", nullable = true,
                foreignKey = @ForeignKey(name = "fk_result_booking"))
    private MockTestBooking booking;

    /**
     * Opaque session ID from the AI grading service.
     * Used to deduplicate re-delivered webhook callbacks.
     */
    @Column(name = "session_id", nullable = false, length = 100)
    private String sessionId;

    // ── AI Grading Sub-Scores (80% weight component details) ──────────────

    @Column(name = "pronunciation_score", precision = 3, scale = 1)
    private BigDecimal pronunciationScore;

    @Column(name = "fluency_score", precision = 3, scale = 1)
    private BigDecimal fluencyScore;

    @Column(name = "lexical_score", precision = 3, scale = 1)
    private BigDecimal lexicalScore;

    @Column(name = "grammar_score", precision = 3, scale = 1)
    private BigDecimal grammarScore;

    @Column(name = "ai_score", precision = 4, scale = 2)
    private BigDecimal aiScore;

    @Column(name = "feedback_text", columnDefinition = "TEXT")
    private String feedbackText;

    @Builder.Default
    @Enumerated(EnumType.STRING)
    @Column(name = "evaluation_status", nullable = false, length = 40)
    private SpeakingEvaluationStatus evaluationStatus = SpeakingEvaluationStatus.SUCCESS;

    @Column(name = "self_corrections_text", columnDefinition = "TEXT")
    private String selfCorrectionsText;

    @Column(name = "evidences_text", columnDefinition = "TEXT")
    private String evidencesText;

    // ── Tutor Rubric (20% weight) ─────────────────────────────────────────
    // Each criterion is 0–9 IELTS band; average of 4 = tutor component score.

    @Column(name = "tutor_fluency_score", precision = 3, scale = 1)
    private BigDecimal tutorFluencyScore;

    @Column(name = "tutor_lexical_score", precision = 3, scale = 1)
    private BigDecimal tutorLexicalScore;

    @Column(name = "tutor_grammar_score", precision = 3, scale = 1)
    private BigDecimal tutorGrammarScore;

    @Column(name = "tutor_pronunciation_score", precision = 3, scale = 1)
    private BigDecimal tutorPronunciationScore;

    @Column(name = "tutor_comments", columnDefinition = "TEXT")
    private String tutorComments;

    // ── Computed Final Result ─────────────────────────────────────────────

    /**
     * overallBand = (aiScore * 0.80) + (avgTutorScore * 0.20)
     * Rounded to nearest 0.5 per IELTS band conventions.
     */
    @Column(name = "overall_band", precision = 3, scale = 1)
    private BigDecimal overallBand;

    @Builder.Default
    @Column(name = "is_complete", nullable = false)
    private Boolean isComplete = false;

    // ── Getters and Setters for self_corrections_text and evidences_text ──

    public String getSelfCorrectionsText() {
        return selfCorrectionsText;
    }

    public void setSelfCorrectionsText(String selfCorrectionsText) {
        this.selfCorrectionsText = selfCorrectionsText;
    }

    public String getEvidencesText() {
        return evidencesText;
    }

    public void setEvidencesText(String evidencesText) {
        this.evidencesText = evidencesText;
    }

    // ── Business Logic ────────────────────────────────────────────────────

    /**
     * Call this once both AI and tutor scores are available to compute the overall band.
     * Uses IELTS rounding: round to nearest 0.5 using remainder extraction.
     */
    public void computeFinalBand() {
        if (aiScore == null
            || tutorFluencyScore == null
            || tutorLexicalScore == null
            || tutorGrammarScore == null
            || tutorPronunciationScore == null) {
            return;
        }

        BigDecimal avgTutor = tutorFluencyScore
            .add(tutorLexicalScore)
            .add(tutorGrammarScore)
            .add(tutorPronunciationScore)
            .divide(BigDecimal.valueOf(4), 2, RoundingMode.HALF_UP);

        BigDecimal raw = aiScore.multiply(new BigDecimal("0.80"))
            .add(avgTutor.multiply(new BigDecimal("0.20")));

        // IELTS rounding: to nearest 0.5 using pure BigDecimal remainder extraction
        BigDecimal[] parts = raw.divideAndRemainder(BigDecimal.ONE);
        BigDecimal integerPart = parts[0];
        BigDecimal decimalPart = parts[1];

        BigDecimal roundedDecimal;
        if (decimalPart.compareTo(new BigDecimal("0.25")) < 0) {
            roundedDecimal = BigDecimal.ZERO;
        } else if (decimalPart.compareTo(new BigDecimal("0.75")) < 0) {
            roundedDecimal = new BigDecimal("0.5");
        } else {
            roundedDecimal = BigDecimal.ONE;
        }

        this.overallBand = integerPart.add(roundedDecimal).setScale(1, RoundingMode.HALF_UP);
        this.isComplete = true;
    }
}
